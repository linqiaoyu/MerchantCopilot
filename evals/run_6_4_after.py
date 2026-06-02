"""6.4 after 回归 — 10 条 bad case(task #26 修复后)跑 graph + judge 3 次众数。

before=0%(6.3 full 实测 10/10 fail)→ after=Y%。McNemar(asymmetric,before saturated 0)。
10 条:q_023-028(6 group-by)+ q_066-069(4 cross_period)。

用法:python evals/run_6_4_after.py
输出:evals/runs/stage6_4_after.json
"""
from __future__ import annotations

import glob
import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.judge import judge_client, judge_one  # noqa: E402

QIDS = ["q_023", "q_024", "q_025", "q_026", "q_027", "q_028",
        "q_066", "q_067", "q_068", "q_069"]
OUT = ROOT / "evals/runs/stage6_4_after.json"
N_SAMPLE = 3


def load_dataset():
    files = [ROOT / "evals/datasets/v1.0/queries.jsonl"] + sorted(
        ROOT.glob("evals/datasets/v1.1/queries_v1.1_round*.jsonl"))
    by_id = {}
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                r = json.loads(line); by_id[r["id"]] = r
    return by_id


def extract_output(state):
    nr = state.get("node_result") or {}
    data = nr.get("data", {}) or {}
    return {"final_answer": state.get("final_answer", ""), "evidence": nr.get("evidence", []),
            "retrieved_chunks": [], "node_data": data, "task": nr.get("task")}


def main():
    from app.agent.graph import build_graph
    by_id = load_dataset()
    graph = build_graph()
    cli = judge_client()
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for i, qid in enumerate(QIDS, 1):
        if qid in res and "error" not in res[qid]:
            print(f"  [{i}/10] {qid} 已存在,跳过"); continue
        rec = by_id[qid]
        t0 = time.time()
        try:
            st = graph.invoke({"user_query": rec["query"]})
            ao = extract_output(st)
            scores = []
            for _ in range(N_SAMPLE):
                scores.append(int(judge_one(rec, ao, client=cli)["score"]))
            mode = Counter(scores).most_common(1)[0][0]
            res[qid] = {"query_type": rec["query_type"], "final_answer": ao["final_answer"],
                        "evidence": ao["evidence"], "node_data": ao["node_data"],
                        "mode_score": mode, "samples_scores": scores, "_sec": round(time.time() - t0, 1)}
        except Exception as e:
            res[qid] = {"error": f"{type(e).__name__}: {e}"}
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{i}/10] {qid} ({rec['query_type']}) mode={res[qid].get('mode_score')} "
              f"samples={res[qid].get('samples_scores')} {res[qid].get('_sec','')}s")

    # McNemar before(全0)→ after
    after = [res[q]["mode_score"] for q in QIDS if "mode_score" in res[q]]
    c = sum(after)          # before=0 & after=1(修好的)
    d = len(after) - c      # before=0 & after=0(仍 fail)
    chi2 = (c * c) / c if c else 0.0
    chi2_cc = ((abs(c) - 1) ** 2) / c if c else 0.0
    print(f"\n=== 6.4 before(0%)→ after McNemar(asymmetric,before saturated 0)===")
    print(f"  after 通过 {c}/{len(after)} = {round(100*c/len(after),1)}%  (before=0%)")
    print(f"  b=0 c(修好)={c} d(仍fail)={d}  χ²={chi2}(连续校正{round(chi2_cc,2)}) 显著(≥3.841)={chi2>=3.841}")
    print(f"  通过条:{[q for q in QIDS if res.get(q,{}).get('mode_score')==1]}")
    print(f"  仍fail:{[q for q in QIDS if res.get(q,{}).get('mode_score')==0]}")


if __name__ == "__main__":
    main()
