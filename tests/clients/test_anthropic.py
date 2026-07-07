"""Tests for the Anthropic client. The SDK is mocked — no network, no API key."""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx
import pytest
from pytest_mock import MockerFixture

from resume_assistant.clients.anthropic import (
    AnthropicAuthError,
    AnthropicClient,
    AnthropicError,
    build_extraction_messages,
)


def _text_response(text: str) -> SimpleNamespace:
    """A fake messages.create response with a single text block."""
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _patch_sdk(mocker: MockerFixture) -> SimpleNamespace:
    """Patch anthropic.Anthropic; return the mock client instance."""
    instance = mocker.patch.object(anthropic, "Anthropic").return_value
    return instance


def test_build_extraction_messages_delimits_resume() -> None:
    messages = build_extraction_messages("Built a cache in Go.")
    content = messages[0]["content"]

    assert "<resume>" in content and "</resume>" in content
    assert "Built a cache in Go." in content  # the raw resume text is present verbatim


def test_missing_api_key_raises_auth_error() -> None:
    with pytest.raises(AnthropicAuthError):
        AnthropicClient(api_key=None, model="claude-sonnet-5")


def test_extract_claims_parses_json(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response(
        '{"claims": [{"text": "Built a cache in Go", "skills": ["Go"], '
        '"category": "project"}]}'
    )

    claims = AnthropicClient(api_key="k", model="claude-sonnet-5").extract_claims("resume")

    assert len(claims) == 1
    assert claims[0].text == "Built a cache in Go"
    assert claims[0].skills == ("go",)  # normalized to lowercase
    assert claims[0].category == "project"


def test_extract_claims_uses_config_model_and_delimited_prompt(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response('{"claims": []}')

    AnthropicClient(api_key="k", model="claude-opus-4-8").extract_claims("Shipped X.")

    kwargs = instance.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-8"  # model comes from config, not hardcoded
    assert "return ONLY a JSON object".lower() in kwargs["system"].lower()  # schema instruction
    assert "<resume>\nShipped X.\n</resume>" in kwargs["messages"][0]["content"]


def test_extract_claims_empty_response_returns_empty(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response('{"claims": []}')

    claims = AnthropicClient(api_key="k", model="claude-sonnet-5").extract_claims("")

    assert claims == []


def test_extract_claims_tolerates_prose_around_json(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response(
        'Here you go:\n{"claims": [{"text": "Did a thing", "skills": [], '
        '"category": "impact"}]}\nHope that helps.'
    )

    claims = AnthropicClient(api_key="k", model="claude-sonnet-5").extract_claims("r")

    assert len(claims) == 1
    assert claims[0].text == "Did a thing"


def test_extract_claims_unparseable_raises(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response("not json at all")

    with pytest.raises(AnthropicError):
        AnthropicClient(api_key="k", model="claude-sonnet-5").extract_claims("r")


def test_extract_claims_api_error_wrapped(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.side_effect = anthropic.APIError(
        "boom", request=httpx.Request("POST", "https://api.anthropic.com"), body=None
    )

    with pytest.raises(AnthropicError):
        AnthropicClient(api_key="k", model="claude-sonnet-5").extract_claims("r")
