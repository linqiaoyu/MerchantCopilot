"""AgentState:LangGraph StateGraph 在节点间流转的状态。

字段经设计讨论裁剪定稿(见 docs):三类任务互斥,一次只走一条路,
故所有业务结果统一收敛到单个 node_result,不为「未来扩展」预留分字段。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    thread_id: str
    dataset_partition: str
    evaluation_arm: str
    budget_context: dict[str, Any]

    merchant_id: str
    """单一 demo 商家的标识；v2 canonical Memory 的查询隔离键。"""

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

    recalled_memories: list[dict[str, Any]]
    memory_query_plan: dict[str, Any]
    memory_usage_trace: dict[str, Any]
    skill_candidates: list[dict[str, Any]]
    selected_skill: dict[str, Any]
    skill_selection_trace: dict[str, Any]
    skill_version: str
    compiled_skill_plan: Any
    skill_execution_trace: list[dict[str, Any]]
    skill_registry_mode: str
    raw_history: list[dict[str, Any]]
    memory_mode: str
    evaluation_memory_context: list[dict[str, Any]]
    evidence_verification: dict[str, Any]
    plan: Any
    action_cursor: int
    action_results: list[dict[str, Any]]
    prior_action_results: list[dict[str, Any]]
    """每个有界 action 的结果，用于 Evidence Verifier 与跨 case 比较。"""

    run_started_monotonic: float
    """仅进程内超时预算用；不可持久化，避免把单调时钟写入 checkpoint。"""

    verification: dict[str, Any]

    memory_candidates: list[dict[str, Any]]
    """候选长期记忆及其确定性 policy 状态；持久化由 S1 Postgres repository 负责。"""

    disable_memory_candidates: bool
    """Only offline no-Memory evaluations may skip candidate extraction entirely."""

    disable_memory_recall: bool
    """Offline component ablations may bypass canonical recall without changing runtime code."""

    disable_rag: bool
    """Offline component ablations may bypass KB retrieval without changing runtime code."""

    disable_skill: bool
    """Offline ablations may bypass Skill retrieval while retaining the bounded planner."""
