"""AgentState:LangGraph StateGraph 在节点间流转的状态。

字段经设计讨论裁剪定稿(见 docs):三类任务互斥,一次只走一条路,
故所有业务结果统一收敛到单个 node_result,不为「未来扩展」预留分字段。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    user_query: str
    """用户原始问题(入口写入,全程只读)。"""

    intent: str
    """Router 分类结果:metric | attribution | strategy。"""

    time_window: dict[str, str]
    """解析出的时间窗 {"start": "2026-04-02", "end": "2026-04-02"};可空。"""

    node_result: dict[str, Any]
    """业务节点统一输出契约:{task, headline, data, evidence}。

    - task:metric | attribution | strategy
    - headline:一句话结论(节点确定性产出,不经 LLM)
    - data:结构化硬数字(SQL 算出,可被测试直接断言)
    - evidence:下钻轨迹/依据列表,供 Insight 组织语言
    """

    final_answer: str
    """Insight 生成的最终自然语言回答。"""

    steps: Annotated[list[dict[str, Any]], operator.add]
    """执行轨迹:每节点 return {"steps":[...]} 经 operator.add 累加(LangGraph 标准 reducer)。

    CLI 可视化用,阶段 5 接 LangSmith 复用。
    """
