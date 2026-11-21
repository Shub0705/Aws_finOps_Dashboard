-- Additive Cost Management schema. Does not modify existing CloudPilot tables.
CREATE TABLE IF NOT EXISTS cm_aws_accounts (
 account_id VARCHAR(12) PRIMARY KEY, account_name VARCHAR(200) NOT NULL,
 enabled BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cm_employees (
 id BIGSERIAL PRIMARY KEY, identity_center_user_id VARCHAR(255) NOT NULL UNIQUE,
 email VARCHAR(320) NOT NULL, display_name VARCHAR(255),
 enabled BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cm_employees_email ON cm_employees(email);
CREATE TABLE IF NOT EXISTS cm_aws_resources (
 id BIGSERIAL PRIMARY KEY, account_id VARCHAR(12) NOT NULL REFERENCES cm_aws_accounts(account_id),
 resource_id VARCHAR(1024) NOT NULL, service_code VARCHAR(100) NOT NULL, region VARCHAR(100),
 owner_employee_id BIGINT REFERENCES cm_employees(id), allocation_method VARCHAR(40) NOT NULL DEFAULT 'unallocated',
 tags_json TEXT, CONSTRAINT uq_cm_resource UNIQUE(account_id, resource_id)
);
CREATE TABLE IF NOT EXISTS cm_pricing_products (
 id BIGSERIAL PRIMARY KEY, provider VARCHAR(40) NOT NULL DEFAULT 'aws_price_list',
 sku VARCHAR(128) NOT NULL, service_code VARCHAR(100) NOT NULL, region VARCHAR(100),
 attributes_json TEXT, imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT uq_cm_pricing_sku UNIQUE(provider, sku)
);
CREATE INDEX IF NOT EXISTS ix_cm_pricing_service ON cm_pricing_products(service_code);
CREATE TABLE IF NOT EXISTS cm_pricing_rates (
 id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL REFERENCES cm_pricing_products(id),
 rate_code VARCHAR(255) NOT NULL, unit VARCHAR(80) NOT NULL, currency VARCHAR(8) NOT NULL,
 price_per_unit NUMERIC(24,12) NOT NULL, effective_from TIMESTAMPTZ NOT NULL,
 effective_to TIMESTAMPTZ, source_version VARCHAR(255), imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT uq_cm_rate_version UNIQUE(product_id, rate_code, effective_from)
);
CREATE INDEX IF NOT EXISTS ix_cm_rate_lookup ON cm_pricing_rates(product_id,effective_from,effective_to);
CREATE TABLE IF NOT EXISTS cm_usage_batches (
 id BIGSERIAL PRIMARY KEY, account_id VARCHAR(12) NOT NULL REFERENCES cm_aws_accounts(account_id),
 window_start TIMESTAMPTZ NOT NULL, window_end TIMESTAMPTZ NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'pending',
 started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, error_message TEXT,
 CONSTRAINT uq_cm_usage_window UNIQUE(account_id,window_start,window_end)
);
CREATE TABLE IF NOT EXISTS cm_identity_mappings (
 id BIGSERIAL PRIMARY KEY, identity_id VARCHAR(512) NOT NULL, employee_id BIGINT NOT NULL REFERENCES cm_employees(id),
 valid_from TIMESTAMPTZ NOT NULL, valid_to TIMESTAMPTZ, source VARCHAR(50) NOT NULL DEFAULT 'identity_center',
 CONSTRAINT uq_cm_identity_valid_from UNIQUE(identity_id,valid_from)
);
CREATE TABLE IF NOT EXISTS cm_usage_records (
 id BIGSERIAL PRIMARY KEY, batch_id BIGINT NOT NULL REFERENCES cm_usage_batches(id),
 account_id VARCHAR(12) NOT NULL REFERENCES cm_aws_accounts(account_id), employee_id BIGINT REFERENCES cm_employees(id),
 resource_id VARCHAR(1024), service_code VARCHAR(100) NOT NULL, usage_type VARCHAR(255) NOT NULL,
 quantity NUMERIC(24,10) NOT NULL, unit VARCHAR(80) NOT NULL, period_start TIMESTAMPTZ NOT NULL,
 period_end TIMESTAMPTZ NOT NULL, source VARCHAR(50) NOT NULL, source_key VARCHAR(512) NOT NULL UNIQUE,
 attribution_status VARCHAR(30) NOT NULL DEFAULT 'unallocated', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cm_usage_period ON cm_usage_records(account_id,period_start,period_end);
CREATE TABLE IF NOT EXISTS cm_estimated_costs (
 id BIGSERIAL PRIMARY KEY, usage_record_id BIGINT NOT NULL REFERENCES cm_usage_records(id),
 pricing_rate_id BIGINT NOT NULL REFERENCES cm_pricing_rates(id), amount NUMERIC(24,10) NOT NULL,
 currency VARCHAR(8) NOT NULL, calculation_version VARCHAR(40) NOT NULL DEFAULT 'v1',
 calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT uq_cm_estimate UNIQUE(usage_record_id,pricing_rate_id)
);
CREATE TABLE IF NOT EXISTS cm_billing_imports (
 id BIGSERIAL PRIMARY KEY, account_id VARCHAR(12) NOT NULL REFERENCES cm_aws_accounts(account_id),
 billing_date TIMESTAMPTZ NOT NULL, s3_key VARCHAR(1024) NOT NULL, s3_version_id VARCHAR(255) NOT NULL DEFAULT '',
 manifest_status VARCHAR(30) NOT NULL DEFAULT 'pending', imported_at TIMESTAMPTZ,
 CONSTRAINT uq_cm_billing_object UNIQUE(account_id,s3_key,s3_version_id)
);
CREATE TABLE IF NOT EXISTS cm_actual_costs (
 id BIGSERIAL PRIMARY KEY, billing_import_id BIGINT NOT NULL REFERENCES cm_billing_imports(id),
 account_id VARCHAR(12) NOT NULL REFERENCES cm_aws_accounts(account_id), billing_date TIMESTAMPTZ NOT NULL,
 employee_id BIGINT REFERENCES cm_employees(id), resource_id VARCHAR(1024), service_code VARCHAR(100) NOT NULL,
 amount NUMERIC(24,10) NOT NULL, currency VARCHAR(8) NOT NULL, line_item_type VARCHAR(100),
 source_line_item_key VARCHAR(512) NOT NULL, CONSTRAINT uq_cm_actual_line UNIQUE(account_id,source_line_item_key)
);
CREATE TABLE IF NOT EXISTS cm_reconciliation_runs (
 id BIGSERIAL PRIMARY KEY, account_id VARCHAR(12) NOT NULL REFERENCES cm_aws_accounts(account_id),
 billing_date TIMESTAMPTZ NOT NULL, attempt INTEGER NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'pending',
 source_complete BOOLEAN NOT NULL DEFAULT FALSE, mismatch_count INTEGER NOT NULL DEFAULT 0, notes TEXT,
 CONSTRAINT uq_cm_recon_attempt UNIQUE(account_id,billing_date,attempt)
);
CREATE TABLE IF NOT EXISTS cm_reconciliation_items (
 id BIGSERIAL PRIMARY KEY, run_id BIGINT NOT NULL REFERENCES cm_reconciliation_runs(id),
 estimated_cost_id BIGINT REFERENCES cm_estimated_costs(id), actual_cost_id BIGINT REFERENCES cm_actual_costs(id),
 estimated_amount NUMERIC(24,10), actual_amount NUMERIC(24,10), difference NUMERIC(24,10),
 currency VARCHAR(8) NOT NULL, status VARCHAR(30) NOT NULL, reason TEXT
);
CREATE TABLE IF NOT EXISTS cm_daily_cost_status (
 id BIGSERIAL PRIMARY KEY, account_id VARCHAR(12) NOT NULL REFERENCES cm_aws_accounts(account_id),
 billing_date TIMESTAMPTZ NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'pending',
 last_reconciled_at TIMESTAMPTZ, finalized_at TIMESTAMPTZ, finalized_by VARCHAR(255), report_s3_key VARCHAR(1024),
 CONSTRAINT uq_cm_daily_status UNIQUE(account_id,billing_date)
);
