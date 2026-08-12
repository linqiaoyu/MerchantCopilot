from pathlib import Path


def test_v2_memory_design_and_demo_script_are_honest_about_unverified_work():
    memory = Path("docs/v2_memory_design.md").read_text(encoding="utf-8")
    demo = Path("docs/v2_demo_script.md").read_text(encoding="utf-8")
    assert "source_event_id" in memory
    assert "T04 的两位真人 temporal truth 签核仍未完成" in memory
    assert "约 6–7 分钟" in demo
    assert "未完成前" in demo


def test_legacy_demo_script_is_explicitly_marked_as_v1_history():
    legacy_demo = Path("docs/demo_script.md").read_text(encoding="utf-8")
    assert "历史 v1 材料" in legacy_demo
    assert "v2_demo_script.md" in legacy_demo
