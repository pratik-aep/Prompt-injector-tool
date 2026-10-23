"""Minimal forward-only SQL migration runner (no external dependency)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def migrate(db_path: Path | str) -> list[str]:
    """Apply pending ``NNN_name.sql`` files in order, each in one transaction."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    applied: list[str] = []
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.stem in done:
                continue
            conn.executescript("BEGIN;\n" + f.read_text() + f"\nINSERT INTO schema_migrations(version) VALUES ('{f.stem}');\nCOMMIT;")
            applied.append(f.stem)
    finally:
        conn.close()
    return applied
