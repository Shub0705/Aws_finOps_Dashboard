
import json
import os
from datetime import datetime, timedelta, timezone, date

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.routes.resource_tracking import router as resource_tracking_router
app = FastAPI(
    title="CloudPilot AWS FinOps API",
    version="1.0.0"
)
app.include_router(resource_tracking_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Only accounts explicitly selected for monitoring.
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


def get_account(account_id):
    account = ACCOUNTS.get(account_id)

    if not account:
        raise HTTPException(
            status_code=404,
            detail="Account is not configured for monitoring"
        )

    return account


def get_session(account_id):
    account = get_account(account_id)

    return boto3.Session(
        profile_name=account["profile"],
        region_name=AWS_REGION
    )


@app.get("/")
def root():
    return {
        "application": "CloudPilot AWS FinOps API",
        "status": "running"
    }


@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/accounts")
def get_accounts():

    results = []

    for account_id, account in ACCOUNTS.items():

        try:
            session = get_session(account_id)

            identity = session.client("sts").get_caller_identity()

            results.append({
                "account_id": account_id,
                "account_name": account["name"],
                "authenticated": identity["Account"] == account_id,
                "status": (
                    "connected"
                    if identity["Account"] == account_id
                    else "account_mismatch"
                ),
            })

        except (ClientError, BotoCoreError) as error:
            results.append({
                "account_id": account_id,
                "account_name": account["name"],
                "authenticated": False,
                "status": "authentication_error",
                "error": str(error),
            })

    return {"accounts": results}

@app.get("/api/costs/services/{account_id}")
def get_service_costs(account_id: str):
    account = get_account(account_id)
    session = get_session(account_id)

    # Cost Explorer date boundaries are date-only.
    today = datetime.now(timezone.utc).date()
    start_date = today.replace(day=1)
    end_date = today + timedelta(days=1)

    try:
        client = session.client("ce", region_name="us-east-1")

        response = client.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.isoformat(),
                "End": end_date.isoformat(),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[
                {
                    "Type": "DIMENSION",
                    "Key": "SERVICE",
                }
            ],
        )

        monthly_services = {}
        daily_costs = []
        monthly_total = 0.0
        daily_total = 0.0
        estimated = False

        for period in response.get("ResultsByTime", []):
            day = period["TimePeriod"]["Start"]
            day_total = 0.0

            for group in period.get("Groups", []):
                service = group["Keys"][0]
                metric = group["Metrics"]["UnblendedCost"]

                amount = float(metric["Amount"])
                currency = metric["Unit"]

                day_total += amount
                monthly_services[service] = (
                    monthly_services.get(service, 0.0) + amount
                )

            monthly_total += day_total

            if day == today.isoformat():
                daily_total = day_total

            daily_costs.append({
                "date": day,
                "amount": round(day_total, 4),
            })

            estimated = estimated or period.get("Estimated", False)

        services = [
            {
                "service": service,
                "amount": round(amount, 4),
                "currency": "USD",
            }
            for service, amount in monthly_services.items()
        ]

        services.sort(
            key=lambda item: item["amount"],
            reverse=True,
        )

        return {
            "account_id": account_id,
            "account_name": account["name"],
            "currency": "USD",
            "period": {
                "start": start_date.isoformat(),
                "end_exclusive": end_date.isoformat(),
                "today": today.isoformat(),
            },
            "daily_total": round(daily_total, 4),
            "total": round(monthly_total, 4),
            "daily_costs": daily_costs,
            "services": services,
            "estimated": estimated,
        }

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")

        if code in ("AccessDenied", "AccessDeniedException"):
            raise HTTPException(
                status_code=403,
                detail="Cost Explorer permission is missing for this account",
            )

        raise HTTPException(
            status_code=502,
            detail="AWS Cost Explorer request failed",
        )

    except BotoCoreError:
        raise HTTPException(
            status_code=502,
            detail="AWS Cost Explorer request failed",
        )


def _collect_inventory_pages(client, operation, result_key, **kwargs):
    """Collect every page from an AWS list/describe operation."""
    items = []
    token = None

    while True:
        request = dict(kwargs)
        if token:
            request["NextToken"] = token

        response = getattr(client, operation)(**request)
        items.extend(response.get(result_key, []))

        token = response.get("NextToken")
        if not token:
            break

    return items


@app.get("/api/inventory/{account_id}")
def get_infrastructure_inventory(account_id: str):
    account = get_account(account_id)

    try:
        session = get_session(account_id)
        ec2 = session.client("ec2", region_name=AWS_REGION)
        eks = session.client("eks", region_name=AWS_REGION)
        rds = session.client("rds", region_name=AWS_REGION)

    except (ClientError, BotoCoreError):
        raise HTTPException(
            status_code=502,
            detail="Unable to initialize AWS inventory session"
        )

    result = {
        "account_id": account_id,
        "account_name": account["name"],
        "region": AWS_REGION,
        "eks": {
            "count": None,
            "clusters": [],
            "status": "pending"
        },
        "vpcs": {
            "count": None,
            "status": "pending"
        },
        "rds": {
            "count": None,
            "instances": [],
            "status": "pending"
        },
        "volumes": {
            "count": None,
            "status": "pending",
            "scope": "all_states"
        },
        "kubernetes": {
            "nodes": None,
            "pods": None,
            "status": "not_configured",
            "message": "Kubernetes API access is not configured"
        },
        "errors": []
    }

    # EKS clusters and names.
    try:
        clusters = _collect_inventory_pages(
            eks, "list_clusters", "clusters"
        )
        result["eks"] = {
            "count": len(clusters),
            "clusters": clusters,
            "status": "ok"
        }
    except (ClientError, BotoCoreError):
        result["eks"]["status"] = "access_denied_or_error"
        result["errors"].append("EKS inventory unavailable")

    # VPC count.
    try:
        vpcs = _collect_inventory_pages(
            ec2, "describe_vpcs", "Vpcs"
        )
        result["vpcs"] = {
            "count": len(vpcs),
            "status": "ok"
        }
    except (ClientError, BotoCoreError):
        result["vpcs"]["status"] = "access_denied_or_error"
        result["errors"].append("VPC inventory unavailable")

    # RDS DB instance count.
    try:
        databases = _collect_inventory_pages(
            rds, "describe_db_instances", "DBInstances"
        )
        result["rds"] = {
            "count": len(databases),
            "instances": [
                {
                    "identifier": db.get("DBInstanceIdentifier"),
                    "engine": db.get("Engine"),
                    "status": db.get("DBInstanceStatus"),
                    "class": db.get("DBInstanceClass")
                }
                for db in databases
            ],
            "status": "ok"
        }
    except (ClientError, BotoCoreError):
        result["rds"]["status"] = "access_denied_or_error"
        result["errors"].append("RDS inventory unavailable")

    # EBS volume count, including all volume states.
    try:
        volumes = _collect_inventory_pages(
            ec2, "describe_volumes", "Volumes"
        )
        result["volumes"] = {
            "count": len(volumes),
            "status": "ok",
            "scope": "all_states"
        }
    except (ClientError, BotoCoreError):
        result["volumes"]["status"] = "access_denied_or_error"
        result["errors"].append("EBS volume inventory unavailable")

    return result


def classify_identity(identity):
    """Classify CloudTrail identity conservatively."""
    identity_type = identity.get("type", "")
    arn = identity.get("arn", "")
    principal_id = identity.get("principalId", "")

    session_context = identity.get("sessionContext", {})
    if not isinstance(session_context, dict):
        session_context = {}

    issuer = session_context.get("sessionIssuer", {})
    if not isinstance(issuer, dict):
        issuer = {}

    if identity_type == "IAMUser":
        actor = identity.get("userName") or "Unknown IAM user"
        return {
            "actor": actor,
            "actor_type": "human_iam",
            "identity_id": arn or principal_id or None,
            "identity_verified": False,
        }

    if identity_type == "Root":
        return {
            "actor": "AWS Account Root",
            "actor_type": "root_identity",
            "identity_id": arn or principal_id or None,
            "identity_verified": bool(arn or principal_id),
        }

    # Identity Center assumed-role sessions must have both the
    # reserved SSO role pattern and Identity Center user context.
    if ":assumed-role/" in arn and "AWSReservedSSO_" in arn:
        on_behalf_of = identity.get("onBehalfOf", {})
        if not isinstance(on_behalf_of, dict):
            on_behalf_of = {}

        user_id = on_behalf_of.get("userId")
        identity_store_arn = on_behalf_of.get("identityStoreArn")

        role_session = arn.split(":assumed-role/", 1)[1]
        role_parts = role_session.split("/", 1)
        session_name = role_parts[1] if len(role_parts) == 2 else ""

        if user_id and identity_store_arn and session_name:
            return {
                "actor": session_name,
                "actor_type": "human_sso",
                "identity_id": f"identitycenter:{user_id}",
                "identity_verified": True,
            }

    # Assumed roles, AWS services, federated identities without
    # verifiable Identity Center context, and unknown principals
    # are not counted as human employees.
    actor = (
        issuer.get("userName")
        or identity.get("userName")
        or "Unknown role or service"
    )

    return {
        "actor": actor,
        "actor_type": "service_or_role",
        "identity_id": arn or principal_id or None,
        "identity_verified": False,
    }


@app.get("/api/activity/recent/{account_id}")
def get_recent_activity(
    account_id: str,
    hours: int = Query(default=24, ge=1, le=168),
):
    account = get_account(account_id)
    session = get_session(account_id)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    max_pages = 5
    page_size = 50
    events = []
    next_token = None
    pages_fetched = 0

    try:
        client = session.client(
            "cloudtrail",
            region_name=AWS_REGION,
        )

        while pages_fetched < max_pages:
            request = {
                "StartTime": start_time,
                "EndTime": end_time,
                "MaxResults": page_size,
            }

            if next_token:
                request["NextToken"] = next_token

            response = client.lookup_events(**request)
            pages_fetched += 1

            for item in response.get("Events", []):
                try:
                    detail = json.loads(
                        item.get("CloudTrailEvent", "{}")
                    )
                    if not isinstance(detail, dict):
                        detail = {}
                except (ValueError, TypeError):
                    detail = {}

                identity = detail.get("userIdentity", {})
                if not isinstance(identity, dict):
                    identity = {}

                classification = classify_identity(identity)

                events.append({
                    "event_id": item.get("EventId"),
                    "event_name": item.get("EventName"),
                    "event_source": item.get("EventSource"),
                    "event_time": item.get("EventTime"),
                    "actor": classification["actor"],
                    "actor_type": classification["actor_type"],
                    "identity_id": classification["identity_id"],
                    "identity_verified": classification["identity_verified"],
                    "account_id": account_id,
                    "region": detail.get("awsRegion"),
                    "read_only": detail.get("readOnly"),
                })

            next_token = response.get("NextToken")
            if not next_token:
                break

        human_events = [
            event for event in events
            if event["actor_type"] == "human_sso"
            and event["identity_verified"] is True
        ]

        unique_human_ids = {
            event["identity_id"]
            for event in human_events
            if event["identity_id"]
        }

        has_more = bool(next_token)

        return {
            "account_id": account_id,
            "account_name": account["name"],
            "window_hours": hours,
            "events": events,
            "pages_fetched": pages_fetched,
            "has_more": has_more,
            "truncated": has_more,
            "next_token_available": has_more,
            "human_event_count": len(human_events),
            "unique_human_identity_count": len(unique_human_ids),
        }

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")

        if code in ("AccessDenied", "AccessDeniedException"):
            raise HTTPException(
                status_code=403,
                detail="CloudTrail access is denied for this account",
            )

        raise HTTPException(
            status_code=502,
            detail="AWS CloudTrail request failed",
        )

    except BotoCoreError:
        raise HTTPException(
            status_code=502,
            detail="AWS CloudTrail request failed",
        )
