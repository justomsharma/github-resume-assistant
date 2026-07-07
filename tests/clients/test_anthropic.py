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
    build_verification_messages,
)
from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    Repo,
    RepoEvidence,
)


def _gap_report(*, empty: bool) -> GapReport:
    """A small gap report with one gap and one backed claim."""
    return GapReport(
        profile_login="octocat",
        backed=(
            ClaimEvidence(
                claim=Claim(text="Built a cache in Go"),
                verdict="backed",
                matching_repos=("go-cache",),
                cited_files=("go-cache/src/cache.go",),
                rationale="",
            ),
        ),
        not_shown=(
            ClaimEvidence(
                claim=Claim(text="Proficient in React"),
                verdict="not_shown",
                matching_repos=(),
                cited_files=(),
                rationale="",
            ),
        ),
        not_verifiable=(),
        github_is_empty=empty,
    )


def _evidence() -> list[RepoEvidence]:
    """One repo's code-level evidence for the verifier."""
    return [
        RepoEvidence(
            repo_name="go-cache",
            primary_language="Go",
            language_breakdown=(("Go", 12000),),
            dependencies=("github.com/redis/go-redis",),
            notable_paths=("src/cache.go", "tests/cache_test.go"),
            file_count=14,
            readme_excerpt="# go-cache\nA distributed cache.",
            pushed_at="2024-06-01T00:00:00Z",
        )
    ]


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


# --- verify_claims (v2.1) ----------------------------------------------------


_CLAIMS = [
    Claim(text="Built a distributed cache in Go", skills=("go",)),
    Claim(text="Proficient in React", skills=("react",)),
    Claim(text="Handled 300+ requests/day", skills=()),
]


def test_build_verification_messages_delimits_claims_and_evidence() -> None:
    messages = build_verification_messages(_CLAIMS, _evidence())
    content = messages[0]["content"]

    assert "<claims>" in content and "</claims>" in content
    assert "<evidence>" in content and "</evidence>" in content
    assert "Built a distributed cache in Go" in content  # claim text verbatim
    assert "go-cache" in content  # real repo grounds the grading
    assert "github.com/redis/go-redis" in content  # parsed dependency is evidence


def test_verify_claims_parses_three_verdicts(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response(
        '{"verdicts": ['
        '{"claim": "Built a distributed cache in Go", "verdict": "backed", '
        '"cited_files": ["go-cache/src/cache.go"], "rationale": "LRU cache in cache.go"},'
        '{"claim": "Proficient in React", "verdict": "not_shown", "cited_files": [], '
        '"rationale": "no React code"},'
        '{"claim": "Handled 300+ requests/day", "verdict": "not_verifiable", '
        '"cited_files": [], "rationale": "traffic can\'t be shown in public code"}]}'
    )

    verdicts = AnthropicClient(api_key="k", model="claude-sonnet-5").verify_claims(
        _CLAIMS, _evidence()
    )

    assert [v.verdict for v in verdicts] == ["backed", "not_shown", "not_verifiable"]
    assert verdicts[0].cited_files == ("go-cache/src/cache.go",)
    assert verdicts[0].matching_repos == ("go-cache",)  # derived from the cited file
    assert verdicts[0].supported is True


def test_verify_claims_uses_config_model_and_schema(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response('{"verdicts": []}')

    AnthropicClient(api_key="k", model="claude-opus-4-8").verify_claims(_CLAIMS, _evidence())

    kwargs = instance.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-8"  # model from config, not hardcoded
    system = kwargs["system"].lower()
    assert "return only a json object" in system  # schema instruction
    assert "backed" in system and "not_shown" in system and "not_verifiable" in system
    assert "cited_files" in kwargs["system"]  # must cite files to back a claim


def test_verify_backed_without_cited_files_is_downgraded(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response(
        '{"verdicts": [{"claim": "Built a distributed cache in Go", "verdict": "backed", '
        '"cited_files": [], "rationale": "trust me"}]}'
    )

    verdicts = AnthropicClient(api_key="k", model="claude-sonnet-5").verify_claims(
        [_CLAIMS[0]], _evidence()
    )

    # 'backed' with no cited file isn't grounded — it becomes an honest gap.
    assert verdicts[0].verdict == "not_shown"


def test_verify_unknown_verdict_and_missing_claim_default_to_not_shown(
    mocker: MockerFixture,
) -> None:
    instance = _patch_sdk(mocker)
    # First claim gets a garbage verdict; the others are omitted entirely.
    instance.messages.create.return_value = _text_response(
        '{"verdicts": [{"claim": "Built a distributed cache in Go", "verdict": "maybe"}]}'
    )

    verdicts = AnthropicClient(api_key="k", model="claude-sonnet-5").verify_claims(
        _CLAIMS, _evidence()
    )

    assert len(verdicts) == 3  # one verdict per claim, in order
    assert all(v.verdict == "not_shown" for v in verdicts)


def test_verify_empty_claims_skips_api(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)

    verdicts = AnthropicClient(api_key="k", model="claude-sonnet-5").verify_claims([], _evidence())

    assert verdicts == []
    instance.messages.create.assert_not_called()


def test_verify_no_evidence_defaults_all_not_shown_without_api(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)

    verdicts = AnthropicClient(api_key="k", model="claude-sonnet-5").verify_claims(_CLAIMS, [])

    assert [v.verdict for v in verdicts] == ["not_shown", "not_shown", "not_shown"]
    instance.messages.create.assert_not_called()  # nothing to grade against


def test_verify_batches_evidence_and_merges_backed_wins(mocker: MockerFixture) -> None:
    # Force two batches by shrinking the char budget below one repo's rendered size.
    mocker.patch("resume_assistant.clients.anthropic._EVIDENCE_CHAR_BUDGET", 10)
    instance = _patch_sdk(mocker)
    # Batch 1 backs the claim; batch 2 says not_shown. Merge must keep 'backed'.
    instance.messages.create.side_effect = [
        _text_response(
            '{"verdicts": [{"claim": "Built a distributed cache in Go", "verdict": "backed", '
            '"cited_files": ["repo-a/cache.go"], "rationale": "found it"}]}'
        ),
        _text_response(
            '{"verdicts": [{"claim": "Built a distributed cache in Go", "verdict": "not_shown", '
            '"cited_files": [], "rationale": "not here"}]}'
        ),
    ]
    two_repos = _evidence() + [
        RepoEvidence(
            repo_name="repo-b",
            primary_language="Go",
            language_breakdown=(("Go", 10),),
            dependencies=(),
            notable_paths=(),
            file_count=1,
            readme_excerpt="other",
            pushed_at=None,
        )
    ]

    verdicts = AnthropicClient(api_key="k", model="claude-sonnet-5").verify_claims(
        [_CLAIMS[0]], two_repos
    )

    assert instance.messages.create.call_count == 2  # one call per batch
    assert verdicts[0].verdict == "backed"  # backed in any batch wins the merge
    assert verdicts[0].cited_files == ("repo-a/cache.go",)


def test_verify_unparseable_raises(mocker: MockerFixture) -> None:
    instance = _patch_sdk(mocker)
    instance.messages.create.return_value = _text_response("not json at all")

    with pytest.raises(AnthropicError):
        AnthropicClient(api_key="k", model="claude-sonnet-5").verify_claims(_CLAIMS, _evidence())
