# v2 Memory 60×6 bad-case report

数据集：`eval-dataset-v2.0-rc1`。此报告仅评估 canonical retrieval；不把 RAG 或 Qwen Judge 的未运行结果写入其中。

## minus_memory

相对 full 的失败：60/60。类别：cross_thread_recall 10、irrelevant_memory 10、stable_profile 20、strategy_feedback_outcome 5、temporal_conflict 15

| case | category | expected | recalled | forbidden recalled | provenance |
|---|---|---|---|---|---|
| mem-stable-01 | stable_profile | fact-s-01 | — | — | missing |
| mem-stable-02 | stable_profile | fact-s-02 | — | — | missing |
| mem-stable-03 | stable_profile | fact-s-03 | — | — | missing |
| mem-stable-04 | stable_profile | fact-s-04 | — | — | missing |
| mem-stable-05 | stable_profile | fact-s-05 | — | — | missing |
| mem-stable-06 | stable_profile | fact-s-06 | — | — | missing |
| mem-stable-07 | stable_profile | fact-s-07 | — | — | missing |
| mem-stable-08 | stable_profile | fact-s-08 | — | — | missing |
| mem-stable-09 | stable_profile | fact-s-09 | — | — | missing |
| mem-stable-10 | stable_profile | fact-s-10 | — | — | missing |
| mem-stable-11 | stable_profile | fact-s-11 | — | — | missing |
| mem-stable-12 | stable_profile | fact-s-12 | — | — | missing |
| mem-stable-13 | stable_profile | fact-s-13 | — | — | missing |
| mem-stable-14 | stable_profile | fact-s-14 | — | — | missing |
| mem-stable-15 | stable_profile | fact-s-15 | — | — | missing |
| mem-stable-16 | stable_profile | fact-s-16 | — | — | missing |
| mem-stable-17 | stable_profile | fact-s-17 | — | — | missing |
| mem-stable-18 | stable_profile | fact-s-18 | — | — | missing |
| mem-stable-19 | stable_profile | fact-s-19 | — | — | missing |
| mem-stable-20 | stable_profile | fact-s-20 | — | — | missing |
| mem-temporal-01 | temporal_conflict | fact-t-01-new | — | — | missing |
| mem-temporal-02 | temporal_conflict | fact-t-02-new | — | — | missing |
| mem-temporal-03 | temporal_conflict | fact-t-03-new | — | — | missing |
| mem-temporal-04 | temporal_conflict | fact-t-04-new | — | — | missing |
| mem-temporal-05 | temporal_conflict | fact-t-05-new | — | — | missing |
| mem-temporal-06 | temporal_conflict | fact-t-06-new | — | — | missing |
| mem-temporal-07 | temporal_conflict | fact-t-07-new | — | — | missing |
| mem-temporal-08 | temporal_conflict | fact-t-08-new | — | — | missing |
| mem-temporal-09 | temporal_conflict | fact-t-09-new | — | — | missing |
| mem-temporal-10 | temporal_conflict | fact-t-10-new | — | — | missing |
| mem-temporal-11 | temporal_conflict | fact-t-11-new | — | — | missing |
| mem-temporal-12 | temporal_conflict | fact-t-12-new | — | — | missing |
| mem-temporal-13 | temporal_conflict | fact-t-13-new | — | — | missing |
| mem-temporal-14 | temporal_conflict | fact-t-14-new | — | — | missing |
| mem-temporal-15 | temporal_conflict | fact-t-15-new | — | — | missing |
| mem-cross-thread-01 | cross_thread_recall | fact-x-01 | — | — | missing |
| mem-cross-thread-02 | cross_thread_recall | fact-x-02 | — | — | missing |
| mem-cross-thread-03 | cross_thread_recall | fact-x-03 | — | — | missing |
| mem-cross-thread-04 | cross_thread_recall | fact-x-04 | — | — | missing |
| mem-cross-thread-05 | cross_thread_recall | fact-x-05 | — | — | missing |
| mem-cross-thread-06 | cross_thread_recall | fact-x-06 | — | — | missing |
| mem-cross-thread-07 | cross_thread_recall | fact-x-07 | — | — | missing |
| mem-cross-thread-08 | cross_thread_recall | fact-x-08 | — | — | missing |
| mem-cross-thread-09 | cross_thread_recall | fact-x-09 | — | — | missing |
| mem-cross-thread-10 | cross_thread_recall | fact-x-10 | — | — | missing |
| mem-noise-01 | irrelevant_memory | fact-n-01-target | — | — | missing |
| mem-noise-02 | irrelevant_memory | fact-n-02-target | — | — | missing |
| mem-noise-03 | irrelevant_memory | fact-n-03-target | — | — | missing |
| mem-noise-04 | irrelevant_memory | fact-n-04-target | — | — | missing |
| mem-noise-05 | irrelevant_memory | fact-n-05-target | — | — | missing |
| mem-noise-06 | irrelevant_memory | fact-n-06-target | — | — | missing |
| mem-noise-07 | irrelevant_memory | fact-n-07-target | — | — | missing |
| mem-noise-08 | irrelevant_memory | fact-n-08-target | — | — | missing |
| mem-noise-09 | irrelevant_memory | fact-n-09-target | — | — | missing |
| mem-noise-10 | irrelevant_memory | fact-n-10-target | — | — | missing |
| mem-decision-01 | strategy_feedback_outcome | fact-d-01-decision, fact-d-01-outcome | — | — | missing |
| mem-decision-02 | strategy_feedback_outcome | fact-d-02-decision, fact-d-02-outcome | — | — | missing |
| mem-decision-03 | strategy_feedback_outcome | fact-d-03-decision, fact-d-03-outcome | — | — | missing |
| mem-decision-04 | strategy_feedback_outcome | fact-d-04-decision, fact-d-04-outcome | — | — | missing |
| mem-decision-05 | strategy_feedback_outcome | fact-d-05-decision, fact-d-05-outcome | — | — | missing |

## minus_rag

相对 full 的失败：0/60。类别：无

无差异失败；该配置未改变 canonical retrieval 指标。

## bare

相对 full 的失败：60/60。类别：cross_thread_recall 10、irrelevant_memory 10、stable_profile 20、strategy_feedback_outcome 5、temporal_conflict 15

| case | category | expected | recalled | forbidden recalled | provenance |
|---|---|---|---|---|---|
| mem-stable-01 | stable_profile | fact-s-01 | — | — | missing |
| mem-stable-02 | stable_profile | fact-s-02 | — | — | missing |
| mem-stable-03 | stable_profile | fact-s-03 | — | — | missing |
| mem-stable-04 | stable_profile | fact-s-04 | — | — | missing |
| mem-stable-05 | stable_profile | fact-s-05 | — | — | missing |
| mem-stable-06 | stable_profile | fact-s-06 | — | — | missing |
| mem-stable-07 | stable_profile | fact-s-07 | — | — | missing |
| mem-stable-08 | stable_profile | fact-s-08 | — | — | missing |
| mem-stable-09 | stable_profile | fact-s-09 | — | — | missing |
| mem-stable-10 | stable_profile | fact-s-10 | — | — | missing |
| mem-stable-11 | stable_profile | fact-s-11 | — | — | missing |
| mem-stable-12 | stable_profile | fact-s-12 | — | — | missing |
| mem-stable-13 | stable_profile | fact-s-13 | — | — | missing |
| mem-stable-14 | stable_profile | fact-s-14 | — | — | missing |
| mem-stable-15 | stable_profile | fact-s-15 | — | — | missing |
| mem-stable-16 | stable_profile | fact-s-16 | — | — | missing |
| mem-stable-17 | stable_profile | fact-s-17 | — | — | missing |
| mem-stable-18 | stable_profile | fact-s-18 | — | — | missing |
| mem-stable-19 | stable_profile | fact-s-19 | — | — | missing |
| mem-stable-20 | stable_profile | fact-s-20 | — | — | missing |
| mem-temporal-01 | temporal_conflict | fact-t-01-new | — | — | missing |
| mem-temporal-02 | temporal_conflict | fact-t-02-new | — | — | missing |
| mem-temporal-03 | temporal_conflict | fact-t-03-new | — | — | missing |
| mem-temporal-04 | temporal_conflict | fact-t-04-new | — | — | missing |
| mem-temporal-05 | temporal_conflict | fact-t-05-new | — | — | missing |
| mem-temporal-06 | temporal_conflict | fact-t-06-new | — | — | missing |
| mem-temporal-07 | temporal_conflict | fact-t-07-new | — | — | missing |
| mem-temporal-08 | temporal_conflict | fact-t-08-new | — | — | missing |
| mem-temporal-09 | temporal_conflict | fact-t-09-new | — | — | missing |
| mem-temporal-10 | temporal_conflict | fact-t-10-new | — | — | missing |
| mem-temporal-11 | temporal_conflict | fact-t-11-new | — | — | missing |
| mem-temporal-12 | temporal_conflict | fact-t-12-new | — | — | missing |
| mem-temporal-13 | temporal_conflict | fact-t-13-new | — | — | missing |
| mem-temporal-14 | temporal_conflict | fact-t-14-new | — | — | missing |
| mem-temporal-15 | temporal_conflict | fact-t-15-new | — | — | missing |
| mem-cross-thread-01 | cross_thread_recall | fact-x-01 | — | — | missing |
| mem-cross-thread-02 | cross_thread_recall | fact-x-02 | — | — | missing |
| mem-cross-thread-03 | cross_thread_recall | fact-x-03 | — | — | missing |
| mem-cross-thread-04 | cross_thread_recall | fact-x-04 | — | — | missing |
| mem-cross-thread-05 | cross_thread_recall | fact-x-05 | — | — | missing |
| mem-cross-thread-06 | cross_thread_recall | fact-x-06 | — | — | missing |
| mem-cross-thread-07 | cross_thread_recall | fact-x-07 | — | — | missing |
| mem-cross-thread-08 | cross_thread_recall | fact-x-08 | — | — | missing |
| mem-cross-thread-09 | cross_thread_recall | fact-x-09 | — | — | missing |
| mem-cross-thread-10 | cross_thread_recall | fact-x-10 | — | — | missing |
| mem-noise-01 | irrelevant_memory | fact-n-01-target | — | — | missing |
| mem-noise-02 | irrelevant_memory | fact-n-02-target | — | — | missing |
| mem-noise-03 | irrelevant_memory | fact-n-03-target | — | — | missing |
| mem-noise-04 | irrelevant_memory | fact-n-04-target | — | — | missing |
| mem-noise-05 | irrelevant_memory | fact-n-05-target | — | — | missing |
| mem-noise-06 | irrelevant_memory | fact-n-06-target | — | — | missing |
| mem-noise-07 | irrelevant_memory | fact-n-07-target | — | — | missing |
| mem-noise-08 | irrelevant_memory | fact-n-08-target | — | — | missing |
| mem-noise-09 | irrelevant_memory | fact-n-09-target | — | — | missing |
| mem-noise-10 | irrelevant_memory | fact-n-10-target | — | — | missing |
| mem-decision-01 | strategy_feedback_outcome | fact-d-01-decision, fact-d-01-outcome | — | — | missing |
| mem-decision-02 | strategy_feedback_outcome | fact-d-02-decision, fact-d-02-outcome | — | — | missing |
| mem-decision-03 | strategy_feedback_outcome | fact-d-03-decision, fact-d-03-outcome | — | — | missing |
| mem-decision-04 | strategy_feedback_outcome | fact-d-04-decision, fact-d-04-outcome | — | — | missing |
| mem-decision-05 | strategy_feedback_outcome | fact-d-05-decision, fact-d-05-outcome | — | — | missing |

## raw_history

相对 full 的失败：15/60。类别：temporal_conflict 15

| case | category | expected | recalled | forbidden recalled | provenance |
|---|---|---|---|---|---|
| mem-temporal-01 | temporal_conflict | fact-t-01-new | fact-t-01-new, fact-t-01-old | fact-t-01-old | ok |
| mem-temporal-02 | temporal_conflict | fact-t-02-new | fact-t-02-new, fact-t-02-old | fact-t-02-old | ok |
| mem-temporal-03 | temporal_conflict | fact-t-03-new | fact-t-03-new, fact-t-03-old | fact-t-03-old | ok |
| mem-temporal-04 | temporal_conflict | fact-t-04-new | fact-t-04-new, fact-t-04-old | fact-t-04-old | ok |
| mem-temporal-05 | temporal_conflict | fact-t-05-new | fact-t-05-new, fact-t-05-old | fact-t-05-old | ok |
| mem-temporal-06 | temporal_conflict | fact-t-06-new | fact-t-06-new, fact-t-06-old | fact-t-06-old | ok |
| mem-temporal-07 | temporal_conflict | fact-t-07-new | fact-t-07-new, fact-t-07-old | fact-t-07-old | ok |
| mem-temporal-08 | temporal_conflict | fact-t-08-new | fact-t-08-new, fact-t-08-old | fact-t-08-old | ok |
| mem-temporal-09 | temporal_conflict | fact-t-09-new | fact-t-09-new, fact-t-09-old | fact-t-09-old | ok |
| mem-temporal-10 | temporal_conflict | fact-t-10-new | fact-t-10-new, fact-t-10-old | fact-t-10-old | ok |
| mem-temporal-11 | temporal_conflict | fact-t-11-new | fact-t-11-new, fact-t-11-old | fact-t-11-old | ok |
| mem-temporal-12 | temporal_conflict | fact-t-12-new | fact-t-12-new, fact-t-12-old | fact-t-12-old | ok |
| mem-temporal-13 | temporal_conflict | fact-t-13-new | fact-t-13-new, fact-t-13-old | fact-t-13-old | ok |
| mem-temporal-14 | temporal_conflict | fact-t-14-new | fact-t-14-new, fact-t-14-old | fact-t-14-old | ok |
| mem-temporal-15 | temporal_conflict | fact-t-15-new | fact-t-15-new, fact-t-15-old | fact-t-15-old | ok |

## no_temporal_policy

相对 full 的失败：20/60。类别：strategy_feedback_outcome 5、temporal_conflict 15

| case | category | expected | recalled | forbidden recalled | provenance |
|---|---|---|---|---|---|
| mem-temporal-01 | temporal_conflict | fact-t-01-new | fact-t-01-new, fact-t-01-old | fact-t-01-old | ok |
| mem-temporal-02 | temporal_conflict | fact-t-02-new | fact-t-02-new, fact-t-02-old | fact-t-02-old | ok |
| mem-temporal-03 | temporal_conflict | fact-t-03-new | fact-t-03-new, fact-t-03-old | fact-t-03-old | ok |
| mem-temporal-04 | temporal_conflict | fact-t-04-new | fact-t-04-new, fact-t-04-old | fact-t-04-old | ok |
| mem-temporal-05 | temporal_conflict | fact-t-05-new | fact-t-05-new, fact-t-05-old | fact-t-05-old | ok |
| mem-temporal-06 | temporal_conflict | fact-t-06-new | fact-t-06-new, fact-t-06-old | fact-t-06-old | ok |
| mem-temporal-07 | temporal_conflict | fact-t-07-new | fact-t-07-new, fact-t-07-old | fact-t-07-old | ok |
| mem-temporal-08 | temporal_conflict | fact-t-08-new | fact-t-08-new, fact-t-08-old | fact-t-08-old | ok |
| mem-temporal-09 | temporal_conflict | fact-t-09-new | fact-t-09-new, fact-t-09-old | fact-t-09-old | ok |
| mem-temporal-10 | temporal_conflict | fact-t-10-new | fact-t-10-new, fact-t-10-old | fact-t-10-old | ok |
| mem-temporal-11 | temporal_conflict | fact-t-11-new | fact-t-11-new, fact-t-11-old | fact-t-11-old | ok |
| mem-temporal-12 | temporal_conflict | fact-t-12-new | fact-t-12-new, fact-t-12-old | fact-t-12-old | ok |
| mem-temporal-13 | temporal_conflict | fact-t-13-new | fact-t-13-new, fact-t-13-old | fact-t-13-old | ok |
| mem-temporal-14 | temporal_conflict | fact-t-14-new | fact-t-14-new, fact-t-14-old | fact-t-14-old | ok |
| mem-temporal-15 | temporal_conflict | fact-t-15-new | fact-t-15-new, fact-t-15-old | fact-t-15-old | ok |
| mem-decision-01 | strategy_feedback_outcome | fact-d-01-decision, fact-d-01-outcome | — | — | missing |
| mem-decision-02 | strategy_feedback_outcome | fact-d-02-decision, fact-d-02-outcome | — | — | missing |
| mem-decision-03 | strategy_feedback_outcome | fact-d-03-decision, fact-d-03-outcome | — | — | missing |
| mem-decision-04 | strategy_feedback_outcome | fact-d-04-decision, fact-d-04-outcome | — | — | missing |
| mem-decision-05 | strategy_feedback_outcome | fact-d-05-decision, fact-d-05-outcome | — | — | missing |

