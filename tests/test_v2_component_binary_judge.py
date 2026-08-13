import json
from pathlib import Path

import evals.run_v2_component_binary_judge as runner
from evals.run_v2_component_ablation import CONFIGURATIONS


def test_agent_output_preserves_evidence_and_node_data():
    assert runner._agent_output({"final_answer": "a", "node_result": {"evidence": ["e"], "data": {"x": 1}}}) == {
        "final_answer": "a", "evidence": ["e"], "node_data": {"x": 1}, "retrieved_chunks": [],
    }


def test_run_rejects_non_component_source(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"runtime": {"configurations": ["wrong"]}}), encoding="utf-8")
    monkeypatch.setattr(runner, "judge_client", lambda: None)
    try:
        runner.run(source, tmp_path / "out.json")
    except ValueError as exc:
        assert "four-arm" in str(exc)
    else:
        raise AssertionError("expected contract rejection")


def test_contract_accepts_a_relative_source_path(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"runtime": {"configurations": ["wrong"]}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "judge_client", lambda: None)
    try:
        runner.run(Path(source.name), Path("out.json"))
    except ValueError as exc:
        assert "four-arm" in str(exc)
    else:
        raise AssertionError("expected contract rejection")
