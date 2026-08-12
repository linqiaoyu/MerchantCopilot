from pathlib import Path


def test_v2_memory_design_and_demo_script_are_honest_about_unverified_work():
    memory = Path("docs/v2_memory_design.md").read_text(encoding="utf-8")
    demo = Path("docs/v2_demo_script.md").read_text(encoding="utf-8")
    assert "source_event_id" in memory
    assert "T04 的两位真人 temporal truth 签核仍未完成" in memory
    assert "约 6–7 分钟" in demo
    assert "未完成前" in demo
