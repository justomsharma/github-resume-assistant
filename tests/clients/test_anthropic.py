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
    build_suggestion_messages,
)
from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    Repo,
)


def _gap_report(*, empty: bool) -> GapReport:
    """A small gap report with one gap and one backed claim."""
    return GapReport(
        profile_login="octocat",
        supported=(
            ClaimEvidence(
                claim=Claim(text="Built a cache in Go"),
                supported=True,
                matching_repos=("go-cache",),
                rationale="",
            ),
        ),
        unsupported=(
            ClaimEvidence(
                claim=Claim(text="Proficient in React"),
                supported=False,
                matching_repos=(),
                rationale="",
            ),
        ),
        github_is_empty=empty,
    )


def _profile(*, empty: bool) -> Profile:
    repos = (
        []
        if empty
        else [
            Repo(
                name="go-cache",
                description="A distributed cache",
                url="https://github.com/octocat/go-cache",
                stars=42,
                primary_language="Go",
                created_at=None,
                last_pushed_at=None,
                is_fork=False,
            )
        ]
    )
    return Profile(
        login="octocat",
        name=None,
        bio=None,
        profile_url="https://github.com/octocat",
        public_repo_count=len(repos),
        followers=0,
        repos=repos,
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
        '{"claims": [{"text": "Built a cache in Go", "skills": ["Go"], "category": "project"}]}'
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


# --- generate_suggestions (v0.3) --------------------------------------------


def test_build_suggestion_messages_delimits_and_grounds_gap_report() -> None:
    messages = build_suggestion_messages(_gap_report(empty=False), _profile(empty=False))
    content = messages[0]["content"]

    assert "<gap_report>" in content and "</gap_report>" in content
    assert "Proficient in React" in content  # the unsupported claim (gap) is present
    assert "Built a cache in Go" in content  # the supported claim is present
    assert "go-cache" in content  # real repo facts ground the suggestions


def test_generate_suggestions_parses_json(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response(
        '{"suggestions": [{"title": "React dashboard", "what_to_build": '
        '"A small dashboard", "proves_claim": "Proficient in React", '
        '"skills": ["React"], "size": "a weekend", "skip": "auth"}]}'
    )

    suggestions = AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
        _gap_report(empty=False), _profile(empty=False)
    )

    assert len(suggestions) == 1
    assert suggestions[0].title == "React dashboard"
    assert suggestions[0].proves_claim == "Proficient in React"
    assert suggestions[0].skills == ("react",)  # normalized to lowercase
    assert suggestions[0].size == "a weekend"
    assert suggestions[0].skip == "auth"


def test_generate_suggestions_uses_config_model_and_schema(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response('{"suggestions": []}')

    AnthropicClient(api_key="k", model="claude-opus-4-8").generate_suggestions(
        _gap_report(empty=True), _profile(empty=True)
    )

    kwargs = instance.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-8"  # model from config, not hardcoded
    assert "return only a json object" in kwargs["system"].lower()  # schema instruction
    assert "empty" in kwargs["system"].lower()  # empty-GitHub handling is instructed
    assert "<gap_report>" in kwargs["messages"][0]["content"]


def test_generate_suggestions_empty_response_returns_empty(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response('{"suggestions": []}')

    suggestions = AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
        _gap_report(empty=False), _profile(empty=False)
    )

    assert suggestions == []


def test_generate_suggestions_skips_incomplete_items(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response(
        '{"suggestions": [{"title": "", "what_to_build": "x"}, '
        '{"title": "Real", "what_to_build": "Build it", "size": "a week"}]}'
    )

    suggestions = AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
        _gap_report(empty=False), _profile(empty=False)
    )

    assert len(suggestions) == 1  # the item missing a title is dropped
    assert suggestions[0].title == "Real"


def test_generate_suggestions_unparseable_raises(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response("not json at all")

    with pytest.raises(AnthropicError):
        AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
            _gap_report(empty=False), _profile(empty=False)
        )


def test_generate_suggestions_api_error_wrapped(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.side_effect = anthropic.APIError(
        "boom", request=httpx.Request("POST", "https://api.anthropic.com"), body=None
    )

    with pytest.raises(AnthropicError):
        AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
            _gap_report(empty=False), _profile(empty=False)
        )


# --- token budget + retry/backoff (v0.3 truncation bugfix) -------------------


def _conn_error() -> anthropic.APIConnectionError:
    """A transient connection error (retryable)."""
    return anthropic.APIConnectionError(
        message="connection dropped",
        request=httpx.Request("POST", "https://api.anthropic.com"),
    )


def _auth_error() -> anthropic.AuthenticationError:
    """A 401 auth error (permanent — must not be retried)."""
    request = httpx.Request("POST", "https://api.anthropic.com")
    return anthropic.AuthenticationError(
        "bad key", response=httpx.Response(401, request=request), body=None
    )


def test_suggestions_use_larger_token_budget_than_claims(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response('{"suggestions": []}')

    client = AnthropicClient(api_key="k", model="claude-sonnet-5")
    client.generate_suggestions(_gap_report(empty=False), _profile(empty=False))
    suggest_tokens = instance.messages.create.call_args.kwargs["max_tokens"]

    instance.messages.create.return_value = _text_response('{"claims": []}')
    client.extract_claims("resume")
    claim_tokens = instance.messages.create.call_args.kwargs["max_tokens"]

    # Suggestions get a bigger budget so the richer JSON isn't truncated mid-object.
    assert suggest_tokens == 4096
    assert claim_tokens == 2048
    assert suggest_tokens > claim_tokens


def test_truncated_suggestions_response_raises_clear_error(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    # A response cut off mid-object: valid prefix, no closing braces — what a
    # too-small max_tokens produced before the fix.
    instance.messages.create.return_value = _text_response(
        '{"suggestions": [{"title": "React app", "what_to_build": "A dashb'
    )

    with pytest.raises(AnthropicError) as excinfo:
        AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
            _gap_report(empty=False), _profile(empty=False)
        )

    assert "incomplete or non-JSON" in str(excinfo.value)


def test_transient_error_is_retried_then_succeeds(mocker: MockerFixture) -> None:
    sleep = mocker.patch("resume_assistant.clients.anthropic.time.sleep")
    instance = _patch_sdk(mocker)
    instance.messages.create.side_effect = [
        _conn_error(),
        _text_response('{"suggestions": []}'),
    ]

    result = AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
        _gap_report(empty=False), _profile(empty=False)
    )

    assert result == []
    assert instance.messages.create.call_count == 2  # first failed, retry succeeded
    sleep.assert_called_once()  # backed off exactly once before the retry


def test_transient_error_retries_exhausted_raises(mocker: MockerFixture) -> None:
    sleep = mocker.patch("resume_assistant.clients.anthropic.time.sleep")
    instance = _patch_sdk(mocker)
    instance.messages.create.side_effect = _conn_error()

    with pytest.raises(AnthropicError):
        AnthropicClient(api_key="k", model="claude-sonnet-5").extract_claims("resume")

    assert instance.messages.create.call_count == 3  # _MAX_RETRIES attempts
    assert sleep.call_count == 2  # slept between attempts, not after the last


def test_auth_error_is_not_retried(mocker: MockerFixture) -> None:
    sleep = mocker.patch("resume_assistant.clients.anthropic.time.sleep")
    instance = _patch_sdk(mocker)
    instance.messages.create.side_effect = _auth_error()

    with pytest.raises(AnthropicAuthError):
        AnthropicClient(api_key="k", model="claude-sonnet-5").generate_suggestions(
            _gap_report(empty=False), _profile(empty=False)
        )

    assert instance.messages.create.call_count == 1  # permanent error, no retry
    sleep.assert_not_called()
