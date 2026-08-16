from pathlib import Path


def test_env_example_contains_every_local_api_runtime_requirement():
    values = {
        line.split("=", 1)[0]
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    assert {"DATABASE_URL", "DATABASE_DIRECT_URL", "DEEPSEEK_API_KEY", "DEMO_ACCESS_TOKEN"} <= values
