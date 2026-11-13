"""Cliente multi-modelo y medidor de uso, con un LLM simulado (sin gastar cuota)."""

from types import SimpleNamespace

import litellm
import pytest

from onco_research_ai.llm import client, usage


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "PATH", tmp_path / "usage.json")
    monkeypatch.setattr(client, "availability", lambda key: (True, ""))


def fake_response(text="ok", tokens=10, headers=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(total_tokens=tokens),
        _hidden_params={"additional_headers": headers or {}},
    )


def test_selected_model_is_the_one_called_and_usage_is_counted(monkeypatch):
    seen = []
    monkeypatch.setattr(
        litellm,
        "completion",
        lambda **kw: seen.append(kw["model"]) or fake_response(tokens=42),
    )
    with client.use_model("gemini") as calls:
        assert client.complete([{"role": "user", "content": "hi"}]) == "ok"
    assert seen == ["gemini/gemini-3.1-flash-lite"]
    assert calls == ["gemini"]
    assert usage.summary("gemini")["requests_today"] == 1
    assert usage.summary("gemini")["tokens_today"] == 42


def test_falls_back_to_next_model_when_daily_quota_is_exhausted(monkeypatch):
    def fake(**kw):
        if kw["model"].startswith("groq/"):
            raise litellm.RateLimitError(
                "Limit 200000, Used 199336 tokens per day (TPD)", "groq", "m"
            )
        return fake_response("from fallback")

    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    with client.use_model("groq") as calls:
        assert client.complete([{"role": "user", "content": "hi"}]) == "from fallback"
    assert calls == ["gemini"]  # contestó el siguiente, y queda anotado quién fue
    assert (
        usage.summary("groq")["reported"]["tokens_day_used"] == 199336
    )  # el error dejó su dato


def test_error_when_no_model_is_available(monkeypatch):
    monkeypatch.setattr(client, "availability", lambda key: (False, "no key"))
    with pytest.raises(client.NoModelAvailable):
        client.complete([{"role": "user", "content": "hi"}])


def test_unknown_model_key_falls_back_to_default():
    with client.use_model("nonsense"):
        assert client._selected.get() == client.DEFAULT_MODEL


def test_groq_rate_headers_are_parsed_with_litellm_prefix():
    info = usage.parse_rate_headers(
        {
            "llm_provider-x-ratelimit-remaining-requests": "820",
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-tokens": "7390",
            "x-ratelimit-limit-tokens": "8000",
        }
    )
    assert info == {
        "remaining_requests": 820,
        "limit_requests": 1000,
        "remaining_tokens_minute": 7390,
        "limit_tokens_minute": 8000,
    }


def test_gemini_estimate_uses_configured_daily_limit(monkeypatch):
    monkeypatch.setattr(litellm, "completion", lambda **kw: fake_response())
    with client.use_model("gemini"):
        client.complete([{"role": "user", "content": "hi"}])
    s = usage.summary("gemini", daily_request_limit=500)
    assert s["requests_left_estimate"] == 499


def test_extract_json_tolerates_code_fences_and_extra_text():
    assert client.extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert (
        client.extract_json('Sure! Here it is: {"a": 1} Hope it helps.') == '{"a": 1}'
    )
    assert client.extract_json('{"a": 1}') == '{"a": 1}'
