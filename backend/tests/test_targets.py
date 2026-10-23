import json

import httpx
import pytest

from backend.core.errors import ScopeViolation, ValidationFailed
from backend.database import orm
from backend.targets.base import Message
from backend.targets.http_api import HttpApiTarget, extract_path
from backend.targets.ollama import OllamaTarget, detect_ollama
from backend.targets.registry import build_target, validate_target_config

MSGS = [Message("system", "be nice"), Message("user", "hi")]


def ndjson(*objs):
    return "\n".join(json.dumps(o) for o in objs).encode()


def ollama_transport(handler):
    return httpx.MockTransport(handler)


async def test_ollama_detects_server_and_lists_models():
    def h(req):
        assert req.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b", "size": 2_000_000_000, "details": {"family": "llama", "parameter_size": "3B", "quantization_level": "Q4_K_M"}}]})
    info = await detect_ollama("http://127.0.0.1:11434", ollama_transport(h))
    assert info["server_up"] and info["models"][0]["parameter_size"] == "3B"


async def test_ollama_server_down_is_graceful():
    def h(req):
        raise httpx.ConnectError("refused")
    info = await detect_ollama("http://127.0.0.1:11434", ollama_transport(h))
    assert not info["server_up"] and info["error"]
    t = OllamaTarget({"model": "x"}, transport=ollama_transport(h))
    r = await t.generate(MSGS)
    assert r.error and "connection" in r.error.lower()


async def test_ollama_streaming_response_and_token_metrics():
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=ndjson({"message": {"content": "Hel"}, "done": False}, {"message": {"content": "lo"}, "done": False},
                                                  {"message": {"content": ""}, "done": True, "prompt_eval_count": 12, "eval_count": 5, "total_duration": 99}))
    t = OllamaTarget({"model": "m", "max_tokens": 64}, transport=ollama_transport(h))
    r = await t.generate(MSGS)
    assert r.text == "Hello" and r.tokens_in == 12 and r.tokens_out == 5 and r.latency_ms > 0
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be nice"} and seen["body"]["options"]["num_predict"] == 64


async def test_ollama_http_error_and_missing_model():
    t = OllamaTarget({"model": "m"}, transport=ollama_transport(lambda r: httpx.Response(404, text='{"error":"model not found"}')))
    r = await t.generate(MSGS)
    assert r.error and "404" in r.error
    assert (await OllamaTarget({}).generate(MSGS)).error == "No Ollama model selected"


async def test_ollama_health_reports_missing_model():
    h = lambda req: httpx.Response(200, json={"models": [{"name": "other:latest"}]})
    res = await OllamaTarget({"model": "m"}, transport=ollama_transport(h)).health()
    assert not res["ok"] and "not installed" in res["detail"]


async def test_ollama_timeout_reported():
    def h(req):
        raise httpx.ReadTimeout("slow")
    r = await OllamaTarget({"model": "m"}, transport=ollama_transport(h)).generate(MSGS)
    assert "timed out" in r.error


# ---- HTTP API target ---------------------------------------------------
CFG = {"url": "https://93.184.216.34/chat", "response_path": "choices.0.message.content", "retry_backoff_s": 0.01,
       "auth": {"type": "bearer"}, "headers": {"X-Team": "t1"}, "body_template": {"model": "m", "messages": "{{messages}}", "q": "{{prompt}}"}}


def api(cfg=None, handler=None, secret_ref="env:PF_KEY", **kw):
    return HttpApiTarget({**CFG, **(cfg or {})}, target_id=f"t{id(handler)}", secret_ref=secret_ref, transport=httpx.MockTransport(handler), **kw)


async def test_http_target_mapping_auth_headers(monkeypatch):
    monkeypatch.setenv("PF_KEY", "tok123456")
    seen = {}

    def h(req):
        seen.update(headers=dict(req.headers), body=json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})
    r = await api(handler=h).generate(MSGS)
    assert r.text == "pong" and r.tokens_in == 3
    assert seen["headers"]["authorization"] == "Bearer tok123456" and seen["headers"]["x-team"] == "t1"
    assert seen["body"]["q"] == "hi" and seen["body"]["messages"][1] == {"role": "user", "content": "hi"}


async def test_http_target_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("PF_KEY", "tok123456")
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    r = await api(handler=h).generate(MSGS)
    assert r.text == "ok" and len(calls) == 2


async def test_http_target_errors_never_leak_credentials(monkeypatch):
    monkeypatch.setenv("PF_KEY", "tok123456")
    h = lambda req: httpx.Response(401, text="bad token tok123456 Bearer tok123456")
    r = await api(handler=h, cfg={"retries": 0}).generate(MSGS)
    assert r.error.startswith("HTTP 401") and "tok123456" not in r.error


async def test_http_target_bad_path_and_missing_credential(monkeypatch):
    monkeypatch.setenv("PF_KEY", "tok123456")
    r = await api(handler=lambda q: httpx.Response(200, json={"x": 1})).generate(MSGS)
    assert "response_path" in r.error
    monkeypatch.delenv("PF_KEY")
    r = await api(handler=lambda q: httpx.Response(200, json={})).generate(MSGS)
    assert "Credential" in r.error


async def test_http_target_rate_limit_applies(monkeypatch):
    import time
    monkeypatch.setenv("PF_KEY", "tok123456")
    t = api(cfg={"rate_limit_per_min": 1}, handler=lambda q: httpx.Response(200, json={"choices": [{"message": {"content": "a"}}]}))
    t.limiter.period = 0.3
    t0 = time.monotonic()
    await t.generate(MSGS)
    await t.generate(MSGS)
    assert time.monotonic() - t0 >= 0.25


def test_extract_path():
    assert extract_path({"a": [{"b": 1}]}, "a.0.b") == 1


def test_config_validation_rules():
    with pytest.raises(ScopeViolation):
        validate_target_config("http_api", {"url": "http://169.254.169.254/x"}, False)
    with pytest.raises(ValidationFailed):
        validate_target_config("http_api", {"url": "ftp://example.com"}, False)
    with pytest.raises(ValidationFailed):
        validate_target_config("http_api", {"url": "https://93.184.216.34", "method": "DELETE"}, False)
    with pytest.raises(ValidationFailed):
        validate_target_config("http_api", {"url": "https://93.184.216.34", "rate_limit_per_min": 0}, False)
    with pytest.raises(ValidationFailed):
        validate_target_config("ollama", {}, False)
    with pytest.raises(ValidationFailed):
        validate_target_config("martian", {}, False)
    assert validate_target_config("http_api", {"url": "http://127.0.0.1:9000/x"}, True)["method"] == "POST"


def test_disabled_target_is_never_built():
    t = orm.Target(id="x", name="n", kind="ollama", config={"model": "m"}, enabled=False)
    with pytest.raises(ScopeViolation):
        build_target(t)


async def test_openai_and_anthropic_inactive_without_credentials(monkeypatch):
    from backend.targets.providers import AnthropicTarget, OpenAITarget
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "not configured" in (await OpenAITarget({"model": "m"}, secret_ref=None).generate(MSGS)).error
    assert "not configured" in (await AnthropicTarget({"model": "m"}, secret_ref=None).generate(MSGS)).error


async def test_openai_and_anthropic_parse_responses(monkeypatch):
    from backend.targets.providers import AnthropicTarget, OpenAITarget
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-000000000000")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    oa = OpenAITarget({"model": "m"}, secret_ref=None, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 2}})))
    assert (await oa.generate(MSGS)).text == "hi"
    seen = {}

    def h(req):
        seen.update(json.loads(req.content), key=req.headers["x-api-key"])
        return httpx.Response(200, json={"content": [{"type": "text", "text": "yo"}], "usage": {"input_tokens": 4, "output_tokens": 1}})
    an = AnthropicTarget({"model": "m"}, secret_ref=None, transport=httpx.MockTransport(h))
    r = await an.generate(MSGS)
    assert r.text == "yo" and r.tokens_in == 4 and seen["system"] == "be nice" and all(m["role"] != "system" for m in seen["messages"])
