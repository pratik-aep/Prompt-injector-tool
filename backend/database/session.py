"""Engine/session management. SQLite runs in WAL mode with foreign keys on."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ..core.config import get_settings
from .migrate import migrate

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None
_mem_lock = threading.RLock()   # the in-memory test DB shares one connection across threads
_in_memory = False


def init_db(db_path=None) -> Engine:
    """(Re)initialise the engine, applying migrations. ``":memory:"`` for tests."""
    global _engine, _factory, _in_memory
    s = get_settings()
    path = db_path if db_path is not None else s.db_path
    _in_memory = str(path) == ":memory:"
    if _in_memory:
        # One shared in-memory connection; migrate through that connection.
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        from .migrate import MIGRATIONS_DIR
        conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.executescript("BEGIN;\n" + f.read_text() + f"\nINSERT INTO schema_migrations(version) VALUES ('{f.stem}');\nCOMMIT;")
        engine = create_engine("sqlite://", creator=lambda: conn, poolclass=StaticPool)
    else:
        migrate(path)
        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):  # pragma: no cover
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        if str(path) != ":memory:":
            cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    with engine.connect() as c:
        c.exec_driver_sql("PRAGMA foreign_keys=ON")
    _engine = engine
    _factory = sessionmaker(engine, expire_on_commit=False)
    return engine


def get_engine() -> Engine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on error."""
    if _factory is None:
        init_db()
    assert _factory is not None
    lock = _mem_lock if _in_memory else None
    if lock:
        lock.acquire()
    s = _factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
        if lock:
            lock.release()
