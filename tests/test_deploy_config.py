from pathlib import Path


def test_cloud_run_demo_profile_and_secret_boundary_are_declared():
    config = Path("deploy/cloudrun-demo.yaml").read_text(encoding="utf-8")
    assert 'autoscaling.knative.dev/minScale: "0"' in config
    assert 'autoscaling.knative.dev/maxScale: "1"' in config
    assert "containerConcurrency: 1" in config
    assert "timeoutSeconds: 300" in config
    assert 'memory: 8Gi' in config and 'cpu: "2"' in config
    assert "secretKeyRef:" in config
    assert "postgresql://" not in config


def test_image_preloads_models_and_excludes_secrets():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    ignored = Path(".dockerignore").read_text(encoding="utf-8")
    assert "python scripts/warm_models.py" in dockerfile
    assert "uvicorn app.api.main:app" in dockerfile
    assert "pip install --upgrade pip" not in dockerfile
    assert ".env" in ignored
    assert ".venv312" in ignored
