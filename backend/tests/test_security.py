import pytest

from backend.core.errors import ScopeViolation, ValidationFailed
from backend.core.security import RateLimiter, redact, resolve_secret, secrets_registry, validate_url


def test_url_scheme_and_credentials_rejected():
    with pytest.raises(ValidationFailed):
        validate_url("file:///etc/passwd")
    with pytest.raises(ValidationFailed):
        validate_url("http://user:pw@example.com/")
    with pytest.raises(ValidationFailed):
        validate_url("not a url")


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/x", "http://localhost/x", "http://169.254.169.254/latest", "http://10.0.0.5/", "http://192.168.1.1/", "http://[::1]/"])
def test_ssrf_blocked(url):
    with pytest.raises(ScopeViolation):
        validate_url(url, resolve=False)


def test_private_allowed_only_when_flagged():
    assert validate_url("http://127.0.0.1:9000/chat", allow_private=True)


def test_public_ip_ok():
    assert validate_url("https://93.184.216.34/chat")


def test_redaction_of_credentials_and_registered_secrets():
    secrets_registry.register("CTF{super_secret_x}")
    out = redact("Authorization: Bearer abcdefghijklmnop and key sk-ABCDEFGHIJKLMNOPQRSTUV and CTF{super_secret_x} api_key=hunter22222")
    assert "abcdefghijklmnop" not in out and "sk-ABCDEF" not in out and "super_secret_x" not in out and "hunter22222" not in out


def test_secret_ref_formats(monkeypatch):
    monkeypatch.setenv("PF_TEST_KEY", "abc")
    assert resolve_secret("env:PF_TEST_KEY") == "abc"
    assert resolve_secret(None) is None
    with pytest.raises(ValidationFailed):
        resolve_secret("sk-rawkeyvalue")


async def test_rate_limiter_blocks_over_limit():
    import asyncio
    import time
    rl = RateLimiter(2, period=0.3)
    t0 = time.monotonic()
    await asyncio.gather(*(rl.acquire() for _ in range(3)))
    assert time.monotonic() - t0 >= 0.25
