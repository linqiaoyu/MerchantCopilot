"""6.3 消融 runner — 三配置 × 双批次(预注册见 ablation_6_3_preregister.md)。

配置(eval-side,不改 app/ 契约):
  full      : 原样 build_graph().invoke
  minus_mem0: monkeypatch strategy.get_profile → 空 profile(RAG 不动)
  baseline  : 裸 LLM,直调 DeepSeek + 最小公平 prompt,无 graph/MCP/RAG/Mem0

双批次(§12):
  full 批 A : delete_all(Mem0) 一次 → seed → 顺序连跑 64 非 paired
  full 批 B : per-pair 进程内隔离 —— delete_all → 前置 → sleep5 → follow-up
              (delete_all 进程内可靠重置,实测验证;保持 RAG/Mem0 模型热)
  minus_mem0: 单趟连跑 50 strategy(Mem0 off 无需隔离)
  baseline  : 30 binary 三类,每条独立无状态

用法:
  python evals/run_ablation.py full_a
  python evals/run_ablation.py full_b
  python evals/run_ablation.py minus_mem0
  python evals/run_ablation.py baseline
  python evals/run_ablation.py all
输出增量写 evals/runs/ablation_6_3_outputs.json,可断点续跑。
"""
from __future__ import annotations

import glob
import json
import re
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "evals" / "runs" / "ablation_6_3_outputs.json"

FAIR_BASELINE_SYSTEM = (
    "你是直播电商经营分析助手。商家「小张」经营一家中端女装直播间,"
    "主要客群是 18-24 岁学生和 25-30 岁职场新人。"
    "请基于你的电商经营知识回答商家的问题。"
)

PRE = re.compile(r"前置\s*query[::]\s*(q_\d+)")


def load_dataset() -> tuple[list[dict], dict]:
    files = [ROOT / "evals/datasets/v1.0/queries.jsonl"] + sorted(
        ROOT.glob("evals/datasets/v1.1/queries_v1.1_round*.jsonl")
    )
    rows = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    by_id = {r["id"]: r for r in rows}
    return rows, by_id


def prereq_of(rec: dict) -> str | None:
    m = PRE.search(rec.get("rubric_notes", "") or "")
    return m.group(1) if m else None


def split_subsets(rows: list[dict]) -> dict:
    binary3 = [r for r in rows if r["query_type"] in ("data_query", "attribution", "cross_period")]
    strat = [r for r in rows if r["query_type"] == "strategy"]
    paired = [(r["id"], prereq_of(r)) for r in strat if prereq_of(r)]
    np_strat = [r for r in strat if not prereq_of(r)]
    return {
        "binary3": binary3,
        "strategy_all": strat,
        "strategy_np": np_strat,
        "paired": paired,  # [(followup_id, prereq_id)]
    }


def extract_output(state: dict) -> dict:
    nr = state.get("node_result") or {}
    data = nr.get("data", {}) or {}
    return {
        "final_answer": state.get("final_answer", ""),
        "evidence": nr.get("evidence", []),
        "retrieved_chunks": data.get("retrieved_chunks", []),
        "node_data": {k: v for k, v in data.items()},
        "task": nr.get("task"),
        "intent": state.get("intent"),
    }


def load_out() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {"full": {}, "minus_mem0": {}, "baseline": {}, "_meta": {}}


def save_out(out: dict) -> None:
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- full 批 A ----------------
def run_full_batch_A(rows, by_id, out):
    from app.agent.graph import build_graph
    from app.memory.merchant_memory import get_client, get_profile, MERCHANT_ID

    subsets = split_subsets(rows)
    # 批 A = 30 binary + 34 非 paired strategy,按 qid 顺序
    batch_a = sorted(subsets["binary3"] + subsets["strategy_np"], key=lambda r: r["id"])
    print(f"[full 批A] {len(batch_a)} 条,清空 Mem0 + seed...")
    get_client().delete_all(user_id=MERCHANT_ID)
    time.sleep(1)
    get_profile(MERCHANT_ID)  # auto-seed 3 事实
    graph = build_graph()
    for i, rec in enumerate(batch_a, 1):
        qid = rec["id"]
        if qid in out["full"]:
            print(f"  [{i}/{len(batch_a)}] {qid} 已存在,跳过")
            continue
        t0 = time.time()
        try:
            st = graph.invoke({"user_query": rec["query"]})
            out["full"][qid] = {**extract_output(st), "batch": "A", "_sec": round(time.time() - t0, 1)}
        except Exception as e:
            out["full"][qid] = {"error": f"{type(e).__name__}: {e}", "batch": "A"}
        save_out(out)
        print(f"  [{i}/{len(batch_a)}] {qid} ({rec['query_type']}) {round(time.time()-t0,1)}s")


# ---------------- full 批 B(per-pair 进程内隔离) ----------------
def run_full_batch_B(rows, by_id, out):
    from app.agent.graph import build_graph
    from app.memory.merchant_memory import get_client, get_profile, MERCHANT_ID

    subsets = split_subsets(rows)
    pairs = subsets["paired"]
    graph = build_graph()
    print(f"[full 批B] {len(pairs)} 对 paired,per-pair 进程内隔离(delete_all)...")
    for i, (fu_id, pre_id) in enumerate(pairs, 1):
        if fu_id in out["full"] and out["full"][fu_id].get("batch") == "B":
            print(f"  [{i}/{len(pairs)}] {fu_id}<-{pre_id} follow-up 已存在,跳过")
            continue
        pre_rec = by_id.get(pre_id)
        fu_rec = by_id[fu_id]
        if pre_rec is None:
            out["full"][fu_id] = {"error": f"前置 {pre_id} 不在 dataset", "batch": "B"}
            save_out(out); continue
        # 隔离:清空 → seed → 前置 → sleep5 → follow-up
        get_client().delete_all(user_id=MERCHANT_ID)
        time.sleep(1)
        get_profile(MERCHANT_ID)
        try:
            graph.invoke({"user_query": pre_rec["query"]})  # 前置写 recent_concern
            time.sleep(5)  # Mem0 写延迟(SOP §8.3)
            st = graph.invoke({"user_query": fu_rec["query"]})
            rc = st.get("node_result", {}).get("data", {}).get("merchant_profile", {}).get("recent_concerns", [])
            out["full"][fu_id] = {**extract_output(st), "batch": "B", "prereq": pre_id,
                                  "recent_concerns_at_run": rc}
        except Exception as e:
            out["full"][fu_id] = {"error": f"{type(e).__name__}: {e}", "batch": "B", "prereq": pre_id}
        save_out(out)
        print(f"  [{i}/{len(pairs)}] {fu_id}<-{pre_id} done")


# ---------------- -Mem0(monkeypatch) ----------------
def run_minus_mem0(rows, by_id, out):
    import app.agent.nodes.strategy as strat_mod

    EMPTY = {"category": "", "audience": "", "style": "", "recent_concerns": []}
    strat_mod.get_profile = lambda *a, **k: dict(EMPTY)
    strat_mod.update_recent_concerns = lambda *a, **k: None  # -Mem0:完全不碰 Mem0
    from app.agent.graph import build_graph

    subsets = split_subsets(rows)
    strat = sorted(subsets["strategy_all"], key=lambda r: r["id"])
    graph = build_graph()
    print(f"[-Mem0] {len(strat)} strategy,monkeypatch get_profile→空,单趟连跑...")
    for i, rec in enumerate(strat, 1):
        qid = rec["id"]
        if qid in out["minus_mem0"]:
            print(f"  [{i}/{len(strat)}] {qid} 已存在,跳过"); continue
        t0 = time.time()
        try:
            st = graph.invoke({"user_query": rec["query"]})
            mp = st.get("node_result", {}).get("data", {}).get("merchant_profile", {})
            out["minus_mem0"][qid] = {**extract_output(st),
                                      "_profile_empty_check": {k: mp.get(k, "") for k in ("category", "audience")},
                                      "_sec": round(time.time() - t0, 1)}
        except Exception as e:
            out["minus_mem0"][qid] = {"error": f"{type(e).__name__}: {e}"}
        save_out(out)
        print(f"  [{i}/{len(strat)}] {qid} {round(time.time()-t0,1)}s")


# ---------------- baseline 裸 LLM ----------------
def run_baseline(rows, by_id, out):
    from app.llm.client import get_llm

    subsets = split_subsets(rows)
    binary3 = sorted(subsets["binary3"], key=lambda r: r["id"])
    llm = get_llm()
    assert not llm.is_stub, "裸 LLM baseline 需要真实 DeepSeek key"
    print(f"[baseline 裸LLM] {len(binary3)} binary 三类,最小公平 prompt 直调 DeepSeek...")
    for i, rec in enumerate(binary3, 1):
        qid = rec["id"]
        if qid in out["baseline"]:
            print(f"  [{i}/{len(binary3)}] {qid} 已存在,跳过"); continue
        t0 = time.time()
        try:
            ans = llm.chat(system=FAIR_BASELINE_SYSTEM, user=rec["query"], temperature=0.0, timeout=40)
            out["baseline"][qid] = {"final_answer": ans, "evidence": [], "retrieved_chunks": [],
                                    "node_data": {}, "task": rec["query_type"],
                                    "_sec": round(time.time() - t0, 1)}
        except Exception as e:
            out["baseline"][qid] = {"error": f"{type(e).__name__}: {e}"}
        save_out(out)
        print(f"  [{i}/{len(binary3)}] {qid} ({rec['query_type']}) {round(time.time()-t0,1)}s")


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    rows, by_id = load_dataset()
    out = load_out()
    out["_meta"]["fair_baseline_system"] = FAIR_BASELINE_SYSTEM
    if phase in ("full_a", "all"):
        run_full_batch_A(rows, by_id, out)
    if phase in ("full_b", "all"):
        run_full_batch_B(rows, by_id, out)
    if phase in ("minus_mem0", "all"):
        run_minus_mem0(rows, by_id, out)
    if phase in ("baseline", "all"):
        run_baseline(rows, by_id, out)
    save_out(out)
    print(f"\n完成 phase={phase}。输出 {OUT_PATH}")
    print(f"  full={len(out['full'])} / minus_mem0={len(out['minus_mem0'])} / baseline={len(out['baseline'])}")


if __name__ == "__main__":
    main()
