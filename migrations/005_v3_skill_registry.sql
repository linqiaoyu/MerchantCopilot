CREATE TABLE IF NOT EXISTS skill_versions (
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    instructions TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'active', 'rejected', 'rolled_back', 'archived')),
    parent_version TEXT,
    source_trace_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (skill_id, version),
    UNIQUE (skill_id, content_hash)
);
CREATE UNIQUE INDEX IF NOT EXISTS skill_versions_one_active
    ON skill_versions (skill_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS skill_events (
    event_id UUID PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('generated', 'promoted', 'rejected', 'rolled_back')),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS skill_events_skill_created_idx
    ON skill_events (skill_id, created_at, event_id);

CREATE TABLE IF NOT EXISTS skill_eval_runs (
    eval_run_id UUID PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    dataset_partition TEXT NOT NULL CHECK (dataset_partition IN ('train', 'dev', 'regression', 'test')),
    dataset_hash TEXT NOT NULL,
    metrics_json JSONB NOT NULL,
    report_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION reject_event_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS run_events_append_only ON run_events;
CREATE TRIGGER run_events_append_only BEFORE UPDATE OR DELETE ON run_events
FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();

DROP TRIGGER IF EXISTS skill_events_append_only ON skill_events;
CREATE TRIGGER skill_events_append_only BEFORE UPDATE OR DELETE ON skill_events
FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();

-- v2 的 index_status 是可补偿投影；除此之外 Memory event 业务内容不可修改。
CREATE OR REPLACE FUNCTION protect_memory_event_payload() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'memory_events is append-only';
    END IF;
    IF (to_jsonb(NEW) - 'index_status') IS DISTINCT FROM (to_jsonb(OLD) - 'index_status') THEN
        RAISE EXCEPTION 'memory_events payload is append-only';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS memory_events_payload_append_only ON memory_events;
CREATE TRIGGER memory_events_payload_append_only BEFORE UPDATE OR DELETE ON memory_events
FOR EACH ROW EXECUTE FUNCTION protect_memory_event_payload();
