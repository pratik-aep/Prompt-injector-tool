"""Redaction, URL/SSRF validation, credential lookup, and rate limiting."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

from .errors import ScopeViolation, ValidationFailed

_REDACTED = "[REDACTED]"
_SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)(\"?\s*[:=]\s*\"?)[^\s\",}]{6,}"),
]


class _SecretRegistry:
    """Known-sensitive literals (e.g. expected flags). Never logged, never echoed."""

    def __init__(self) -> None:
        self._values: set[str] = set()

    def register(self, value: str | None) -> None:
        if value and len(value) >= 4:
            self._values.add(value)

    def clear(self) -> None:
        self._values.clear()

    def scrub(self, text: str) -> str:
        for v in sorted(self._values, key=len, reverse=True):
            text = text.replace(v, _REDACTED)
        return text


secrets_registry = _SecretRegistry()


def redact(text: str, *, include_registered: bool = True) -> str:
    """Strip credentials (and registered literals) from text bound for logs/errors."""
    if not isinstance(text, str):
        text = str(text)
    for p in _SECRET_PATTERNS:
        if p.groups >= 2:
            text = p.sub(lambda m: f"{m.group(1)}{m.group(2) if p.groups > 1 else ''}{_REDACTED}", text)
        else:
            text = p.sub(lambda m: (m.group(1) if p.groups else "") + _REDACTED, text)
    return secrets_registry.scrub(text) if include_registered else text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # pragma: no cover - logging must never raise
            pass
        return True


def install_log_redaction() -> None:
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        root.addFilter(RedactingFilter())
    for h in root.handlers:
        h.addFilter(RedactingFilter())


# ---- URL validation / SSRF -------------------------------------------------

_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


def _is_private(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified


def validate_url(url: str, *, allow_private: bool = False, resolve: bool = True) -> str:
    """Validate a user-registered endpoint URL.

    Rules: http/https only, no embedded credentials, a host is required, and
    (unless ``allow_private``) the host must not resolve to a private,
    loopback, link-local, or metadata address (SSRF protection). Loopback is
    permitted only when ``allow_private`` is set — used by the Ollama adapter
    and by explicitly-flagged local CTF servers.
    """
    try:
        p = urlparse(url)
    except ValueError as e:
        raise ValidationFailed(f"Invalid URL: {e}") from e
    if p.scheme not in ("http", "https"):
        raise ValidationFailed("URL scheme must be http or https")
    if not p.hostname:
        raise ValidationFailed("URL must include a host")
    if p.username or p.password:
        raise ValidationFailed("URLs with embedded credentials are not allowed")
    host = p.hostname
    if allow_private:
        return url
    if host.lower() in _LOOPBACK_NAMES:
        raise ScopeViolation("Loopback endpoints must be registered as local (allow_private)")
    try:
        ips = [host] if _is_ip(host) else (
            [ai[4][0] for ai in socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80))] if resolve else []
        )
    except socket.gaierror as e:
        raise ValidationFailed(f"Host does not resolve: {host}") from e
    for ip in ips:
        if _is_private(ip):
            raise ScopeViolation("Endpoint resolves to a private/internal address; blocked (SSRF protection)")
    return url


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


# ---- Credentials -----------------------------------------------------------

def resolve_secret(ref: str | None) -> str | None:
    """Resolve a secret reference. Formats: ``env:NAME`` or ``keychain:SERVICE``.

    Secrets are never stored in SQLite — only the reference is.
    """
    if not ref:
        return None
    kind, _, name = ref.partition(":")
    if kind == "env":
        value = os.environ.get(name) or None
        secrets_registry.register(value)   # anything we resolve is scrubbed from logs/errors from now on
        return value
    if kind == "keychain" and sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["security", "find-generic-password", "-s", name, "-w"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            value = out.stdout.strip() or None if out.returncode == 0 else None
            secrets_registry.register(value)
            return value
        except (OSError, subprocess.SubprocessError):
            return None
    raise ValidationFailed("secret_ref must look like 'env:NAME' or 'keychain:SERVICE'")


# ---- Rate limiting ---------------------------------------------------------

class RateLimiter:
    """Async sliding-window limiter: at most ``max_calls`` per ``period`` seconds."""

    def __init__(self, max_calls: int, period: float = 60.0):
        self.max_calls = max(1, max_calls)
        self.period = period
        self._stamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._stamps = [t for t in self._stamps if now - t < self.period]
                if len(self._stamps) < self.max_calls:
                    self._stamps.append(now)
                    return
                await asyncio.sleep(max(0.01, self.period - (now - self._stamps[0])))
