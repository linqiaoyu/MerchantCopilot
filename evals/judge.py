"""LLM-as-judge — 6.2 calibration 用(judge 实现,本轮 step 1 交付,step 4 才跑)。

判分契约(从 ANNOTATION_SOP.md §8.2 推出,详见 calibration_sampling.md §6):
  - judge 对每条输出 4 个维度各 0/1 + 简短理由,按 query_type 聚合:
    * strategy           → mean(4 维) ∈ {0,0.25,0.5,0.75,1.0} 连续值
    * data_query/cross_period/attribution → AND(该类 SOP §8.2 判据) → binary 0/1
  - 4 维:factual_accuracy / grounding_to_context / actionability / strategy_relevance

judge 模型:Qwen-Max(不同家于被测 DeepSeek-V3,降 self-eval;零新 key/依赖,
  复用 app/llm/client.LLMClient)。provider 可配 —— 若 PM 改用 GPT/Gemini,
  在 _PROVIDERS 加配置 + .env 加 key,judge_client(provider=...) 一行切换。

⚠️ 标注独立性(DESIGN.md §5):judge 不得在 PM 标完 30 条前跑(避免 anchor)。
  本模块 step 1 只交付实现,step 4(PM 标注后)才调用 run_judge。
"""
from __future__ import annotations

import json
import os

from app.llm.client import _PROVIDERS, LLMClient, _load_dotenv

_load_dotenv()

JUDGE_PROVIDER_DEFAULT = "qwen"  # 不同家于被测 DeepSeek;PM 可改 GPT/Gemini

# 4 个固定评分维度(v1 锁,PM 6.2 opening prompt)
DIMENSIONS = ("factual_accuracy", "grounding_to_context", "actionability", "strategy_relevance")


def judge_client(provider: str = JUDGE_PROVIDER_DEFAULT) -> LLMClient:
    """构造 judge LLM client(强制指定 provider,不走 get_llm 的 DeepSeek 优先)。"""
    if provider not in _PROVIDERS:
        raise ValueError(f"未知 judge provider: {provider}(可选 {list(_PROVIDERS)})")
    cfg = _PROVIDERS[provider]
    key = os.environ.get(cfg["key_env"], "").strip()
    if not key:
        raise RuntimeError(
            f"judge provider={provider} 缺 {cfg['key_env']}。"
            f"Qwen-Max 是零新依赖默认选择;若用 GPT/Gemini 需先在 .env 配 key + _PROVIDERS 加配置。"
        )
    base = os.environ.get(cfg["base_env"], "").strip() or cfg["base_default"]
    return LLMClient(provider, key, base, cfg["model"])


# ---- 按 query_type 的判据(SOP §8.2)写进 judge system prompt ----

_RUBRIC_BY_TYPE = {
    "data_query": (
        "【data_query 判据(SOP §8.2,binary)】全部满足才 pass=1:\n"
        "1. factual_accuracy:LLM 答的数字与 factual_anchor SQL 真值相对差 ≤ ±10%(允许 mock 噪声)\n"
        "2. strategy_relevance(此处复用为「字段对齐」):LLM 提到的维度(主播/子品类/traffic_source 等)与 query 要求一致;"
        "   若 query 要求 group by 某维度而 LLM 返回合并总数(未拆分)→ 此维度判 0(group by silent failure)\n"
        "3. grounding_to_context(此处复用为「时间窗对齐」):LLM 取的日期范围与 query 指定一致(差 1 天容忍)\n"
        "4. actionability:data_query 不强制建议条数,默认 1(不作扣分项)\n"
    ),
    "cross_period": (
        "【cross_period 判据(SOP §8.2,同 data_query,binary)】全部满足才 pass=1:\n"
        "1. factual_accuracy:数字与 factual_anchor SQL 真值相对差 ≤ ±10%\n"
        "2. strategy_relevance(字段对齐):跨期对比的各时间段维度与 query 一致\n"
        "3. grounding_to_context(时间窗对齐):LLM 是否正确解析多段时间窗;"
        "   若 LLM 把跨期 query 默认到单日/数据集最新日 → 判 0(时间窗解析短板)\n"
        "4. actionability:默认 1\n"
    ),
    "attribution": (
        "【attribution 判据(SOP §8.2 + §3.2 behavior alignment,binary)】全部满足才 pass=1:\n"
        "评分依据是 node_result 的 evidence/data 里 SQL drill-down 输出字段,**不看 RAG chunks**"
        "(attribution 节点架构上不走 RAG)。\n"
        "1. factual_accuracy:LLM 至少正确引用 1 个 factual_anchor 关键数字(相对差 ≤ ±10%)\n"
        "2. strategy_relevance(根因识别):归因结论与 factual_anchor 根因主信号一致"
        "(case1 人货错配/转化率断崖;case2 付费投流泛流量;case3 P_C3 色差)\n"
        "3. grounding_to_context(维度覆盖):答案涵盖 expected_strategy_dimensions 至少 1 个,"
        "且可追溯到对应 SQL drill-down 分支\n"
        "4. actionability:归因可附 1 条修复建议,默认 1\n"
        "注:跨 case 对比 / 诱导式模糊 query 若节点走 unknown 兜底「未匹配已知异常,已交人工」,"
        "这是设计正确的兜底(不臆造归因),但相对 factual_anchor 的具体根因未命中 → 仍判 fail。\n"
    ),
    "strategy": (
        "【strategy 判据(SOP §8.2 + §3.1 content alignment,连续值)】4 维各 0/1,score=mean(4维):\n"
        "评分依据含 retrieved_chunks(RAG content alignment)。\n"
        "1. factual_accuracy:无 hallucination —— 不编造 fact 表不存在的数字"
        "(如与本 query 无关却说「转化率 4.2%→1.1%」)。无编造=1\n"
        "2. grounding_to_context:至少 1 个建议可追溯到 must_cite_rag_doc_slugs 白名单内某篇 KB"
        "(retrieved_chunks 命中 ≥1 即可)。命中=1\n"
        "   ★ 若本条 query 是 q_014:忽略死字段 category_specific-spring-window"
        "(RAG 不读 Mem0 永远召不回),只判 follow-up 题面对应 KB 是否命中(DESIGN.md §8)\n"
        "3. actionability:可执行建议条数 ≥ expected_action_count。达标=1\n"
        "4. strategy_relevance:答案覆盖 expected_strategy_dimensions ≥ ceil(N/2) 个。达标=1\n"
        "   ★ 半干净 paired(题面 broad,画像层客群/价格带充斥):仍按 expected_dimensions 判覆盖,"
        "不因画像描述多就加分\n"
    ),
}

_JUDGE_SYSTEM_TEMPLATE = (
    "你是直播电商经营分析 Agent 的评测裁判。被测 Agent 用 DeepSeek-V3;你用不同家模型,客观评分。\n"
    "针对单条 query,依据下面的判据,对 4 个维度逐一判 0 或 1,并给一句中文理由。\n\n"
    "{rubric}\n"
    "【输出格式】严格输出一个 JSON(不要 ```包裹,不要多余文字):\n"
    '{{"factual_accuracy": {{"score": 0或1, "reason": "..."}}, '
    '"grounding_to_context": {{"score": 0或1, "reason": "..."}}, '
    '"actionability": {{"score": 0或1, "reason": "..."}}, '
    '"strategy_relevance": {{"score": 0或1, "reason": "..."}}}}\n'
)


def build_judge_system(query_type: str) -> str:
    rubric = _RUBRIC_BY_TYPE[query_type]
    return _JUDGE_SYSTEM_TEMPLATE.format(rubric=rubric)


def build_judge_user(record: dict, agent_output: dict) -> str:
    """把 query + Agent 输出 + 真值 + rubric 组装成 judge 的 user payload。"""
    gt = record.get("ground_truth", {})
    payload = {
        "query": record["query"],
        "query_type": record["query_type"],
        "difficulty": record["difficulty"],
        "factual_anchor": gt.get("factual_anchor"),
        "expected_strategy_dimensions": gt.get("expected_strategy_dimensions", []),
        "must_cite_rag_doc_slugs": gt.get("must_cite_rag_doc_slugs", []),
        "expected_action_count": gt.get("expected_action_count"),
        "rubric_notes": record.get("rubric_notes", ""),
        "agent_final_answer": agent_output.get("final_answer", ""),
        "agent_evidence": agent_output.get("evidence", []),
        # strategy 给 judge 看 RAG 召回;attribution/metric 不给(架构上无 RAG)
        "agent_retrieved_chunks": agent_output.get("retrieved_chunks", []),
        "agent_node_data": agent_output.get("node_data", {}),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def aggregate_score(query_type: str, dims: dict) -> dict:
    """4 维 0/1 → 按 query_type 聚合。返回 {score, verdict, scoring_mode}。"""
    vals = {d: int(dims[d]["score"]) for d in DIMENSIONS}
    if query_type == "strategy":
        score = sum(vals.values()) / 4.0  # ∈ {0,0.25,0.5,0.75,1.0}
        return {"score": score, "verdict": None, "scoring_mode": "continuous"}
    # data_query / cross_period / attribution:AND → binary
    # actionability 默认不作硬否决(各类判据里 actionability 已设默认 1)
    hard = ("factual_accuracy", "grounding_to_context", "strategy_relevance")
    pass_ = all(vals[d] == 1 for d in hard)
    return {"score": int(pass_), "verdict": "pass" if pass_ else "fail",
            "scoring_mode": "binary"}


def judge_one(record: dict, agent_output: dict, provider: str = JUDGE_PROVIDER_DEFAULT,
              client: LLMClient | None = None) -> dict:
    """评一条。返回 {dimensions, score, verdict, scoring_mode, judge_provider}。

    ⚠️ 仅 step 4(PM 标完)调用。
    """
    cli = client or judge_client(provider)
    qtype = record["query_type"]
    system = build_judge_system(qtype)
    user = build_judge_user(record, agent_output)
    raw = cli.chat(system=system, user=user, temperature=0.0)
    raw_stripped = raw.strip()
    if raw_stripped.startswith("```"):
        raw_stripped = raw_stripped.strip("`")
        if raw_stripped.lower().startswith("json"):
            raw_stripped = raw_stripped[4:].lstrip()
    dims = json.loads(raw_stripped)
    agg = aggregate_score(qtype, dims)
    return {
        "id": record["id"],
        "query_type": qtype,
        "dimensions": dims,
        **agg,
        "judge_provider": cli.provider,
        "judge_model": cli.model,
    }


def run_judge(records: list[dict], agent_outputs: dict[str, dict],
              provider: str = JUDGE_PROVIDER_DEFAULT) -> list[dict]:
    """批量评分(step 4)。agent_outputs: {qid: {final_answer, evidence, ...}}。"""
    cli = judge_client(provider)
    results = []
    for rec in records:
        out = agent_outputs.get(rec["id"])
        if out is None:
            raise KeyError(f"缺 {rec['id']} 的 Agent 输出")
        results.append(judge_one(rec, out, client=cli))
    return results
