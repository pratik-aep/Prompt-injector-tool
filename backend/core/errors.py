"""Typed application errors. Messages are safe to show to users."""


class PromptForgeError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        if status_code:
            self.status_code = status_code


class NotFound(PromptForgeError):
    status_code = 404


class ScopeViolation(PromptForgeError):
    """Target not registered/enabled, or URL outside the approved scope."""
    status_code = 403


class BudgetExceeded(PromptForgeError):
    status_code = 429


class TargetError(PromptForgeError):
    """A target failed in a way the user should see (never includes secrets)."""
    status_code = 502


class ValidationFailed(PromptForgeError):
    status_code = 422
