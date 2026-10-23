"""Evaluator data types and the custom-plugin interface."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


class Verdict(str, Enum):
    VERIFIED_SUCCESS = "verified_success"
    POSSIBLE_SUCCESS = "possible_success"
    FAILED = "failed"
    INVALID_TEST = "invalid_test"
    EVALUATION_ERROR = "evaluation_error"


@dataclass
class CheckResult:
    kind: str
    triggered: bool            # True => the check observed the attack objective
    progress: float = 0.0      # 0..1 deterministic near-miss signal (never from tone)
    reason: str = ""
    deterministic: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    verdict: Verdict
    score: float                       # success score in [0, 1]; 1.0 only when verified
    reasons: list[str]
    checks: list[CheckResult] = field(default_factory=list)
    is_estimate: bool = False
    verified_flag: str | None = None   # set only on exact match with the configured flag

    def to_details(self) -> dict[str, Any]:
        return {"checks": [asdict(c) for c in self.checks], "verified_flag_found": self.verified_flag is not None}


class EvaluatorPlugin(Protocol):
    """Interface for custom evaluator plugins (a Python file in the plugins dir).

    Define ``NAME: str`` and ``def evaluate(response: str, context: dict) -> dict``
    returning ``{"success": bool, "progress": float (0-1), "reason": str}``.
    ``context`` holds ``prompt`` and the check's ``params``; it never includes
    the expected flag. Plugins run in-process and are disabled unless the operator
    sets PROMPTFORGE_ENABLE_PLUGINS=1.
    """
    NAME: str

    def evaluate(self, response: str, context: dict[str, Any]) -> dict[str, Any]: ...
