# v3.2 deterministic preregistration

Frozen on 2026-08-17 before any v3.2 formal Skill test execution.

- `memory_e2e_80.json`: 80 cases, SHA-256 `e794d0d26b8a36953cf57f3237c68e53f3d9b582ae97f66025367baac55e12bd`.
- `skill_eval_140.json`: 140 cases, SHA-256 `518a3e05ecc6aedb1e117a135a462529beed0229ef042c0950ad3587785b5619`.
- v3.0/v3.1 datasets and all failure/evolution artifacts remain immutable.
- The sole v3.2 oracle change is the reviewed `anomaly-root-cause` contract: `metric → attribution`, matching its preregistered baseline-validation requirement. This removes the prior redundancy with the bare attribution path.
- Test remains 60 cases, 20 per Skill. It is excluded from candidate generation, selection, promotion, rollback and threshold tuning.
- Ground truth is controlled deterministic synthetic truth, not human gold. Missing/nil rows remain failures.
- API hard budget is CNY 100 with warning at CNY 80; Qwen remains qualitative-only and optional.
