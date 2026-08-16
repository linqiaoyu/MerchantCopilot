CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS run_records (
    run_id UUID PRIMARY KEY,
    thread_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    idempotency_key UUID NOT NULL UNIQUE,
    status TEXT NOT NULL,
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS run_records_thread_created_idx ON run_records (thread_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_events (
    event_id UUID PRIMARY KEY,
    run_id UUID REFERENCES run_records(run_id),
    merchant_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json JSONB NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    index_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, source_ref)
);

CREATE TABLE IF NOT EXISTS memory_facts (
    memory_id UUID PRIMARY KEY,
    source_event_id UUID NOT NULL UNIQUE REFERENCES memory_events(event_id),
    merchant_id TEXT NOT NULL,
    memory_kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json JSONB NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),
    status TEXT NOT NULL DEFAULT 'pending',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memory_facts_active_idx ON memory_facts (merchant_id, subject, predicate)
WHERE status = 'active' AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS memory_facts_embedding_idx ON memory_facts
USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

CREATE TABLE IF NOT EXISTS memory_links (
    link_id UUID PRIMARY KEY,
    from_memory_id UUID NOT NULL REFERENCES memory_facts(memory_id),
    to_memory_id UUID NOT NULL REFERENCES memory_facts(memory_id),
    relation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (from_memory_id, to_memory_id, relation)
);

CREATE TABLE IF NOT EXISTS usage_counters (
    counter_month DATE NOT NULL,
    merchant_id TEXT NOT NULL,
    run_count INTEGER NOT NULL DEFAULT 0,
    prompt_tokens BIGINT NOT NULL DEFAULT 0,
    completion_tokens BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (counter_month, merchant_id)
);
