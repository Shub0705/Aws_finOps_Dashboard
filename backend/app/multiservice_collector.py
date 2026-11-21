import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import psycopg

from botocore.exceptions import ClientError
from psycopg.types.json import Jsonb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("multiservice")

DATABASE_URL = os.environ["DATABASE_URL"].replace(
    "postgresql+psycopg://",
    "postgresql://",
    1
)

DATA_DIR = Path(
    os.getenv("CLOUDTRAIL_DATA_DIR", "/app/cloudtrail-data")
)

INTERVAL = 300
SOURCE = "multiservice-v1"

ACCOUNTS = {
    "407125827522":
        "shubham-karale@infononprod-407125827522",
    "615167489437":
        "shubham-karale@infoclientenv-615167489437",
}

REGIONS = [
    r.strip()
    for r in os.getenv(
        "CLOUDTRAIL_REGIONS",
        "us-east-1"
    ).split(",")
    if r.strip()
]

# Resource ID extraction for known API response formats.
# Expand these adapters as services are verified.
RESOURCE_FIELDS = {
    "RunInstances": ("instancesSet", "items", "instanceId"),
    "CreateVolume": ("volumeId",),
    "CreateVpc": ("vpc", "vpcId"),
    "CreateSubnet": ("subnet", "subnetId"),
    "CreateSecurityGroup": ("groupId",),
    "CreateNatGateway": ("natGateway", "natGatewayId"),
    "CreateInternetGateway": ("internetGateway", "internetGatewayId"),
    "CreateDBInstance": ("dBInstance", "dBInstanceArn"),
    "CreateFunction20150331": ("functionArn",),
    "CreateCluster": ("cluster", "arn"),
}

def get_nested(data, path):
    current = data

    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)

    return current


def extract_resources(event):
    name = event.get("eventName", "")
    response = event.get("responseElements") or {}
    params = event.get("requestParameters") or {}

    results = []

    if name == "RunInstances":
        items = get_nested(
            response,
            ("instancesSet", "items")
        ) or []

        if isinstance(items, dict):
            items = [items]

        for item in items:
            if isinstance(item, dict) and item.get("instanceId"):
                results.append(item["instanceId"])

    elif name in RESOURCE_FIELDS:
        value = get_nested(response, RESOURCE_FIELDS[name])

        if isinstance(value, str) and value:
            results.append(value)

    # Known request-side identifiers for delete/update events.
    request_ids = {
        "TerminateInstances": ("instancesSet", "items"),
        "DeleteVolume": ("volumeId",),
        "DeleteVpc": ("vpcId",),
        "DeleteSubnet": ("subnetId",),
        "DeleteSecurityGroup": ("groupId",),
        "DeleteNatGateway": ("natGatewayId",),
        "DeleteDBInstance": ("dBInstanceIdentifier",),
        "DeleteFunction20150331": ("functionName",),
    }

    if name == "TerminateInstances":
        items = get_nested(
            params, ("instancesSet", "items")
        ) or []

        if isinstance(items, dict):
            items = [items]

        for item in items:
            if isinstance(item, dict) and item.get("instanceId"):
                results.append(item["instanceId"])

    elif name in request_ids:
        value = get_nested(params, request_ids[name])

        if isinstance(value, str) and value:
            results.append(value)

    # CloudTrail resource ARNs are useful for other event types.
    for item in event.get("resources") or []:
        if isinstance(item, dict):
            arn = item.get("ARN")
            if arn:
                results.append(arn)

    return list(dict.fromkeys(results))


def actor(event):
    identity = event.get("userIdentity") or {}
    context = identity.get("sessionContext") or {}

    return (
        context.get("sourceIdentity")
        or identity.get("userName")
        or identity.get("arn")
        or identity.get("principalId")
    )


def save_event_file(account_id, region, event_id, event):
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", event_id)

    folder = DATA_DIR / account_id / region / "multiservice"
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"{safe_id}.json"

    if path.exists():
        return

    temporary = path.with_suffix(".tmp")
    with open(temporary, "w") as file:
        json.dump(event, file)
        file.flush()
        os.fsync(file.fileno())

    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def process_event(conn, account_id, region, item):
    raw = item.get("CloudTrailEvent")
    if not raw:
        return 0

    event = json.loads(raw)

    event_id = event.get("eventID") or item.get("EventId")
    event_name = event.get("eventName", "")
    event_time = item.get("EventTime")

    if not event_id or not event_time:
        return 0

    # Store failed API attempts in raw history, but do not
    # treat them as successful resource changes.
    save_event_file(account_id, region, event_id, event)

    if event.get("errorCode"):
        return 0

    resource_ids = extract_resources(event)

    if not resource_ids:
        return 0

    service = event.get("eventSource", "unknown")
    service_code = service.split(".")[0].upper()

    saved = 0

    with conn.transaction():
        for resource_id in resource_ids:
            result = conn.execute(
                """
                INSERT INTO cm_resource_events (
                    account_id,
                    event_id,
                    resource_id,
                    service_code,
                    region,
                    event_name,
                    event_time,
                    actor,
                    actor_type,
                    event_source,
                    event_json
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (
                    account_id,event_id,resource_id
                )
                DO NOTHING
                RETURNING id
                """,
                (
                    account_id,
                    event_id,
                    resource_id,
                    service_code,
                    event.get("awsRegion") or region,
                    event_name,
                    event_time,
                    actor(event),
                    (event.get("userIdentity") or {}).get("type"),
                    service,
                    Jsonb(event),
                )
            ).fetchone()

            if result:
                saved += 1

    return saved


def collect(account_id, profile, region):
    session = boto3.Session(
        profile_name=profile,
        region_name=region
    )

    identity = session.client("sts").get_caller_identity()

    if identity["Account"] != account_id:
        raise RuntimeError("AWS account mismatch")

    client = session.client("cloudtrail")

    with psycopg.connect(
        DATABASE_URL, autocommit=True
    ) as conn:

        row = conn.execute(
            """
            SELECT checkpoint
            FROM cm_resource_collector_state
            WHERE account_id=%s
              AND region=%s
              AND source=%s
            """,
            (account_id, region, SOURCE)
        ).fetchone()

        end = datetime.now(timezone.utc)

        start = (
            row[0] - timedelta(hours=24)
            if row
            else end - timedelta(days=1)
        )

        # CloudTrail Event History has a limited lookback.
        start = max(start, end - timedelta(days=89))

        count = 0

        paginator = client.get_paginator("lookup_events")

        for page in paginator.paginate(
            StartTime=start,
            EndTime=end,
            PaginationConfig={"PageSize": 50}
        ):
            for event in page.get("Events", []):
                count += process_event(
                    conn, account_id, region, event
                )

        with conn.transaction():
            conn.execute(
                """
                INSERT INTO cm_resource_collector_state
                    (account_id,region,source,checkpoint)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (account_id,region,source)
                DO UPDATE SET
                    checkpoint=EXCLUDED.checkpoint,
                    updated_at=NOW()
                """,
                (account_id, region, SOURCE, end)
            )

        log.info(
            "Account=%s Region=%s New resource events=%s",
            account_id, region, count
        )


while True:
    for account_id, profile in ACCOUNTS.items():
        for region in REGIONS:
            try:
                collect(account_id, profile, region)
            except Exception:
                log.exception(
                    "Collection failed account=%s region=%s",
                    account_id, region
                )

    time.sleep(INTERVAL)
