# v3 deterministic preregistration

Frozen on 2026-08-17 before any formal test optimization.

- `memory_e2e_80.json`: 80 cases, SHA-256 `b6c6b0a73b9af26a07165ca098c3dc8a858880127d220d0fc0fdd7672a391129`.
- `skill_eval_140.json`: 140 cases, SHA-256 `2af9146f910201449e1bd11289aa68229b81fe855600d304ba51bcfba707a743`.
- Ground truth is deterministic controlled synthetic truth, not human gold.
- Skill test split contains exactly 60 cases, 20 per Skill. Test cases may only be used once for the preregistered six-arm final report; they may not generate, select, patch, promote, or roll back a Skill.
- Missing cases, duplicated `(case_id, arm)`, unknown arms, nil filtering, or a hash mismatch invalidate a run.
- Formal API accounting uses the dated price snapshot in `evals/v3/price_snapshot_2026-08-17.json`; CNY 80 warns and CNY 100 stops before the next call.
- Qwen is qualitative only: at most 20 cases and at most 10% of the total budget.
