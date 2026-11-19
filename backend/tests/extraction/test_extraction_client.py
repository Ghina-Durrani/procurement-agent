"""Tests for the real client. A fake network (httpx MockTransport) is used: no internet."""
import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.extraction import (
    LLMAuthError,
    LLMNotConfigured,
    LLMRateLimited,
    LLMRequestFailed,
    build_llm_client,
)
from app.services.extraction.openai_compatible import OpenAICompatibleClient

KEY = "test-key-not-real-123"


def make_client(handler, base_url="https://api.example.test/openai/v1") -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        base_url=base_url,
        api_key=SecretStr(KEY),
        model="some-model",
        transport=httpx.MockTransport(handler),
    )


def ok(content: str):
    return lambda request: httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_request_has_the_expected_address_headers_and_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    assert make_client(handler).complete("SYS", "USER") == "{}"
    assert seen["url"] == "https://api.example.test/openai/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    body = seen["body"]
    assert body["model"] == "some-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


def test_trailing_slash_in_the_base_address_is_fine():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return ok("{}")(request)

    make_client(handler, base_url="https://api.example.test/v1/").complete("a", "b")
    assert seen["url"] == "https://api.example.test/v1/chat/completions"


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_gives_auth_error(status):
    with pytest.raises(LLMAuthError):
        make_client(lambda r: httpx.Response(status)).complete("a", "b")


def test_rate_limit_reports_how_long_to_wait():
    handler = lambda r: httpx.Response(429, headers={"retry-after": "12"})  # noqa: E731
    with pytest.raises(LLMRateLimited) as info:
        make_client(handler).complete("a", "b")
    assert info.value.retry_after_seconds == 12.0


def test_rate_limit_without_the_header_still_works():
    with pytest.raises(LLMRateLimited) as info:
        make_client(lambda r: httpx.Response(429)).complete("a", "b")
    assert info.value.retry_after_seconds is None


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_other_errors_give_request_failed_with_only_the_status(status):
    body = {"error": "echo of private request text: SECRET-REQUEST"}
    with pytest.raises(LLMRequestFailed) as info:
        make_client(lambda r: httpx.Response(status, json=body)).complete("a", "b")
    assert str(status) in str(info.value)
    assert "SECRET-REQUEST" not in str(info.value)


def test_timeout_and_network_errors_give_request_failed():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def broken(request):
        raise httpx.ConnectError("no route", request=request)

    for handler in (timeout, broken):
        with pytest.raises(LLMRequestFailed):
            make_client(handler).complete("a", "b")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": 42}}]}),
    ],
)
def test_unreadable_or_empty_answers_give_request_failed(response):
    with pytest.raises(LLMRequestFailed):
        make_client(lambda r: response).complete("a", "b")


def test_error_messages_never_contain_the_api_key():
    for status in (401, 429, 500):
        with pytest.raises(Exception) as info:
            make_client(lambda r, s=status: httpx.Response(s)).complete("a", "b")
        assert KEY not in str(info.value)
    assert KEY not in repr(SecretStr(KEY))


@pytest.mark.parametrize(
    "base_url", ["http://api.example.test/v1", "ftp://api.example.test", "api.example.test"]
)
def test_the_key_is_never_sent_over_plain_http_to_another_machine(base_url):
    with pytest.raises(LLMNotConfigured):
        make_client(ok("{}"), base_url=base_url)


@pytest.mark.parametrize("base_url", ["http://localhost:11434/v1", "http://127.0.0.1:8080/v1"])
def test_plain_http_is_allowed_for_a_model_on_this_computer(base_url):
    assert make_client(ok("{}"), base_url=base_url).complete("a", "b") == "{}"


# ---------- building the client from settings ----------


def test_factory_without_a_key_explains_what_to_do():
    with pytest.raises(LLMNotConfigured, match="LLM_API_KEY"):
        build_llm_client(Settings(_env_file=None, llm_api_key=None))


def test_factory_with_a_blank_key_is_the_same_as_no_key():
    with pytest.raises(LLMNotConfigured):
        build_llm_client(Settings(_env_file=None, llm_api_key=SecretStr("   ")))


def test_factory_builds_a_client_when_a_key_is_present():
    client = build_llm_client(Settings(_env_file=None, llm_api_key=SecretStr(KEY)))
    assert isinstance(client, OpenAICompatibleClient)


def test_default_settings_point_at_groq_and_can_be_changed():
    settings = Settings(_env_file=None)
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"
    other = Settings(_env_file=None, llm_base_url="https://api.openai.com/v1", llm_model="gpt-x")
    assert other.llm_model == "gpt-x"
