from evals.run_v2_qwen_recalibration import _has_unique_mode, load_records, parse_human_labelled_outputs
from evals.analyze_v2_qwen_recalibration import analyze


def test_legacy_calibration_parser_has_complete_independent_pairs():
    rows = parse_human_labelled_outputs()
    assert len(rows) == 30
    assert [row["id"] for row in rows[:3]] == ["q_001", "q_021", "q_002"]
    assert sum(row["query_type"] == "strategy" for row in rows) == 12
    assert sum(row["query_type"] != "strategy" for row in rows) == 18
    assert all(row["agent_output"]["final_answer"] for row in rows)


def test_legacy_calibration_parser_metadata_matches_frozen_dataset():
    dataset = load_records()
    for row in parse_human_labelled_outputs():
        assert dataset[row["id"]]["query_type"] == row["query_type"]
        assert dataset[row["id"]]["difficulty"] == row["difficulty"]


def test_unique_mode_detection_rejects_three_way_split():
    assert not _has_unique_mode([0.5, 0.75, 1.0])
    assert _has_unique_mode([0.5, 0.75, 0.75])


def test_recalibration_analysis_downgrades_incomplete_strategy_pairs():
    result = analyze({
        "pairs": {"binary": [{"human": 1, "judge": 1}],
                  "strategy": [{"human": 0.5, "judge": 0.5}, {"human": 1.0, "judge": 1.0}]},
        "unresolved_ids": ["q_011"],
    })
    assert result["binary_mode"] == "eligible"
    assert result["strategy_mode"] == "reference-only"
