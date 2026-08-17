ALTER TABLE memory_events
    ADD COLUMN IF NOT EXISTS thread_id TEXT,
    ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 2,
    ADD COLUMN IF NOT EXISTS effective_from TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS effective_to TIMESTAMPTZ;

ALTER TABLE memory_facts
    ADD COLUMN IF NOT EXISTS fact_type TEXT NOT NULL DEFAULT 'observation',
    ADD COLUMN IF NOT EXISTS scope_type TEXT NOT NULL DEFAULT 'merchant',
    ADD COLUMN IF NOT EXISTS scope_id TEXT,
    ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS truth_confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS utility_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS contradiction_group_id UUID,
    ADD COLUMN IF NOT EXISTS approval_reason TEXT,
    ADD COLUMN IF NOT EXISTS effective_from TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS effective_to TIMESTAMPTZ;

UPDATE memory_facts
   SET fact_type = CASE
       WHEN memory_kind IN ('strategy', 'decision') THEN 'decision'
       WHEN memory_kind = 'outcome' THEN 'outcome'
       ELSE fact_type
   END,
       scope_id = COALESCE(scope_id, merchant_id),
       truth_confidence = confidence
 WHERE scope_id IS NULL
    OR memory_kind IN ('strategy', 'decision', 'outcome');

ALTER TABLE memory_facts DROP CONSTRAINT IF EXISTS memory_facts_fact_type_check;
ALTER TABLE memory_facts ADD CONSTRAINT memory_facts_fact_type_check
    CHECK (fact_type IN ('observation', 'user_fact', 'inference', 'decision', 'outcome'));
ALTER TABLE memory_facts DROP CONSTRAINT IF EXISTS memory_facts_scope_type_check;
ALTER TABLE memory_facts ADD CONSTRAINT memory_facts_scope_type_check
    CHECK (scope_type IN ('merchant', 'thread'));
ALTER TABLE memory_facts DROP CONSTRAINT IF EXISTS memory_facts_effective_range_check;
ALTER TABLE memory_facts ADD CONSTRAINT memory_facts_effective_range_check
    CHECK ((effective_from IS NULL AND effective_to IS NULL)
        OR (effective_from IS NOT NULL AND effective_to IS NOT NULL AND effective_from < effective_to));

DROP INDEX IF EXISTS memory_facts_one_active_semantic_key;
CREATE UNIQUE INDEX IF NOT EXISTS memory_facts_one_active_current_key
    ON memory_facts (merchant_id, subject, predicate)
    WHERE status = 'active' AND valid_to IS NULL
      AND effective_from IS NULL AND effective_to IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS memory_facts_one_active_period_key
    ON memory_facts (merchant_id, subject, predicate, effective_from, effective_to)
    WHERE status = 'active' AND valid_to IS NULL
      AND effective_from IS NOT NULL AND effective_to IS NOT NULL;

CREATE TABLE IF NOT EXISTS run_events (
    event_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES run_records(run_id),
    sequence_no INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    model_visible BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, sequence_no)
);
CREATE INDEX IF NOT EXISTS run_events_type_idx
    ON run_events (run_id, event_type, sequence_no);

CREATE INDEX IF NOT EXISTS memory_facts_scope_active_idx
    ON memory_facts (merchant_id, scope_type, scope_id, fact_type, valid_from DESC)
 WHERE status = 'active' AND valid_to IS NULL;
