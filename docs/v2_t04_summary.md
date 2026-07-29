# v2 T04：Memory 评测预注册

完成日期：2026-07-30

- 冻结 eval-dataset-v2.0-rc1：60 条受控多轮 Memory 序列。
- 覆盖稳定画像 20、时序冲突 15、跨 thread 10、无关干扰 10、Strategy→Feedback→Outcome 5。
- 每条包含事件顺序、当前真值、禁止召回项、预期召回和 provenance。
- 新增无依赖 Schema 校验器和 pytest 覆盖；校验通过。
- 预注册固定两组消融、指标、nil result 规则和调参边界。
- ANNOTATION_REVIEW.md 提供双人独立 temporal ground truth 签核表；当前尚未由两位真人签核，因此这项验收证据仍待补齐。
