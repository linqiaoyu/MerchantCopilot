# v3 dataset revision log

## v3.0-rc1 — retained failure

The first formal deterministic PostgreSQL Memory run is retained at
`evals/runs/v3_memory_e2e_80_postgres_20260817.json` with its report. It found
16/80 failures: temporal correction cases required citation of the superseded
source event even though the expected current fact was the correcting event.
Canonical state selection remained exact, but answer provenance was 0.80.

No implementation was tuned against these failed cases. The inconsistency was
corrected in a new dataset version rather than overwriting v3.0-rc1.

## v3.1-rc1 — retained pre-test revision

The provenance oracle is derived from current active events. Skill-Eval also
adds held-out anomaly language to make static/evolved selection measurably
different; train/dev/regression/test partitions remain disjoint by case ID and
test is excluded from candidate generation, selection and promotion.

No v3.1 frozen Skill test was executed. Its development/evolution artifacts remain retained.

## v3.2-rc1 — current frozen benchmark

Pre-formal-test architecture review found that anomaly Skill v1 had the same
single attribution action as the bare planner, so it could not demonstrate
procedural value. The reviewed static Skill v2 now executes `metric →
attribution`; the Skill oracle was updated in a new dataset version. No v3.1
formal Skill test was run, and every earlier artifact is retained.

The first and only v3.2 frozen Skill test completed under run id
`frozen-test-v3.2-rc1`; raw rows and the derived report are stored separately in
`evals/runs/`.
