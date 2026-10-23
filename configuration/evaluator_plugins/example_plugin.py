"""Example custom evaluator plugin (loaded only when PROMPTFORGE_ENABLE_PLUGINS=1).

Reference it from a challenge's evaluator_config:
    {"checks": [{"kind": "plugin", "name": "contains_digits", "params": {"min_digits": 4}}]}
"""
import re

NAME = "contains_digits"


def evaluate(response: str, context: dict) -> dict:
    need = int(context.get("params", {}).get("min_digits", 4))
    n = len(re.findall(r"\d", response))
    return {"success": n >= need, "progress": min(1.0, n / need), "reason": f"{n} digit(s) found, need {need}"}
