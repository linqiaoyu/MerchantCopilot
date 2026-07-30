"""Apply the local or Supabase direct-connection migrations once."""
from __future__ import annotations

from app.storage.database import apply_migrations


if __name__ == "__main__":
    for migration in apply_migrations():
        print(f"applied {migration}")
