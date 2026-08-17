# v3.1 deterministic preregistration

Frozen on 2026-08-17 before any v3.1 formal Skill test execution.

- `memory_e2e_80.json`: 80 cases, SHA-256 `2d22f750b68b0e7b075aa0eeba424c0c3571d2cfaff8ad7f4e997942951fc71b`.
- `skill_eval_140.json`: 140 cases, SHA-256 `ca00deaa68541364e8c5bcd9ee028ed78f7df0680360d84e8c29f32edf4c5857`.
- Ground truth is controlled deterministic synthetic truth, not human gold.
- v3.0-rc1 and its failed formal deterministic Memory run remain immutable. v3.1 changes the temporal-correction provenance oracle from the superseded source to the active correction source; it also preregisters held-out anomaly phrasing needed to measure Skill evolution.
- Skill test contains exactly 60 cases and 20 per Skill. Test cases may only be used for the final six-arm report; they may not generate, select, patch, promote or roll back a Skill.
- Missing cases, duplicated `(case_id, arm)`, unknown arms, nil filtering, or a hash mismatch invalidates a run.
- Formal API accounting uses `evals/v3/price_snapshot_2026-08-17.json`; CNY 80 warns and CNY 100 hard-stops before the next call.
- Qwen remains qualitative-only: at most 20 cases and at most 10% of total budget.
