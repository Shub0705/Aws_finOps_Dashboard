
import os
import re
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import psycopg
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("human-resource-collector")

INTERVAL = int(os.getenv("COLLECT_INTERVAL", "300"))
REGIONS = [
    x.strip()
    for x in os.getenv("CLOUDTRAIL_REGIONS", "us-east-1").split(",")
    if x.strip()
]
DATA_DIR = Path(os.getenv("CLOUDTRAIL_DATA_DIR", "/app/cloudtrail-data"))

ACCOUNTS = {
    "407125827522": {
        "name": "INFO NON PROD",
        "profile": "shubham-karale@infononprod-407125827522",
    },
    "615167489437": {
        "name": "INFO CLIENT ENVIRONMENT",
        "profile": "shubham-karale@infoclientenv-615167489437",
    },
}

# Explicitly supported lifecycle events.
# S3 remains handled by the existing S3 collector.
EVENTS = {
    "RunInstances": ("EC2", "create"),
    "TerminateInstances": ("EC2", "delete"),
    "CreateVolume": ("EBS", "create"),
    "DeleteVolume": ("EBS", "delete"),
    "CreateVpc": ("VPC", "create"),
    "DeleteVpc": ("VPC", "delete"),
    "CreateSubnet": ("SUBNET", "create"),
    "DeleteSubnet": ("SUBNET", "delete"),
    "CreateSecurityGroup": ("SECURITY_GROUP", "create"),
    "DeleteSecurityGroup": ("SECURITY_GROUP", "delete"),
    "CreateDBInstance": ("RDS", "create"),
    "DeleteDBInstance": ("RDS", "delete"),
    "CreateFunction20150331": ("LAMBDA", "create"),
    "DeleteFunction20150331": ("LAMBDA", "delete"),
}

def database_url():
    url = os.environ["DATABASE_URL"]
    return url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )

def human_identity(event):
    """Return a human identifier, or None for unverified actors."""
    identity = event.get("userIdentity") or {}
    identity_type = identity.get("type", "")
    arn = identity.get("arn", "")
    invoked_by = identity.get("invokedBy")

    if invoked_by or identity_type == "AWSService":
        return None

    if identity_type == "IAMUser":
        return identity.get("userName") or arn or None

    if identity_type == "AssumedRole":
        if ":assumed-role/" not in arn:
            return None

        parts = arn.split(":assumed-role/", 1)[1].split("/", 1)
        if len(parts) != 2:
            return None

        role_name, session_name = parts

        # AWS IAM Identity Center / SSO role.
        # Exclude all other roles unless attribution is added later.
        if not role_name.startswith("AWSReservedSSO_"):
            return None

        if not session_name or session_name.lower() in {
            "autoscaling", "unknown"
        }:
            return None

        return session_name

    return None

def nested(data, *keys):
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data

def extract_ids(event, event_name):
    request = event.get("requestParameters") or {}
    response = event.get("responseElements") or {}
    result = []

    if event_name == "RunInstances":
        items = nested(response, "instancesSet", "items") or []
        if isinstance(items, dict):
            items = [items]
        result = [
            item.get("instanceId")
            for item in items
            if isinstance(item, dict)
        ]

    elif event_name == "TerminateInstances":
        items = nested(request, "instancesSet", "items") or []
        if isinstance(items, dict):
            items = [items]
        result = [
            item.get("instanceId")
            for item in items
            if isinstance(item, dict)
        ]

    elif event_name == "CreateVolume":
        result = [response.get("volumeId")]

    elif event_name == "DeleteVolume":
        result = [request.get("volumeId")]

    elif event_name == "CreateVpc":
        result = [nested(response, "vpc", "vpcId")]

    elif event_name == "DeleteVpc":
        result = [request.get("vpcId")]

    elif event_name == "CreateSubnet":
        result = [nested(response, "subnet", "subnetId")]

    elif event_name == "DeleteSubnet":
        result = [request.get("subnetId")]

    elif event_name == "CreateSecurityGroup":
        result = [response.get("groupId")]

    elif event_name == "DeleteSecurityGroup":
        result = [request.get("groupId")]

    elif event_name == "CreateDBInstance":
        result = [
            nested(response, "dBInstance", "dBInstanceArn")
            or nested(response, "dBInstance", "dBInstanceIdentifier")
            or request.get("dBInstanceIdentifier")
        ]

    elif event_name == "DeleteDBInstance":
        result = [request.get("dBInstanceIdentifier")]

    elif event_name == "CreateFunction20150331":
        result = [
            response.get("functionArn")
            or response.get("functionName")
        ]

    elif event_name == "DeleteFunction20150331":
        function_name = request.get("functionName")

        if function_name:
            if function_name.startswith("arn:aws:lambda:"):
                result = [function_name]
            else:
                region = event.get("awsRegion")
                account_id = (
                    event.get("recipientAccountId")
                    or (event.get("userIdentity") or {}).get("accountId")
                )

                if region and account_id:
                    result = [
                        f"arn:aws:lambda:{region}:{account_id}:"
                        f"function:{function_name}"
                    ]

    return list(dict.fromkeys(
        value for value in result
        if isinstance(value, str) and value.strip()
    ))

def archive_event(account_id, region, event_id, event):
    folder = DATA_DIR / account_id / region / "human"
    folder.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", event_id)
    target = folder / f"{safe_id}.json"
    temp = folder / f"{safe_id}.tmp"

    temp.write_text(json.dumps(event, default=str, indent=2))
    temp.replace(target)

def save_event(conn, account_id, account_name, region,
               event_id, event_name, event_time,
               actor, resource_id, service, action, event):

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO cm_aws_accounts
                (account_id, account_name)
            VALUES (%s, %s)
            ON CONFLICT (account_id) DO NOTHING
        """, (account_id, account_name))

        cur.execute("""
            INSERT INTO cm_resource_events
                (account_id, event_id, resource_id,
                 service_code, region, event_name,
                 event_time, actor, actor_type,
                 event_source, event_json)
            VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (account_id, event_id, resource_id)
            DO NOTHING
        """, (
            account_id, event_id, resource_id,
            service, region, event_name, event_time,
            actor, "human",
            event.get("eventSource"),
            json.dumps(event, default=str),
        ))

        if action == "create":
            cur.execute("""
                INSERT INTO cm_aws_resources
                    (account_id, resource_id, service_code,
                     region, created_at, created_by,
                     created_by_type, resource_status,
                     last_event_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, 'human',
                     'created', %s)
                ON CONFLICT (account_id, resource_id)
                DO UPDATE SET
                    service_code = EXCLUDED.service_code,
                    region = EXCLUDED.region,
                    created_at = CASE
                        WHEN cm_aws_resources.created_at IS NULL
                          OR cm_aws_resources.resource_status = 'deleted'
                        THEN EXCLUDED.created_at
                        ELSE cm_aws_resources.created_at
                    END,
                    created_by = CASE
                        WHEN cm_aws_resources.created_at IS NULL
                          OR cm_aws_resources.resource_status = 'deleted'
                        THEN EXCLUDED.created_by
                        ELSE cm_aws_resources.created_by
                    END,
                    created_by_type = 'human',
                    resource_status = 'created',
                    last_event_at = EXCLUDED.last_event_at
                WHERE cm_aws_resources.last_event_at IS NULL
                   OR cm_aws_resources.last_event_at
                      <= EXCLUDED.last_event_at
            """, (
                account_id, resource_id, service,
                region, event_time, actor, event_time,
            ))

        elif action == "delete":
            # Preserve creation history.
            # Only update a resource that already exists.
            cur.execute("""
                UPDATE cm_aws_resources
                SET resource_status = 'deleted',
                    last_event_at = %s
                WHERE account_id = %s
                  AND resource_id = %s
                  AND (last_event_at IS NULL OR last_event_at <= %s)
            """, (
                event_time, account_id, resource_id, event_time
            ))

def checkpoint(conn, account_id, region, event_name):
    source = "human-" + event_name
    with conn.cursor() as cur:
        cur.execute("""
            SELECT checkpoint
            FROM cm_resource_collector_state
            WHERE account_id = %s
              AND region = %s
              AND source = %s
        """, (account_id, region, source))
        row = cur.fetchone()

    return row[0] if row else None

def update_checkpoint(conn, account_id, region, event_name, value):
    source = "human-" + event_name
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO cm_resource_collector_state
                (account_id, region, source, checkpoint, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (account_id, region, source)
            DO UPDATE SET
                checkpoint = EXCLUDED.checkpoint,
                updated_at = NOW()
        """, (account_id, region, source, value))
    conn.commit()

def collect_event(client, conn, account_id, account_name,
                  region, event_name, service, action):

    now = datetime.now(timezone.utc)
    last = checkpoint(conn, account_id, region, event_name)

    # First run: look back 7 days.
    # Later runs: overlap 10 minutes to avoid missed events.
    start = (
        max(last - timedelta(minutes=10),
            now - timedelta(days=89))
        if last else now - timedelta(days=7)
    )

    count = 0
    token = None

    while True:
        args = {
            "LookupAttributes": [{
                "AttributeKey": "EventName",
                "AttributeValue": event_name,
            }],
            "StartTime": start,
            "EndTime": now,
            "MaxResults": 50,
        }
        if token:
            args["NextToken"] = token

        response = client.lookup_events(**args)

        for summary in response.get("Events", []):
            event = json.loads(summary["CloudTrailEvent"])

            if event.get("errorCode"):
                continue

            if event.get("eventSource") != {
                "EC2": "ec2.amazonaws.com",
                "EBS": "ec2.amazonaws.com",
                "VPC": "ec2.amazonaws.com",
                "SUBNET": "ec2.amazonaws.com",
                "SECURITY_GROUP": "ec2.amazonaws.com",
                "RDS": "rds.amazonaws.com",
                "LAMBDA": "lambda.amazonaws.com",
            }[service]:
                continue

            actor = human_identity(event)
            if not actor:
                continue

            resource_ids = extract_ids(event, event_name)
            if not resource_ids:
                log.warning(
                    "No resource ID: account=%s event=%s id=%s",
                    account_id, event_name, summary["EventId"]
                )
                continue

            event_time = summary["EventTime"]
            event_id = summary["EventId"]

            archive_event(account_id, region, event_id, event)

            for resource_id in resource_ids:
                with conn.transaction():
                    save_event(
                        conn, account_id, account_name,
                        region, event_id, event_name,
                        event_time, actor, resource_id,
                        service, action, event
                    )
                count += 1

        token = response.get("NextToken")
        if not token:
            break

        # CloudTrail LookupEvents is throttled per account/region.
        time.sleep(0.6)

    update_checkpoint(conn, account_id, region, event_name, now)
    return count

def run_once():
    with psycopg.connect(database_url(), autocommit=True) as conn:
        for account_id, config in ACCOUNTS.items():
            try:
                session = boto3.Session(
                    profile_name=config["profile"]
                )

                actual = session.client(
                    "sts"
                ).get_caller_identity()["Account"]

                if actual != account_id:
                    log.error(
                        "Account mismatch: expected=%s actual=%s",
                        account_id, actual
                    )
                    continue

            except Exception:
                log.exception("AWS authentication failed: %s", account_id)
                continue

            for region in REGIONS:
                client = session.client(
                    "cloudtrail",
                    region_name=region,
                    config=__import__(
                        "botocore.config", fromlist=["Config"]
                    ).Config(
                        retries={
                            "mode": "adaptive",
                            "max_attempts": 10
                        }
                    )
                )

                for event_name, (service, action) in EVENTS.items():
                    try:
                        count = collect_event(
                            client, conn,
                            account_id, config["name"],
                            region, event_name, service, action
                        )
                        log.info(
                            "Account=%s Region=%s Event=%s "
                            "Resources=%s",
                            account_id, region, event_name, count
                        )
                    except Exception:
                        log.exception(
                            "Collection failed account=%s "
                            "region=%s event=%s",
                            account_id, region, event_name
                        )

                    time.sleep(0.6)

def main():
    while True:
        started = time.monotonic()
        try:
            run_once()
        except Exception:
            log.exception("Collector cycle failed")

        elapsed = time.monotonic() - started
        wait = max(0, INTERVAL - elapsed)
        log.info("Cycle finished in %.1fs; next check in %.1fs",
                 elapsed, wait)
        time.sleep(wait)

if __name__ == "__main__":
    main()

