# Memory v2 标注与独立复核记录

数据集：eval-dataset-v2.0-rc1
复核对象：60 条 temporal ground truth、有效期、禁止召回项和 provenance。

## 标注口径

- current_truth 只能指当前有效且可复用的 canonical fact。
- temporal_conflict 中 old fact 必须进入 forbidden_memory_ids，新事实必须 supersede 它。
- 仅旧 thread 的 working_note 必须禁止在新 thread 召回。
- LLM proposed_decision 在 positive feedback 前不属于可复用 outcome memory。
- expected_provenance 的 source_event_id 必须出现在同一 case 的 events 中。

## 双人独立签核（待真人完成）

| 审阅人 | 角色/身份 | 独立复核日期 | 覆盖案例 | 分歧记录链接 | 签核 |
|---|---|---|---|---|---|
| Reviewer A | 待指定 | 待签核 | 60/60 | 待填写 | 待签核 |
| Reviewer B | 待指定 | 待签核 | 60/60 | 待填写 | 待签核 |

在两位不同真人完成独立复核前，数据集仅为 RC1，不得表述为已满足“双人复核”验收项。
