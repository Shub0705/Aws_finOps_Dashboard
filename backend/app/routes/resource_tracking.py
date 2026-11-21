from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cost_management.database import get_db

router = APIRouter(
    prefix="/api/resource-tracking",
    tags=["Resource Tracking"]
)


@router.get("/resources")
def get_resources(
    account_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT
                r.id,
                r.account_id,
                a.account_name AS account_name,
                r.resource_id,
                r.resource_name,
                r.service_code,
                r.region,
                r.created_at,
                r.created_by,
                r.created_by_type,
                r.resource_status,
                r.last_event_at
            FROM cm_aws_resources r
            LEFT JOIN cm_aws_accounts a
                ON a.account_id = r.account_id
            WHERE (CAST(:account_id AS VARCHAR) IS NULL OR r.account_id = :account_id)
              AND r.created_by_type = 'human'
            ORDER BY r.created_at DESC NULLS LAST, r.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            "account_id": account_id,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return {
        "success": True,
        "resources": [dict(row) for row in rows],
    }


@router.get("/events")
def get_events(
    account_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT
                account_id,
                resource_id,
                service_code,
                region,
                event_name,
                event_time,
                actor,
                actor_type
            FROM cm_resource_events
            WHERE (CAST(:account_id AS VARCHAR) IS NULL OR account_id = :account_id)
            ORDER BY event_time DESC
            LIMIT :limit
        """),
        {"account_id": account_id, "limit": limit},
    ).mappings().all()

    return {
        "success": True,
        "events": [dict(row) for row in rows],
    }


@router.get("/monthly-costs")
def get_monthly_costs(
    account_id: str | None = None,
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT
                account_id,
                resource_id,
                billing_month,
                cost_type,
                amount,
                currency,
                source
            FROM cm_resource_monthly_costs
            WHERE (CAST(:account_id AS VARCHAR) IS NULL OR account_id = :account_id)
            ORDER BY billing_month DESC, resource_id
            LIMIT 500
        """),
        {"account_id": account_id},
    ).mappings().all()

    return {
        "success": True,
        "monthly_costs": [dict(row) for row in rows],
    }
