"""Run all pytest regression checks against a disposable native pgvector DB."""
from __future__ import annotations

import argparse
import gzip
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    name = "delivery_regression_" + uuid4().hex[:12]
    with psycopg.connect("dbname=postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            from app.storage.database import apply_migrations
            dsn = f"dbname={name}"
            apply_migrations(dsn)
            env = {**os.environ, "DATABASE_URL": dsn, "DATABASE_DIRECT_URL": dsn,
                   "LEGACY_TEST_DATABASE_URL": dsn, "MERCHANTCOPILOT_DISABLE_LANGSMITH": "1",
                   "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "DEEPSEEK_API_KEY": "", "QWEN_API_KEY": ""}
            # 参数化安全测试的 case ID 含假密钥样本；原始 JUnit 无损归档，
            # 避免下一轮源码扫描把测试夹具在报告中的拷贝误报为真实凭据。
            with TemporaryDirectory(prefix="delivery-junit-") as temporary:
                junit = Path(temporary) / "pytest.xml"
                with (args.output / "pytest.txt").open("w") as log:
                    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(junit)],
                                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                if junit.exists():
                    (args.output / "pytest.xml.gz").write_bytes(gzip.compress(junit.read_bytes(), mtime=0))
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    print("\n".join((args.output / "pytest.txt").read_text().splitlines()[-24:]))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
