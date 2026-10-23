"""One-shot startup: migrate DB, seed built-ins, register secret literals for log redaction."""
from __future__ import annotations

from ..core.security import install_log_redaction
from ..database.session import init_db, session_scope
from ..strategies.library import seed_builtin_strategies
from .challenges import register_all_secrets, seed_challenges
from .targets import seed_default_targets


def bootstrap(db_path=None) -> None:
    init_db(db_path)
    install_log_redaction()
    with session_scope() as db:
        seed_default_targets(db)
        seed_builtin_strategies(db)
        seed_challenges(db)
        register_all_secrets(db)
