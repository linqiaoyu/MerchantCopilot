# v2 Memory 人工独立复核清单

只向 Reviewer 展示每条 case 的 event 序列与 query；不得展示 current_truth、expected_recall_ids、forbidden_memory_ids 或 provenance。

必须逐条独立判断：10 条 irrelevant_memory（禁止召回边界）与 5 条 strategy_feedback_outcome（反馈后复用边界）。其余 45 条可先通过 rederive 脚本，再抽样人工确认。

限制：rederive_v2_truth.py 与标注共用口径，只能验证转录与内部一致性；它不是独立复核，不计入两人次。
