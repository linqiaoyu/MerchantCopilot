"""阶段 5 B.3-B.5:Streamlit demo —— 三段可视化 + 侧边栏 + 降级 UI + trace URL 嵌入。

主区域:final_answer → (strategy 任务时) 知识库召回 / 商家画像 / 建议列表三段。
侧边栏:商家最近问过的问题(Mem0 recent_concerns,有滞后一次的渲染时序)。
页脚:本次 invoke 的 LangSmith trace URL(失败 fallback 到 project 主页)。

运行:streamlit run ui/app.py
"""
from __future__ import annotations

import streamlit as st

from app.agent.graph_v2 import build_graph_v2
from app.agent.runtime import run_query
from app.memory.merchant_memory import get_profile

DEMO_MERCHANT_ID = "xiaozhang_women"
LANGSMITH_PROJECT = "merchant-copilot"


@st.cache_resource
def get_graph():
    """缓存 graph 单例 —— BGE-M3 / CrossEncoder / Mem0 客户端只在首次启动加载。"""
    return build_graph_v2()


@st.cache_resource
def get_langsmith_client():
    """LangSmith Client 单例;失败返回 None,页脚走 fallback。"""
    try:
        from langsmith import Client
        return Client()
    except Exception:
        return None


def _fetch_latest_trace_url() -> str | None:
    """拿最新 LangGraph root run 的完整 URL。失败返回 None。"""
    client = get_langsmith_client()
    if client is None:
        return None
    try:
        runs = list(client.list_runs(
            project_name=LANGSMITH_PROJECT,
            filter='eq(name, "LangGraph")',
            limit=1,
        ))
        if runs:
            return client.get_run_url(run=runs[0])
    except Exception:
        pass
    return None


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 📝 商家最近问过的问题")
        st.caption("(商家画像 + 历史关注问题,按 mem0 内部排序展示前 5 条)")
        try:
            profile = get_profile(DEMO_MERCHANT_ID)
            concerns = profile.get("recent_concerns", [])
        except Exception:
            concerns = []
        if concerns:
            for i, c in enumerate(concerns):
                if i == 0:
                    st.markdown(f"**🔸 {c}**")
                else:
                    st.markdown(f"・{c}")
        else:
            st.caption("(暂无历史问题)")


def _render_chunks(chunks: list) -> None:
    if not chunks:
        st.caption("⚠️ 知识库召回不可用,strategy 走 profile-only 路径")
        return
    with st.expander(f"📚 知识库召回 (top {len(chunks)})", expanded=False):
        for ch in chunks:
            st.markdown(f"**{ch.get('source_doc', '')}** — {ch.get('heading', '')}")


def _render_profile(profile: dict) -> None:
    cols = st.columns(3)
    cols[0].metric("🏷️ 类目", profile.get("category", ""))
    cols[1].metric("👥 主力客群", profile.get("audience", ""))
    cols[2].metric("🎨 风格偏好", profile.get("style", ""))


def _render_recommendations(recs: list) -> None:
    st.markdown("### 💡 建议")
    for i, rec in enumerate(recs, 1):
        st.markdown(f"**{i}.** {rec}")


st.set_page_config(page_title="MerchantCopilot", page_icon=None, layout="wide")
st.title("MerchantCopilot")
st.caption("直播电商商家经营分析 Agent · LangGraph + RAG + Mem0")

_render_sidebar()
graph = get_graph()

query = st.text_area(
    label="请输入你的问题",
    placeholder="例如:退款率高怎么办",
    height=100,
)
submitted = st.button("提交", type="primary")

if submitted:
    if not query.strip():
        st.warning("请先输入问题")
    else:
        with st.spinner("分析中..."):
            result = run_query(query.strip(), graph=graph)

        node_result = result.get("node_result", {})
        data = node_result.get("data", {})
        generation = data.get("generation", "")

        st.markdown(result.get("final_answer", "未获得分析结果,请重述问题或缩小范围"))

        if generation == "unavailable":
            st.error("⚠️ 服务暂不可用 — 4b strategy 节点 5 路降级最末路径,请检查 RAG + LLM 双链路")
        else:
            if generation == "template_fallback_from_chunks":
                st.info("ℹ️ LLM 不可用,展示模板兜底回答")

            rag_status = data.get("rag_status", "")
            if rag_status.startswith("unavailable:"):
                st.warning(f"知识库召回降级:{rag_status}")

            # 三段渲染仅 strategy 任务触发(metric/attribution 的 data schema 不同)
            if "recommendations" in data:
                st.divider()
                _render_chunks(data.get("retrieved_chunks", []))
                _render_profile(data.get("merchant_profile", {}))
                _render_recommendations(data.get("recommendations", []))

        st.divider()
        trace_url = _fetch_latest_trace_url()
        if trace_url:
            st.caption(f"🔗 [查看本次调用的完整 trace]({trace_url})")
        else:
            st.caption(
                "🔗 LangSmith trace 暂不可用,请到 "
                "[merchant-copilot project](https://smith.langchain.com) 查看"
            )
