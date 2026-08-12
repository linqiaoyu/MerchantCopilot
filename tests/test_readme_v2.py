from pathlib import Path


def test_root_readme_describes_v2_and_marks_historical_boundaries():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "MerchantCopilot v2" in readme
    assert "deepseek-v4-flash" in readme
    assert "qwen3.7-plus-2026-05-26" in readme
    assert "v2_verification_ledger.md" in readme
    assert "flowchart LR" in readme
    assert "历史 v1" in readme
    assert "DeepSeek-V3" not in readme
    assert "Qwen-Max" not in readme
