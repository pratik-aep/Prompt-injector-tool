"""Custom evaluator plugins: Python files in the plugins dir (opt-in)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from .base import CheckResult


class PluginError(Exception):
    pass


def load_plugins() -> dict[str, Any]:
    s = get_settings()
    if not s.enable_plugins:
        return {}
    out: dict[str, Any] = {}
    d: Path = s.plugins_dir
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"pf_plugin_{f.stem}", f)
        if not spec or not spec.loader:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "NAME") and hasattr(mod, "evaluate"):
            out[mod.NAME] = mod
    return out


def run_plugin(response: str, cfg: dict[str, Any], prompt: str) -> CheckResult:
    if not get_settings().enable_plugins:
        raise PluginError("Evaluator plugins are disabled (set PROMPTFORGE_ENABLE_PLUGINS=1 to opt in)")
    plugins = load_plugins()
    mod = plugins.get(cfg.get("name"))
    if mod is None:
        raise PluginError(f"Plugin '{cfg.get('name')}' not found")
    res = mod.evaluate(response, {"prompt": prompt, "params": cfg.get("params", {})})
    return CheckResult("plugin", bool(res.get("success")), float(res.get("progress", 1.0 if res.get("success") else 0.0)),
                       str(res.get("reason", ""))[:300], extra={"plugin": cfg.get("name")})
