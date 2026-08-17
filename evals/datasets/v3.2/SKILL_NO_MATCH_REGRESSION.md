# Auxiliary no-match safety regression

This post-test safety suite contains 30 generic metric/data requests with no Skill oracle. It is not used for candidate generation, promotion, threshold selection or the frozen 60-case headline test.

- Case generator: `evals/v3/run_skill_no_match.py`
- Canonical case-list SHA-256: `8bab08e8d81eaaa7743c3b4aa5044e23ac15d3862027ca23b040fe2d8570c391`
- Registries: file static and PostgreSQL active/evolved
- Expected: no Skill selected in all 60 registry/case evaluations
- Result: `evals/runs/v3_2_skill_no_match_30_20260817.json`
