import json

import httpx
import pytest

from app.services.llm import (
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.llm.gemini import GeminiClient
from app.services.llm.throttle import Throttle

API_KEY = "test-key-should-never-leak"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


def completed(text: str = '{"ok": true}', **extra: object) -> httpx.Response:
    body = {
        "id": "int-1",
        "model": "gemini-3.5-flash-lite",
        "status": "completed",
        "output_text": text,
        "usage": {
            "total_input_tokens": 1200,
            "total_output_tokens": 180,
            "total_thought_tokens": 40,
        },
        **extra,
    }
    return httpx.Response(200, json=body)


def make_client(*responses: httpx.Response | Exception, delays: list[float] | None = None, **kw):
    queue = list(responses)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client = GeminiClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_key=API_KEY,
        model="gemini-3.5-flash-lite",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_revision="2026-05-20",
        sleep=(delays if delays is not None else []).append,
        **{"max_retries": 2, **kw},
    )
    return client, requests


def call(client: GeminiClient):
    return client.generate_json(
        system_instruction="sys", prompt="article", schema={"type": "object"}, max_output_tokens=512
    )


def test_request_shape_and_successful_response() -> None:
    client, requests = make_client(completed())
    result = call(client)

    request = requests[0]
    assert str(request.url) == URL
    assert request.headers["x-goog-api-key"] == API_KEY
    assert request.headers["Api-Revision"] == "2026-05-20"
    body = json.loads(request.content)
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["system_instruction"] == "sys"
    assert body["input"] == "article"
    assert body["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": {"type": "object"},
    }
    assert body["generation_config"] == {"max_output_tokens": 512}
    assert body["store"] is False

    assert result.text == '{"ok": true}'
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.thought_tokens) == (
        1200,
        180,
        40,
    )


def test_output_text_falls_back_to_model_output_steps() -> None:
    response = httpx.Response(
        200,
        json={
            "status": "completed",
            "steps": [
                {"type": "thought", "content": [{"type": "text", "text": "ignored"}]},
                {"type": "model_output", "content": [{"type": "text", "text": '{"a":'}]},
                {"type": "model_output", "content": [{"type": "text", "text": " 1}"}]},
            ],
        },
    )
    client, _ = make_client(response)
    assert call(client).text == '{"a": 1}'


def test_rate_limit_is_retried_honouring_retry_after() -> None:
    delays: list[float] = []
    client, requests = make_client(
        httpx.Response(429, headers={"Retry-After": "7"}), completed(), delays=delays
    )
    assert call(client).text
    assert delays == [7.0]
    assert len(requests) == 2


def test_persistent_rate_limit_raises_rate_limit_error() -> None:
    limited = httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
    client, requests = make_client(limited, limited, limited)
    with pytest.raises(LLMRateLimitError, match="RESOURCE_EXHAUSTED"):
        call(client)
    assert len(requests) == 3


def test_timeouts_are_retried_then_raised() -> None:
    timeout = httpx.ReadTimeout("slow")
    delays: list[float] = []
    client, _ = make_client(timeout, timeout, timeout, delays=delays, backoff_base=2.0)
    with pytest.raises(LLMTimeoutError):
        call(client)
    assert delays == [2.0, 4.0]


def test_server_errors_are_transient() -> None:
    client, _ = make_client(httpx.Response(503), completed())
    assert call(client).text
    client, _ = make_client(
        httpx.ConnectError("x"), httpx.ConnectError("x"), httpx.ConnectError("x")
    )
    with pytest.raises(LLMUnavailableError):
        call(client)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_configuration_errors_and_not_retried(status: int) -> None:
    client, requests = make_client(
        httpx.Response(status, json={"error": {"status": "INVALID_ARGUMENT"}})
    )
    with pytest.raises(LLMConfigurationError) as exc:
        call(client)
    assert len(requests) == 1
    assert API_KEY not in str(exc.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"status": "incomplete", "output_text": "{"}),
        httpx.Response(200, json={"status": "failed"}),
        httpx.Response(200, json={"status": "completed", "output_text": "  "}),
        httpx.Response(200, content=b"not json"),
    ],
)
def test_unusable_responses_raise_response_error(response: httpx.Response) -> None:
    client, _ = make_client(response)
    with pytest.raises(LLMResponseError):
        call(client)


def test_missing_api_key_is_rejected_up_front() -> None:
    with pytest.raises(LLMConfigurationError):
        GeminiClient(
            httpx.Client(), api_key="", model="m", base_url="https://x.example", api_revision="r"
        )


def test_throttle_spaces_calls() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    throttle = Throttle(30, clock=lambda: now[0], sleep=sleep)  # one call per 2s
    throttle.wait()
    throttle.wait()
    now[0] += 5
    throttle.wait()
    assert sleeps == [2.0]
