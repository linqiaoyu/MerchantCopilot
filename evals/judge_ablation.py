"""6.3 judge 跑批 — binary 三类(full + baseline),每条 3 次取众数(方法论 13)。

只评 binary 三类(data_query/attribution/cross_period,judge α=0.856 可信);
strategy 50 的画像锚定是 CC 人工判(做法 Y),不在此脚本。

用法:python evals/judge_ablation.py
输入:evals/runs/ablation_6_3_outputs.json(full + baseline 的 Agent 输出)
输出:evals/runs/ablation_6_3_judge.json
"""
from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.judge import judge_client, judge_one  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/runs/ablation_6_3_outputs.json"
JUDGE_OUT = ROOT / "evals/runs/ablation_6_3_judge.json"
N_SAMPLE = 3


def load_dataset():
    files = [ROOT / "evals/datasets/v1.0/queries.jsonl"] + sorted(
        ROOT.glob("evals/datasets/v1.1/queries_v1.1_round*.jsonl"))
    by_id = {}
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                r = json.loads(line)
                by_id[r["id"]] = r
    return by_id


def judge_3x(rec, agent_output, cli):
    scores, samples = [], []
    for _ in range(N_SAMPLE):
        res = judge_one(rec, agent_output, client=cli)
        scores.append(int(res["score"]))
        samples.append({"score": int(res["score"]),
                        "dims": {d: res["dimensions"][d]["score"] for d in res["dimensions"]}})
    mode = Counter(scores).most_common(1)[0][0]
    return {"mode_score": mode, "samples_scores": scores, "samples": samples}


def main():
    by_id = load_dataset()
    out = json.loads(OUT.read_text(encoding="utf-8"))
    cli = judge_client()  # Qwen-Max
    binary_types = ("data_query", "attribution", "cross_period")
    binary_ids = sorted([qid for qid, r in by_id.items() if r["query_type"] in binary_types])
    print(f"binary 三类 {len(binary_ids)} 条 × 2 配置(full/baseline)× {N_SAMPLE} 次 judge...")

    result = json.loads(JUDGE_OUT.read_text(encoding="utf-8")) if JUDGE_OUT.exists() else {"full": {}, "baseline": {}}
    for cfg in ("full", "baseline"):
        for i, qid in enumerate(binary_ids, 1):
            if qid in result[cfg]:
                continue
            ao = out[cfg].get(qid)
            if ao is None or "error" in ao:
                result[cfg][qid] = {"error": "无 Agent 输出"}
                JUDGE_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                continue
            rec = by_id[qid]
            try:
                result[cfg][qid] = {**judge_3x(rec, ao, cli), "query_type": rec["query_type"]}
            except Exception as e:
                result[cfg][qid] = {"error": f"{type(e).__name__}: {e}"}
            JUDGE_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  [{cfg} {i}/{len(binary_ids)}] {qid} ({rec['query_type']}) "
                  f"mode={result[cfg][qid].get('mode_score')} samples={result[cfg][qid].get('samples_scores')}")
    print(f"\n完成。输出 {JUDGE_OUT}")


if __name__ == "__main__":
    main()
