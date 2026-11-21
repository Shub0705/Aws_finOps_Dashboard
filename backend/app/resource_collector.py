import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from psycopg.types.json import Jsonb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("cloudpilot-collector")

ACCOUNTS = {
    "407125827522": (
        "INFO NON PROD",
        "shubham-karale@infononprod-407125827522",
    ),
    "615167489437": (
        "INFO CLIENT ENVIRONMENT",
        "shubham-karale@infoclientenv-615167489437",
    ),
}

DATABASE_URL = os.environ["DATABASE_URL"]

# SQLAlchemy URLs use postgresql+psycopg://
# psycopg.connect() requires postgresql://
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql+psycopg://",
        "postgresql://",
        1,
    )

DATA_DIR = Path(os.getenv("CLOUDTRAIL_DATA_DIR", "/app/cloudtrail-data"))
REGIONS = [
    region.strip()
    for region in os.getenv("CLOUDTRAIL_REGIONS", "us-east-1").split(",")
    if region.strip()
]
INTERVAL = int(os.getenv("COLLECT_INTERVAL_SECONDS", "300"))
SOURCE = "s3-buckets"

EVENTS = {
    "CreateBucket": "created",
    "DeleteBucket": "deleted",
}


def get_checkpoint(conn, account_id, region):
    row = conn.execute(
        """
        SELECT checkpoint
        FROM cm_resource_collector_state
        WHERE account_id = %s
          AND region = %s
          AND source = %s
        """,
        (account_id, region, SOURCE),
    ).fetchone()

    return row[0] if row else None


def save_checkpoint(conn, account_id, region, checkpoint):
    with conn.transaction():
        conn.execute(
            """
            INSERT INTO cm_resource_collector_state
                (account_id, region, source, checkpoint)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (account_id, region, source)
            DO UPDATE SET
                checkpoint = GREATEST(
                    cm_resource_collector_state.checkpoint,
                    EXCLUDED.checkpoint
                ),
                updated_at = NOW()
            """,
            (account_id, region, SOURCE, checkpoint),
        )


def bucket_name_from_event(record):
    params = record.get("requestParameters") or {}
    name = params.get("bucketName")

    if name:
        return name

    for resource in record.get("resources") or []:
        arn = resource.get("ARN", "")
        if arn.startswith("arn:aws:s3:::"):
            return arn.split(":::", 1)[1].split("/", 1)[0]

    return None


def actor_from_event(record):
    identity = record.get("userIdentity") or {}
    context = identity.get("sessionContext") or {}

    if identity.get("invokedBy"):
        return None

    identity_type = identity.get("type")
    arn = identity.get("arn") or ""

    if identity_type == "IAMUser":
        return identity.get("userName") or arn or None

    if identity_type == "AssumedRole":
        if ":assumed-role/" not in arn:
            return None

        role_and_session = arn.split(":assumed-role/", 1)[1]
        parts = role_and_session.split("/", 1)

        if len(parts) != 2:
            return None

        role_name, session_name = parts

        if not role_name.startswith("AWSReservedSSO_"):
            return None

        if not session_name or session_name.lower() in {
            "autoscaling", "unknown"
        }:
            return None

        return session_name

    return None


def save_raw_event(account_id, region, event_id, record):
    event_time = record.get("eventTime", "unknown")
    day = event_time[:10] if isinstance(event_time, str) else "unknown"

    folder = DATA_DIR / account_id / region / day
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Event IDs are UUIDs from CloudTrail.
    safe_id = "".join(
        char for char in event_id
        if char.isalnum() or char in "-_"
    )

    target = folder / f"{safe_id}.json"

    if target.exists():
        return

    fd, temporary = tempfile.mkstemp(dir=folder, prefix=".event-")

    try:
        with os.fdopen(fd, "w") as file:
            json.dump(record, file, indent=2)
            file.flush()
            os.fsync(file.fileno())

        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def process_event(conn, account_id, account_name, region, event):
    raw = event.get("CloudTrailEvent")

    if not raw:
        return False

    record = json.loads(raw)

    # Failed AWS API requests must not create resource records.
    if record.get("errorCode") or record.get("errorMessage"):
        return False

    event_name = record.get("eventName")
    if event_name not in EVENTS:
        return False

    bucket = bucket_name_from_event(record)
    if not bucket:
        log.warning("Bucket name unavailable for event %s", event.get("EventId"))
        return False

    event_id = record.get("eventID") or event.get("EventId")
    event_time = event.get("EventTime")

    if not event_id or not event_time:
        return False

    actor = actor_from_event(record)

    # Only record verified human actions.
    if not actor:
        return False

    actor_type = "human"
    event_region = record.get("awsRegion") or region
    status = EVENTS[event_name]

    # Persist raw event locally before recording it in PostgreSQL.
    save_raw_event(account_id, region, event_id, record)

    with conn.transaction():
        conn.execute(
            """
            INSERT INTO cm_aws_accounts
                (account_id, account_name)
            VALUES (%s, %s)
            ON CONFLICT (account_id) DO NOTHING
            """,
            (account_id, account_name),
        )

        conn.execute(
            """
            INSERT INTO cm_resource_events (
                account_id, event_id, resource_id,
                service_code, region, event_name,
                event_time, actor, actor_type,
                event_source, event_json
            )
            VALUES (
                %s, %s, %s, 'S3', %s, %s,
                %s, %s, %s, 's3.amazonaws.com', %s
            )
            ON CONFLICT (account_id, event_id, resource_id)
            DO NOTHING
            """,
            (
                account_id, event_id, bucket,
                event_region, event_name, event_time,
                actor, actor_type, Jsonb(record),
            ),
        )

        conn.execute(
            """
            INSERT INTO cm_aws_resources (
                account_id, resource_id, service_code,
                region, resource_name, created_at,
                created_by, created_by_type,
                resource_status, last_event_at
            )
            VALUES (
                %s, %s, 'S3', %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (account_id, resource_id)
            DO UPDATE SET
                resource_name = EXCLUDED.resource_name,
                created_at = CASE
                    WHEN EXCLUDED.created_at IS NULL
                    THEN cm_aws_resources.created_at
                    WHEN cm_aws_resources.created_at IS NULL
                    THEN EXCLUDED.created_at
                    ELSE LEAST(
                        cm_aws_resources.created_at,
                        EXCLUDED.created_at
                    )
                END,
                created_by = CASE
                    WHEN cm_aws_resources.created_at IS NULL
                      OR (
                          EXCLUDED.created_at IS NOT NULL
                          AND EXCLUDED.created_at
                              < cm_aws_resources.created_at
                      )
                    THEN EXCLUDED.created_by
                    ELSE cm_aws_resources.created_by
                END,
                created_by_type = CASE
                    WHEN cm_aws_resources.created_at IS NULL
                      OR (
                          EXCLUDED.created_at IS NOT NULL
                          AND EXCLUDED.created_at
                              < cm_aws_resources.created_at
                      )
                    THEN EXCLUDED.created_by_type
                    ELSE cm_aws_resources.created_by_type
                END,
                resource_status = CASE
                    WHEN EXCLUDED.last_event_at >=
                        COALESCE(
                            cm_aws_resources.last_event_at,
                            '-infinity'::timestamptz
                        )
                    THEN EXCLUDED.resource_status
                    ELSE cm_aws_resources.resource_status
                END,
                last_event_at = GREATEST(
                    cm_aws_resources.last_event_at,
                    EXCLUDED.last_event_at
                )
            """,
            (
                account_id,
                bucket,
                event_region,
                bucket,
                event_time if event_name == "CreateBucket" else None,
                actor if event_name == "CreateBucket" else None,
                actor_type if event_name == "CreateBucket" else None,
                status,
                event_time,
            ),
        )

    return True


def collect_account_region(account_id, account_name, profile, region):
    session = boto3.Session(
        profile_name=profile,
        region_name=region,
    )

    # Confirm the profile is connected to the intended account.
    identity = session.client("sts").get_caller_identity()

    if identity["Account"] != account_id:
        raise RuntimeError(
            f"Account mismatch: expected {account_id}, "
            f"received {identity['Account']}"
        )

    client = session.client("cloudtrail")

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        checkpoint = get_checkpoint(conn, account_id, region)

        end_time = datetime.now(timezone.utc)

        if checkpoint:
            # Replay the previous 24 hours to tolerate delayed events.
            start_time = max(
                checkpoint - timedelta(hours=24),
                end_time - timedelta(days=89),
            )
        else:
            # Initial historical backfill.
            start_time = end_time - timedelta(days=89)

        total = 0

        for event_name in EVENTS:
            paginator = client.get_paginator("lookup_events")

            pages = paginator.paginate(
                LookupAttributes=[
                    {
                        "AttributeKey": "EventName",
                        "AttributeValue": event_name,
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                PaginationConfig={"PageSize": 50},
            )

            events = []

            for page in pages:
                events.extend(page.get("Events", []))

            # Apply events chronologically so newer lifecycle
            # operations determine the latest known status.
            events.sort(key=lambda item: item["EventTime"])

            for event in events:
                if process_event(
                    conn, account_id, account_name, region, event
                ):
                    total += 1

        # Advance only after both event types were processed.
        save_checkpoint(conn, account_id, region, end_time)

        log.info(
            "Account=%s Region=%s Events processed=%s",
            account_id, region, total,
        )


def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

    while True:
        for account_id, (account_name, profile) in ACCOUNTS.items():
            for region in REGIONS:
                try:
                    collect_account_region(
                        account_id, account_name, profile, region
                    )
                except Exception:
                    log.exception(
                        "Collection failed: account=%s region=%s",
                        account_id, region,
                    )

        time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
