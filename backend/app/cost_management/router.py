from datetime import date, datetime, time, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from .database import get_db
from .models import DailyCostStatus, EstimatedCost, UsageRecord, Employee

router = APIRouter(prefix="/api/cost-management", tags=["Cost Management"])

@router.get("/health")
def health():
    return {"module": "cost-management", "status": "ready"}

@router.get("/daily-summary")
def daily_summary(billing_date: date = Query(...), account_id: str | None = None,
                  db: Session = Depends(get_db)):
    start = datetime.combine(billing_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(billing_date, time.max, tzinfo=timezone.utc)
    q = (db.query(func.sum(EstimatedCost.amount), EstimatedCost.currency)
         .join(UsageRecord, UsageRecord.id == EstimatedCost.usage_record_id)
         .filter(UsageRecord.period_start >= start, UsageRecord.period_start <= end)
         .group_by(EstimatedCost.currency))
    if account_id:
        q = q.filter(UsageRecord.account_id == account_id)
    totals = [{"estimated_total": str(amount or 0), "currency": currency}
              for amount, currency in q.all()]
    sq = db.query(DailyCostStatus).filter(DailyCostStatus.billing_date == start)
    if account_id:
        sq = sq.filter(DailyCostStatus.account_id == account_id)
    statuses = [{"account_id": x.account_id, "status": x.status,
                 "last_reconciled_at": x.last_reconciled_at,
                 "finalized_at": x.finalized_at} for x in sq.all()]
    return {"billing_date": billing_date.isoformat(), "estimated_totals": totals,
            "verification": statuses,
            "note": "Actual billing comparison is unavailable until CUR ingestion is implemented."}

@router.get("/employees")
def employee_costs(billing_date: date = Query(...), db: Session = Depends(get_db)):
    start = datetime.combine(billing_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(billing_date, time.max, tzinfo=timezone.utc)
    rows = (db.query(Employee.id, Employee.email, Employee.display_name,
                     func.sum(EstimatedCost.amount), EstimatedCost.currency)
            .join(UsageRecord, UsageRecord.employee_id == Employee.id)
            .join(EstimatedCost, EstimatedCost.usage_record_id == UsageRecord.id)
            .filter(UsageRecord.period_start >= start, UsageRecord.period_start <= end)
            .group_by(Employee.id, Employee.email, Employee.display_name, EstimatedCost.currency)
            .order_by(func.sum(EstimatedCost.amount).desc()).all())
    return {"billing_date": billing_date.isoformat(), "employees": [
        {"employee_id": i, "email": email, "display_name": name,
         "estimated_cost": str(amount or 0), "currency": currency}
        for i, email, name, amount, currency in rows
    ]}

@router.post("/daily-status/{account_id}/{billing_date}/finalize")
def finalize(account_id: str, billing_date: date,
             approved_by: str = Query(..., min_length=3, max_length=255),
             db: Session = Depends(get_db)):
    start = datetime.combine(billing_date, time.min, tzinfo=timezone.utc)
    row = (db.query(DailyCostStatus)
           .filter(DailyCostStatus.account_id == account_id,
                   DailyCostStatus.billing_date == start)
           .with_for_update().first())
    if row is None:
        raise HTTPException(404, "Daily cost status not found")
    if row.status != "verified":
        raise HTTPException(409, "Only verified reports can be finalized")
    row.status = "finalized"
    row.finalized_at = datetime.now(timezone.utc)
    row.finalized_by = approved_by
    db.commit()
    return {"account_id": account_id, "billing_date": billing_date.isoformat(),
            "status": row.status, "finalized_at": row.finalized_at,
            "finalized_by": row.finalized_by}
