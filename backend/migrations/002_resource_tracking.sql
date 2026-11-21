BEGIN;

ALTER TABLE cm_aws_resources
    ADD COLUMN IF NOT EXISTS resource_name TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_by TEXT,
    ADD COLUMN IF NOT EXISTS created_by_type TEXT,
    ADD COLUMN IF NOT EXISTS resource_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS status_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS cm_resource_events (
    id BIGSERIAL PRIMARY KEY,
    account_id VARCHAR(12) NOT NULL,
    event_id TEXT NOT NULL,
    resource_id VARCHAR(1024) NOT NULL,
    service_code VARCHAR(100) NOT NULL,
    region VARCHAR(100),
    event_name TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    actor TEXT,
    actor_type TEXT,
    event_source TEXT,
    event_json JSONB NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id, event_id, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_cm_resource_events_time
    ON cm_resource_events(account_id, event_time DESC);

CREATE TABLE IF NOT EXISTS cm_resource_monthly_costs (
    id BIGSERIAL PRIMARY KEY,
    account_id VARCHAR(12) NOT NULL,
    resource_id VARCHAR(1024) NOT NULL,
    billing_month DATE NOT NULL,
    cost_type VARCHAR(20) NOT NULL
        CHECK (cost_type IN ('actual', 'estimated', 'allocated')),
    amount NUMERIC(20,8) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    source TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id, resource_id, billing_month, cost_type, source)
);

CREATE TABLE IF NOT EXISTS cm_resource_collector_state (
    account_id VARCHAR(12) NOT NULL,
    region VARCHAR(100) NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'lookup',
    checkpoint TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(account_id, region, source)
);

COMMIT;
