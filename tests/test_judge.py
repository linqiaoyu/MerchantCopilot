import json

from evals.judge import judge_one


class _TrailingTextClient:
    provider = "qwen_judge"
    model = "qwen3.7-plus-2026-05-26"

    def chat(self, **_kwargs):
        return json.dumps({
            "factual_accuracy": {"score": 1, "reason": "ok"},
            "grounding_to_context": {"score": 1, "reason": "ok"},
            "actionability": {"score": 1, "reason": "ok"},
            "strategy_relevance": {"score": 1, "reason": "ok"},
        }) + "\n补充说明"


def test_judge_accepts_one_json_object_followed_by_provider_prose():
    record = {"id": "q", "query_type": "data_query", "query": "q", "difficulty": "simple", "ground_truth": {}}
    result = judge_one(record, {"final_answer": "a"}, client=_TrailingTextClient())
    assert result["score"] == 1
