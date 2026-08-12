"""Re-score the frozen, human-labelled v1 calibration corpus with Qwen.

This is deliberately a *judge* calibration, not a v2 quality result: the
Agent answers are the historical DeepSeek-V3 answers that the PM labelled
before the old Qwen-Max score was produced.  Keeping the source Markdown
immutable lets the new fixed Qwen snapshot be compared to independent human
labels without leaking either the old Judge result or v2 runtime output.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.client import capture_usage  # noqa: E402
from evals.judge import judge_client, judge_one  # noqa: E402

SOURCE = ROOT / "evals/runs/calibration_agent_outputs.md"
OUT_DEFAULT = ROOT / "evals/runs/v2_qwen_recalibration_legacy30_20260812.json"
HEADING = re.compile(r"^## \[\d+/30\] (q_\d+).*?\(([^/]+) / ([^)]+)\)", re.M)


def load_records() -> dict[str, dict]:
    """Load the historical frozen 80-query dataset indexed by id."""
    files = [ROOT / "evals/datasets/v1.0/queries.jsonl"] + sorted(
        ROOT.glob("evals/datasets/v1.1/queries_v1.1_round*.jsonl")
    )
    rows: dict[str, dict] = {}
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["id"]] = row
    return rows


def _field(section: str, name: str) -> str:
    match = re.search(rf"^\*\*{re.escape(name)}\*\*: ?(.+)$", section, re.M)
    return match.group(1).strip() if match else ""


def _human_label(section: str, query_type: str) -> str:
    scale = r"0/0\.25/0\.5/0\.75/1\.0" if query_type == "strategy" else r"0/1"
    match = re.search(rf"^\*\*PM 标注\*\* \({scale}\): ?(.+)$", section, re.M)
    return match.group(1).strip() if match else ""


def parse_human_labelled_outputs(source: Path = SOURCE) -> list[dict]:
    """Parse exactly 30 self-contained Markdown records and their PM labels."""
    text = source.read_text(encoding="utf-8")
    headings = list(HEADING.finditer(text))
    parsed: list[dict] = []
    for index, match in enumerate(headings):
        section = text[match.start(): headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        qid, query_type, difficulty = match.group(1), match.group(2).strip(), match.group(3).strip()
        answer_match = re.search(r"\*\*Agent Final Answer\*\*:\s*(.*?)\n\*\*Evidence\*\*:", section, re.S)
        if not answer_match:
            raise ValueError(f"{qid}: missing Agent Final Answer")
        evidence_match = re.search(
            r"\*\*Evidence\*\*:\s*(.*?)(?=\n\*\*(?:RAG 召回 chunks|真值 factual_anchor)\*\*:)",
            section,
            re.S,
        )
        if not evidence_match:
            raise ValueError(f"{qid}: missing Evidence")
        raw_label = _human_label(section, query_type)
        if not raw_label:
            raise ValueError(f"{qid}: missing PM label")
        chunks = _field(section, "RAG 召回 chunks")
        parsed.append({
            "id": qid,
            "query_type": query_type,
            "difficulty": difficulty,
            "human": float(raw_label) if query_type == "strategy" else int(raw_label),
            "agent_output": {
                "final_answer": answer_match.group(1).strip(),
                "evidence": [line[2:].strip() for line in evidence_match.group(1).splitlines() if line.startswith("- ")],
                "retrieved_chunks": [item.strip() for item in chunks.split(";") if item.strip()],
                "node_data": {},
            },
        })
    if len(parsed) != 30 or len({row["id"] for row in parsed}) != 30:
        raise ValueError(f"expected exactly 30 unique labelled records, got {len(parsed)}")
    return parsed


def _usage_total(rows: list[dict]) -> dict[str, int]:
    return {key: sum(int(row["usage"].get(key, 0)) for row in rows)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


def _has_unique_mode(scores: list[float | int]) -> bool:
    counts = Counter(scores)
    return len(counts) == 1 or list(counts.values()).count(max(counts.values())) == 1


def _empty_result(source: Path, client, sample_count: int) -> dict:
    return {
        "source": str(source.relative_to(ROOT)),
        "scope": "legacy human-labelled v1 Agent outputs; judge calibration only, not a v2 quality result",
        "judge_provider": client.provider,
        "judge_model": client.model,
        "sample_count": sample_count,
        "records": [],
    }


def _finish(result: dict) -> dict:
    rows = result["records"]
    binary = [{"id": row["id"], "human": row["human"], "judge": row["judge_mode"]}
              for row in rows if row["query_type"] != "strategy" and row.get("judge_mode") is not None]
    strategy = [{"id": row["id"], "human": row["human"], "judge": row["judge_mode"]}
                for row in rows if row["query_type"] == "strategy" and row.get("judge_mode") is not None]
    result["pairs"] = {"binary": binary, "strategy": strategy}
    result["unresolved_ids"] = [row["id"] for row in rows if row.get("judge_mode") is None]
    result["usage_total"] = _usage_total([{"usage": row["usage"]} for row in rows])
    return result


def run(sample_count: int = 3, source: Path = SOURCE, checkpoint: Path | None = None) -> dict:
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    dataset = load_records()
    parsed = parse_human_labelled_outputs(source)
    client = judge_client()
    result = _empty_result(source, client, sample_count)
    if checkpoint and checkpoint.exists():
        result = json.loads(checkpoint.read_text(encoding="utf-8"))
        if result.get("sample_count") != sample_count or result.get("judge_model") != client.model:
            raise ValueError("checkpoint does not match the requested fixed Judge run")
    rows: list[dict] = result["records"]
    complete_ids = {row["id"] for row in rows}
    for index, item in enumerate(parsed, 1):
        if item["id"] in complete_ids:
            print(f"[{index}/30] {item['id']} checkpointed", flush=True)
            continue
        record = dataset[item["id"]]
        if (record["query_type"], record["difficulty"]) != (item["query_type"], item["difficulty"]):
            raise ValueError(f"{item['id']}: Markdown metadata disagrees with frozen dataset")
        samples, usages = [], []
        for _ in range(sample_count):
            with capture_usage() as usage:
                samples.append(judge_one(record, item["agent_output"], client=client, timeout=90.0))
            usages.extend(usage)
        scores = [sample["score"] for sample in samples]
        score = Counter(scores).most_common(1)[0][0]
        rows.append({
            "id": item["id"], "query_type": item["query_type"], "human": item["human"],
            "judge_scores": scores, "judge_mode": score, "samples": samples,
            "usage": _usage_total(usages),
        })
        if checkpoint:
            checkpoint.write_text(json.dumps(_finish(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{index}/30] {item['id']} {item['query_type']} human={item['human']} judge={scores} mode={score}", flush=True)
    # A three-way split after three samples is not a mode.  Add two samples so
    # a five-sample majority is available, rather than letting Counter's input
    # order silently choose a score.
    parsed_by_id = {item["id"]: item for item in parsed}
    for row in rows:
        if _has_unique_mode(row["judge_scores"]):
            continue
        item = parsed_by_id[row["id"]]
        record = dataset[row["id"]]
        for _ in range(2):
            with capture_usage() as usage:
                sample = judge_one(record, item["agent_output"], client=client, timeout=90.0)
            row["samples"].append(sample)
            row["judge_scores"].append(sample["score"])
            row["usage"] = _usage_total([{"usage": row["usage"]}, *({"usage": entry} for entry in usage)])
        if not _has_unique_mode(row["judge_scores"]):
            row["judge_mode"] = None
            row["mode_status"] = "unresolved_after_five_samples"
        else:
            row["judge_mode"] = Counter(row["judge_scores"]).most_common(1)[0][0]
            row["mode_status"] = "resolved_after_five_samples"
        if checkpoint:
            checkpoint.write_text(json.dumps(_finish(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[tie-handled] {row['id']} judge={row['judge_scores']} mode={row['judge_mode']} status={row['mode_status']}", flush=True)
    return _finish(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    result = run(sample_count=args.samples, checkpoint=args.out)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "usage_total": result["usage_total"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
