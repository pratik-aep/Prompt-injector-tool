"""Application settings, read from environment variables (prefix PROMPTFORGE_)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"PROMPTFORGE_{name}", default)


@dataclass
class Settings:
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8000")))
    db_path: Path = field(default_factory=lambda: Path(_env("DB_PATH", str(ROOT / "data" / "promptforge.db"))))
    challenges_dir: Path = field(default_factory=lambda: Path(_env("CHALLENGES_DIR", str(ROOT / "challenges"))))
    strategies_dir: Path = field(default_factory=lambda: Path(_env("STRATEGIES_DIR", str(ROOT / "templates" / "strategies"))))
    plugins_dir: Path = field(default_factory=lambda: Path(_env("PLUGINS_DIR", str(ROOT / "configuration" / "evaluator_plugins"))))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://127.0.0.1:11434"))
    local_concurrency: int = field(default_factory=lambda: int(_env("LOCAL_CONCURRENCY", "1")))
    default_timeout_s: float = field(default_factory=lambda: float(_env("TIMEOUT_S", "120")))
    # Plugins are arbitrary Python: off unless the operator opts in.
    enable_plugins: bool = field(default_factory=lambda: _env("ENABLE_PLUGINS", "0") == "1")
    allow_lan: bool = field(default_factory=lambda: _env("ALLOW_LAN", "0") == "1")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(s: Settings | None) -> None:
    global _settings
    _settings = s
