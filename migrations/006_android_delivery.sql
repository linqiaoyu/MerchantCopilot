-- Android 交付仅增加投影和请求收据，不改写历史 canonical events。
ALTER TABLE run_records
    ADD COLUMN IF NOT EXISTS execution_owner TEXT,
    ADD COLUMN IF NOT EXISTS deadline_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;

-- 单执行槽覆盖使用新交付协议的任务；历史评测记录不参与槽竞争。
CREATE UNIQUE INDEX IF NOT EXISTS delivery_one_live_run
    ON run_records ((true))
    WHERE execution_owner IS NOT NULL AND status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS delivery_runs_merchant_page
    ON run_records (merchant_id, created_at DESC, run_id DESC);

CREATE TABLE IF NOT EXISTS delivery_operations (
    idempotency_key UUID PRIMARY KEY,
    operation TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    request_json JSONB NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE memory_facts
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1);

CREATE INDEX IF NOT EXISTS delivery_memories_merchant_page
    ON memory_facts (merchant_id, created_at DESC, memory_id DESC);

-- public_ 前缀只标识客户端投影。内部模型输入及输出仍留在原始 run_events。
CREATE INDEX IF NOT EXISTS delivery_public_events
    ON run_events (run_id, sequence_no)
    WHERE event_type LIKE 'public_%';

CREATE TRIGGER delivery_operations_append_only BEFORE UPDATE OR DELETE ON delivery_operations
FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();
