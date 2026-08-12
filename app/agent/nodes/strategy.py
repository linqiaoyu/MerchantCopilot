"""Strategy 节点:RAG + canonical Memory → LLM 改写出可执行建议。

阶段 4b 重写(对外契约不变,内部硬编码模板全删):
  - data["recommendations"] / data["merchant_profile"] / data["topic"] 三契约字段保留
  - 函数签名 strategy(state) -> dict 不变
  - 返回 {node_result: {task, headline, data, evidence}, steps: [...]}

5 路降级矩阵(条件判断顺序与 PM 草案 review 一致):
  RAG ok + LLM ok + prompt ok  → "llm" 主路径
  RAG fail + LLM ok            → "llm"(LLM 用纯 profile,kb_chunks=[])
  RAG ok + LLM 任一不可用       → "template_fallback_from_chunks"
  RAG fail + LLM 任一不可用     → "unavailable"(诚实说"暂不可用")

Memory 只来自 graph 的 ``recalled_memories``：它们已经经过 Policy Gate 和
pgvector 的时序/主题筛选。本节点不得直接读写 Mem0，避免绕过 policy gate。
"""
from __future__ import annotations

import json
from pathlib import Path

from langsmith import traceable

from app.agent.state import AgentState
from app.llm.client import get_llm
from app.rag.retriever import RAGNotAvailableError, retrieve

# --- prompt 懒加载单例(沿用 app/rag/retriever:get_reranker 范式)---
# 不在模块顶层读取文件:strategy.txt 缺失时 import 仍成功,走 fallback,
# test_graph 4/4 不挂(改造对下游透明的硬指标)。
_LLM_PROMPT: str | None = None
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "strategy.txt"


def _get_prompt() -> str | None:
    """返回 strategy.txt 内容;文件缺失返回 None(不缓存负面结果)。"""
    global _LLM_PROMPT
    if _LLM_PROMPT is not None:
        return _LLM_PROMPT
    try:
        _LLM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
        return _LLM_PROMPT
    except FileNotFoundError:
        return None  # 不缓存 None:文件后续被创建时仍可热加载


def _fallback_recommendations(chunks: list) -> list[str]:
    """LLM 不可用时:top-3 chunk 的 heading + 首句拼成 3 条建议。

    返回必为非空(chunks 至少 1 条时);chunks 空由调用方走"unavailable" 分支。
    """
    out = []
    for c in chunks[:3]:
        heading = c.metadata.get("heading", "") or c.source_doc
        first_sentence = c.content.split("。")[0][:80]
        out.append(f"参考《{heading}》:{first_sentence}。")
    return out


def profile_from_recalled_memories(recalled_memories: list[dict]) -> dict[str, object]:
    """Expose approved canonical facts to the Strategy prompt without a second store.

    Only stable profile predicates become named profile fields.  The complete,
    bounded context remains visible as provenance rather than being silently
    collapsed into a mutable Mem0 profile.
    """
    profile: dict[str, object] = {
        "category": "", "audience": "", "style": "", "recent_concerns": [],
        "canonical_context": recalled_memories,
    }
    concerns: list[str] = []
    for memory in recalled_memories:
        predicate = str(memory.get("predicate", ""))
        content = str(memory.get("content", ""))
        if predicate in {"category", "audience", "style"} and not profile[predicate]:
            profile[predicate] = content
        elif predicate in {"recent_concern", "recent_concerns"} and content:
            concerns.append(content)
    profile["recent_concerns"] = concerns[:5]
    return profile


@traceable(name="node_strategy", tags=["agent_node"])
def strategy(state: AgentState) -> dict:
    query = state["user_query"]
    llm = get_llm()
    recalled = state.get("recalled_memories", [])
    profile = profile_from_recalled_memories(recalled)
    profile_source = "canonical_pgvector" if recalled else "canonical_empty"

    # ---- RAG:fail-safe 包裹 ----
    chunks: list = []
    rag_status = "ok"
    try:
        chunks = retrieve(query, top_k=5)
    except RAGNotAvailableError as e:
        rag_status = f"unavailable: {e.__class__.__name__}"

    # ---- LLM:fail-safe 包裹 ----
    prompt = _get_prompt()
    recommendations: list[str] = []
    topic = ""
    generation = ""

    if not llm.is_stub and prompt is not None:
        try:
            user_payload = json.dumps({
                "user_query": query,
                "profile": {k: profile.get(k, "") for k in ("category", "audience", "style")},
                "recent_concerns": profile.get("recent_concerns", []),
                "canonical_memory": profile["canonical_context"],
                "kb_chunks": [
                    {"heading": c.metadata.get("heading", ""), "content": c.content}
                    for c in chunks
                ],
            }, ensure_ascii=False)
            # Strategy needs synthesis across profile and KB, so retain thinking mode.
            raw = llm.chat(system=prompt, user=user_payload, thinking=True)
            # 容错:LLM 可能给 ```json ... ``` 包裹(prompt L17 已禁,但兜底)
            raw_stripped = raw.strip()
            if raw_stripped.startswith("```"):
                raw_stripped = raw_stripped.strip("`")
                if raw_stripped.lower().startswith("json"):
                    raw_stripped = raw_stripped[4:].lstrip()
            parsed = json.loads(raw_stripped)
            topic = (parsed.get("topic") or "").strip()
            recommendations = [
                str(r).strip() for r in parsed.get("recommendations", []) if str(r).strip()
            ][:5]
            if recommendations:
                generation = "llm"
        except Exception as e:
            # LLM 失败(网络 / JSON 解析 / schema 不符)→ 落 fallback
            print(f"[strategy] LLM 主路径失败,落 fallback: {type(e).__name__}: {e}")

    # ---- 降级:LLM 没拿到 recommendations → chunk fallback / unavailable ----
    if not recommendations:
        if chunks:
            recommendations = _fallback_recommendations(chunks)
            generation = "template_fallback_from_chunks"
            topic = topic or "基于知识库片段的临时建议"
        else:
            recommendations = ["策略子系统暂不可用,请人工进一步核实"]
            generation = "unavailable"
            topic = topic or "策略暂不可用"

    # ---- C 方案:hanzi_count warning(PM 拍板 ② 文案不改)----
    for rec in recommendations:
        hanzi_count = sum(1 for c in rec if '一' <= c <= '鿿')
        if not (30 <= hanzi_count <= 60):
            print(f"[strategy] WARN: recommendation length out of [30,60]: "
                  f"{hanzi_count} chars, content: {rec[:30]}...")

    # ---- 组装 node_result(契约对齐)----
    headline = f"策略建议:{topic}"
    data = {
        # --- 契约必须保留(insight.py:24 兜底分支 + Insight LLM prompt 都会读)---
        "topic": topic,
        "recommendations": recommendations,
        "merchant_profile": profile,
        # --- 可观测性增字段(Insight LLM 透明,无 score 数字避免污染)---
        "retrieved_chunks": [
            {"source_doc": c.source_doc, "heading": c.metadata.get("heading", "")}
            for c in chunks
        ],
        "profile_source": profile_source,
        "generation": generation,
        "rag_status": rag_status,
    }
    evidence = [
        f"商家画像:{profile.get('category', '')};{profile.get('audience', '')}",
        (
            f"KB 召回 {len(chunks)} 条相关片段"
            + (f"(top-1:《{chunks[0].metadata.get('heading', '')}》)" if chunks else "(无召回)")
        ),
        f"生成方式:{generation}",
    ]
    recent = profile.get("recent_concerns", [])
    if recent:
        evidence.append(f"近期关注({len(recent)} 条):{recent[0]}")

    result = {"task": "strategy", "headline": headline,
              "data": data, "evidence": evidence}
    step = {"node": "Strategy", "summary": headline,
            "data": {"generation": generation, "rag_status": rag_status,
                     "chunks": len(chunks)}}
    return {"node_result": result, "steps": [step]}
