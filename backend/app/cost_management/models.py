from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def now_utc():
    return datetime.now(timezone.utc)

class AwsAccount(Base):
    __tablename__ = "cm_aws_accounts"
    account_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Employee(Base):
    __tablename__ = "cm_employees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identity_center_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class AwsResource(Base):
    __tablename__ = "cm_aws_resources"
    __table_args__ = (UniqueConstraint("account_id", "resource_id", name="uq_cm_resource"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("cm_aws_accounts.account_id"), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    service_code: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100))
    owner_employee_id: Mapped[int | None] = mapped_column(ForeignKey("cm_employees.id"))
    allocation_method: Mapped[str] = mapped_column(String(40), default="unallocated", nullable=False)
    tags_json: Mapped[str | None] = mapped_column(Text)

class PricingProduct(Base):
    __tablename__ = "cm_pricing_products"
    __table_args__ = (UniqueConstraint("provider", "sku", name="uq_cm_pricing_sku"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="aws_price_list")
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    service_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    region: Mapped[str | None] = mapped_column(String(100))
    attributes_json: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class PricingRate(Base):
    __tablename__ = "cm_pricing_rates"
    __table_args__ = (
        UniqueConstraint("product_id", "rate_code", "effective_from", name="uq_cm_rate_version"),
        Index("ix_cm_rate_lookup", "product_id", "effective_from", "effective_to"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("cm_pricing_products.id"), nullable=False)
    rate_code: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    price_per_unit: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_version: Mapped[str | None] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class UsageBatch(Base):
    __tablename__ = "cm_usage_batches"
    __table_args__ = (UniqueConstraint("account_id", "window_start", "window_end", name="uq_cm_usage_window"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("cm_aws_accounts.account_id"), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

class UsageRecord(Base):
    __tablename__ = "cm_usage_records"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_cm_usage_source"),
        Index("ix_cm_usage_period", "account_id", "period_start", "period_end"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("cm_usage_batches.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("cm_aws_accounts.account_id"), nullable=False)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("cm_employees.id"))
    resource_id: Mapped[str | None] = mapped_column(String(1024))
    service_code: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_type: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    attribution_status: Mapped[str] = mapped_column(String(30), default="unallocated")

class EstimatedCost(Base):
    __tablename__ = "cm_estimated_costs"
    __table_args__ = (UniqueConstraint("usage_record_id", "pricing_rate_id", name="uq_cm_estimate"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usage_record_id: Mapped[int] = mapped_column(ForeignKey("cm_usage_records.id"), nullable=False)
    pricing_rate_id: Mapped[int] = mapped_column(ForeignKey("cm_pricing_rates.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(40), default="v1")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class BillingImport(Base):
    __tablename__ = "cm_billing_imports"
    __table_args__ = (UniqueConstraint("account_id", "s3_key", "s3_version_id", name="uq_cm_billing_object"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("cm_aws_accounts.account_id"), nullable=False)
    billing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    s3_version_id: Mapped[str] = mapped_column(String(255), default="")
    manifest_status: Mapped[str] = mapped_column(String(30), default="pending")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ActualCost(Base):
    __tablename__ = "cm_actual_costs"
    __table_args__ = (UniqueConstraint("account_id", "source_line_item_key", name="uq_cm_actual_line"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    billing_import_id: Mapped[int] = mapped_column(ForeignKey("cm_billing_imports.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("cm_aws_accounts.account_id"), nullable=False)
    billing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("cm_employees.id"))
    resource_id: Mapped[str | None] = mapped_column(String(1024))
    service_code: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    line_item_type: Mapped[str | None] = mapped_column(String(100))
    source_line_item_key: Mapped[str] = mapped_column(String(512), nullable=False)

class ReconciliationRun(Base):
    __tablename__ = "cm_reconciliation_runs"
    __table_args__ = (UniqueConstraint("account_id", "billing_date", "attempt", name="uq_cm_recon_attempt"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("cm_aws_accounts.account_id"), nullable=False)
    billing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    source_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    mismatch_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

class ReconciliationItem(Base):
    __tablename__ = "cm_reconciliation_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("cm_reconciliation_runs.id"), nullable=False)
    estimated_cost_id: Mapped[int | None] = mapped_column(ForeignKey("cm_estimated_costs.id"))
    actual_cost_id: Mapped[int | None] = mapped_column(ForeignKey("cm_actual_costs.id"))
    estimated_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    difference: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

class DailyCostStatus(Base):
    __tablename__ = "cm_daily_cost_status"
    __table_args__ = (UniqueConstraint("account_id", "billing_date", name="uq_cm_daily_status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("cm_aws_accounts.account_id"), nullable=False)
    billing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[str | None] = mapped_column(String(255))
    report_s3_key: Mapped[str | None] = mapped_column(String(1024))
