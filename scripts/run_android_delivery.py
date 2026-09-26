"""Launch the local Android demonstration from a private config file.

Initialization creates a dedicated database and applies migrations; it never
changes the user's pre-existing canonical database or frozen evaluation data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / ".cache/android_delivery/runtime.json")
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.initialize:
        if args.config.exists():
            raise SystemExit("config already exists; omit --initialize to reuse it")
        import psycopg
        from psycopg import sql
        from app.storage.database import apply_migrations
        name = "merchant_delivery_" + uuid4().hex[:12]
        with psycopg.connect("dbname=postgres", autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        dsn = f"dbname={name}"
        apply_migrations(dsn)
        args.config.parent.mkdir(parents=True, exist_ok=True)
        config = {"database_url": dsn, "access_token": secrets.token_urlsafe(32),
                  "merchant_id": "xiaozhang_women", "port": args.port,
                  "base_url": f"http://127.0.0.1:{args.port}"}
        fd = os.open(args.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle, indent=2)
        print(f"Initialized private configuration: {args.config}", flush=True)
    config = json.loads(args.config.read_text())
    os.environ.update(DATABASE_URL=config["database_url"], DEMO_ACCESS_TOKEN=config["access_token"],
                      DEMO_MERCHANT_ID=config["merchant_id"], MERCHANTCOPILOT_DELIVERY_ENABLED="1",
                      MERCHANTCOPILOT_DISABLE_LANGSMITH="1", LANGSMITH_TRACING="false")
    import uvicorn
    print(f"Local Android backend: {config['base_url']}; warmup readiness: /readyz", flush=True)
    uvicorn.run("app.api.main:app", host="127.0.0.1", port=config["port"], log_level="warning")


if __name__ == "__main__":
    main()
