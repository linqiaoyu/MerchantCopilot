"""6.3 McNemar 分析 — 两主线。

主线 2(系统 vs 裸 LLM):full vs baseline binary 通过率,McNemar n=30。
主线 1(Memory 价值):full vs -Mem0 画像锚定率,McNemar n=50(读 CC 人工判文件)。

用法:python evals/analyze_ablation.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mcnemar(pairs):
    """pairs: list of (cond_pass_A, cond_pass_B) binary。A=full/有, B=ablation/无。
    返回 2x2 + χ²(无连续性校正,asymmetric)+ b/c。"""
    a = sum(1 for x, y in pairs if x == 1 and y == 1)
    b = sum(1 for x, y in pairs if x == 1 and y == 0)  # A pass, B fail(discordant 关键)
    c = sum(1 for x, y in pairs if x == 0 and y == 1)
    d = sum(1 for x, y in pairs if x == 0 and y == 0)
    n = len(pairs)
    bc = b + c
    chi2 = ((b - c) ** 2) / bc if bc > 0 else 0.0
    # 连续性校正版(小样本更稳)
    chi2_cc = ((abs(b - c) - 1) ** 2) / bc if bc > 0 else 0.0
    pA = (a + b) / n if n else 0
    pB = (a + c) / n if n else 0
    return {"n": n, "a": a, "b": b, "c": c, "d": d, "chi2": round(chi2, 3),
            "chi2_cc": round(chi2_cc, 3), "p_A": round(pA, 3), "p_B": round(pB, 3),
            "sig_0.05": bc > 0 and chi2 >= 3.841, "sig_cc": bc > 0 and chi2_cc >= 3.841}


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


def main_line_2():
    jp = ROOT / "evals/runs/ablation_6_3_judge.json"
    if not jp.exists():
        print("[主线2] 缺 judge 输出,跳过"); return
    j = json.loads(jp.read_text(encoding="utf-8"))
    by_id = load_dataset()
    ids = sorted(set(j["full"]) & set(j["baseline"]))
    pairs, by_type = [], {}
    for qid in ids:
        f, b = j["full"][qid], j["baseline"][qid]
        if "error" in f or "error" in b:
            continue
        pf, pb = f["mode_score"], b["mode_score"]
        pairs.append((pf, pb))
        t = by_id[qid]["query_type"]
        by_type.setdefault(t, []).append((qid, pf, pb))
    print("\n=== 主线 2:full(系统)vs baseline(裸LLM)binary 通过率 ===")
    m = mcnemar(pairs)
    print(f"  n={m['n']}  full通过率={m['p_A']}  裸LLM通过率={m['p_B']}")
    print(f"  2x2: a(双pass)={m['a']} b(full✓裸✗)={m['b']} c(full✗裸✓)={m['c']} d(双fail)={m['d']}")
    print(f"  χ²={m['chi2']} (连续校正 {m['chi2_cc']})  显著(>3.841)={m['sig_0.05']} / 校正后={m['sig_cc']}")
    print("  --- discordant 来源拆解(按 query_type)---")
    for t, lst in by_type.items():
        bb = sum(1 for _, pf, pb in lst if pf == 1 and pb == 0)
        cc = sum(1 for _, pf, pb in lst if pf == 0 and pb == 1)
        dd = sum(1 for _, pf, pb in lst if pf == 0 and pb == 0)
        aa = sum(1 for _, pf, pb in lst if pf == 1 and pb == 1)
        print(f"    {t}: n={len(lst)} a={aa} b={bb} c={cc} d={dd}  "
              f"discordant(b)条={[q for q,pf,pb in lst if pf==1 and pb==0]}")


def main_line_1():
    ap = ROOT / "evals/runs/ablation_6_3_anchoring.json"
    if not ap.exists():
        print("\n[主线1] 缺画像锚定人工判文件 ablation_6_3_anchoring.json,跳过"); return
    anc = json.loads(ap.read_text(encoding="utf-8"))
    pairs = []
    for qid, v in anc.items():
        if qid.startswith("_"):
            continue
        pairs.append((int(v["full"]), int(v["minus_mem0"])))
    print("\n=== 主线 1:full vs -Mem0 常驻画像锚定率(CC 人工判,n=50)===")
    m = mcnemar(pairs)
    print(f"  n={m['n']}  full锚定率={m['p_A']}  -Mem0锚定率={m['p_B']}")
    print(f"  2x2: a(双锚定)={m['a']} b(full锚✓ -Mem0✗)={m['b']} c={m['c']} d={m['d']}")
    print(f"  χ²={m['chi2']} (连续校正 {m['chi2_cc']})  显著={m['sig_0.05']} / 校正后={m['sig_cc']}")


if __name__ == "__main__":
    main_line_2()
    main_line_1()
