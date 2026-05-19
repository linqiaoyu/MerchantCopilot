"""Strategy 节点:策略建议。

阶段 2 是骨架:返回按问题关键词命中的硬编码模板,
不接 RAG / 不接 Mem0(留阶段 4)。Memory 先用一个 dict 占位。
真实组件在阶段 4 从下方标注的两个接入口接入,**此处只留注释,不预先抽象接口**。
"""
from __future__ import annotations

from app.agent.state import AgentState

# --- Memory 占位(阶段 4 替换为 Mem0 商家画像 merchant_memory.get_profile()) ---
# 字段对齐 CLAUDE.md 简历映射要求:至少 类目 / 主力客群 / 风格偏好
_MERCHANT_PROFILE = {
    "category": "女装(中端,主力价格带 ¥100-300)",
    "audience": "18-24 学生 + 25-30 职场新人(student/young_pro 约 85%)",
    "streamers": "小张(午场)、小李(工作日晚场)",
}

# 硬编码策略模板:阶段 4 这些 recommendations 改为 RAG 召回知识库 + LLM 改写
_TEMPLATES = [
    {
        "match": ["投流", "付费", "泛流量", "roi", "投放", "推广"],
        "topic": "付费投流效率优化",
        "recommendations": [
            "收紧投流定向:按主力客群(学生/职场新人 + 女装中端价格带)做人群包,减少泛流量灌入",
            "设单量级 ROI 红线,转化率连续低于自然流量 1/3 时自动降预算",
            "投流流量单独承接:用高性价比引流款做钩子,而非直接推高客单单品",
        ],
    },
    {
        "match": ["退款", "退货", "质量", "色差", "差评"],
        "topic": "新品质量与退款管控",
        "recommendations": [
            "新品上架首 3 天小批量试卖,退款率 >15% 立即下架复查",
            "针织/真丝类重点做色差质检与实拍比对,主图标注真实色卡",
            "退款原因按 SKU 日监控,单品「色差/质量」占比超 50% 触发预警",
        ],
    },
    {
        "match": ["选品", "客群", "错配", "高端", "高客单", "人货"],
        "topic": "选品与客群匹配",
        "recommendations": [
            "主推位锚定主力客群价格带(¥100-300),高客单单品不占当日唯一主推",
            "高端/成熟向单品单独排专场,避免与学生/职场新人主场客群对冲",
            "上新前用历史同价位带转化率预估,低于基线 50% 不进主推",
        ],
    },
]

_DEFAULT = {
    "topic": "综合经营建议",
    "recommendations": [
        "盯住转化率与退款率两个核心健康度指标,偏离基线及时下钻归因",
        "选品与排播紧扣主力客群(学生 + 职场新人,女装中端)",
        "大促/上新前先做小规模验证,再放量",
    ],
}


def _pick_template(query: str) -> dict:
    q = query.lower()
    for tpl in _TEMPLATES:
        if any(kw in q for kw in tpl["match"]):
            return tpl
    return _DEFAULT


def strategy(state: AgentState) -> dict:
    # 阶段 4 接入口①:此处用 RAG retriever 按 query 召回知识库 chunk
    # 阶段 4 接入口②:此处用 Mem0 取商家画像替换 _MERCHANT_PROFILE
    profile = _MERCHANT_PROFILE
    tpl = _pick_template(state["user_query"])

    headline = f"策略建议:{tpl['topic']}(基于商家画像生成)"
    data = {
        "topic": tpl["topic"],
        "recommendations": tpl["recommendations"],
        "merchant_profile": profile,
        "source": "stage2-hardcoded-template",  # 阶段4 改为 "rag+memory"
    }
    evidence = [
        f"商家画像:{profile['category']};主力客群 {profile['audience']}",
        "建议来源:阶段 2 硬编码模板(阶段 4 将由 BGE-M3 RAG 召回知识库 + Mem0 画像支撑)",
    ]
    result = {"task": "strategy", "headline": headline,
              "data": data, "evidence": evidence}
    step = {"node": "Strategy", "summary": headline, "data": data}
    return {"node_result": result, "steps": [step]}
