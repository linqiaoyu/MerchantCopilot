CREATE TABLE IF NOT EXISTS threads (
    thread_id UUID PRIMARY KEY,
    merchant_id TEXT NOT NULL,
    idempotency_key UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS threads_merchant_created_idx ON threads (merchant_id, created_at DESC);

ALTER TABLE run_records
    ADD COLUMN IF NOT EXISTS feedback_json JSONB;
