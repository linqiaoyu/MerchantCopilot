"""两个 MCP tool 的 JSON Schema(单独成文件,便于演示时逐字段讲解)。

设计取舍:
- 输入 schema 故意收窄 —— metric / anomaly_type 是闭枚举,不做自由 SQL
  (自由 SQL 属 Text-to-SQL 范畴,不在阶段 3)。
- 日期参数可选:不传时 Server 用数据集 MAX(date) 兜底,并在返回的
  evidence 里显式声明用了哪个默认日(诚实展示默认行为)。
- server.py 直接 import 这里的常量注册 tool,schema 只此一份不重复写。
"""
from __future__ import annotations

_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"  # ISO 8601 date,如 2026-04-02

QUERY_METRIC_NAME = "query_metric"
QUERY_METRIC_DESC = (
    "查询小张女装店在指定时间窗的经营指标。返回统一契约 "
    "{task,headline,data,evidence}。start_date/end_date 不传则默认数据集最新一天,"
    "并在 evidence 中声明。data 始终返回全量指标包(metric 参数只决定 headline "
    "聚焦哪个指标,不裁剪 data)。"
)
QUERY_METRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "metric": {
            "type": "string",
            # 闭枚举:用户问的是哪个指标 → 决定 headline 措辞;data 包不受影响
            "enum": ["gmv", "uv", "conversion", "refund_rate", "aov"],
            "description": "聚焦指标:gmv 毛销售额 / uv 访客 / conversion 转化率 "
            "/ refund_rate 退款率 / aov 客单价。",
        },
        "start_date": {
            "type": "string",
            "pattern": _ISO_DATE,
            "description": "窗口起始日(ISO 8601)。省略则与 end_date 一同回退到数据集最新一天。",
        },
        "end_date": {
            "type": "string",
            "pattern": _ISO_DATE,
            "description": "窗口结束日(ISO 8601)。省略则回退到数据集最新一天。",
        },
    },
    "required": ["metric"],
    "additionalProperties": False,
}

ATTRIBUTE_ANOMALY_NAME = "attribute_anomaly"
ATTRIBUTE_ANOMALY_DESC = (
    "对指定异常日做多步下钻归因(按 README 锁定的 2 步固定路径)。"
    "返回统一契约 {task,headline,data,evidence}。anomaly_date 不传则默认数据集"
    "最新一天,并在 evidence 中声明。"
)
ATTRIBUTE_ANOMALY_SCHEMA = {
    "type": "object",
    "properties": {
        "anomaly_type": {
            "type": "string",
            "enum": ["gmv_drop", "uv_surge", "refund_surge"],
            # 隐式语义提醒(给读 schema 的人 / 面试官):
            # refund_surge 是「连续异常」,Server 内部会自动从 anomaly_date
            # 派生一个 14 天回溯窗(anomaly_date-13d .. anomaly_date)再做趋势下钻;
            # gmv_drop / uv_surge 是单日异常,直接用 anomaly_date 当天。
            "description": "异常类型:gmv_drop GMV暴跌 / uv_surge UV暴涨 / "
            "refund_surge 退款率连续异常(后者 Server 内部自动派生 14 天回溯窗)。",
        },
        "anomaly_date": {
            "type": "string",
            "pattern": _ISO_DATE,
            "description": "异常发生日(ISO 8601)。省略则回退到数据集最新一天。",
        },
    },
    "required": ["anomaly_type"],
    "additionalProperties": False,
}
