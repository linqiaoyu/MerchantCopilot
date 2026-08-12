"""Apply the local or Supabase direct-connection migrations once."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage.database import apply_migrations


if __name__ == "__main__":
    for migration in apply_migrations():
        print(f"applied {migration}")
