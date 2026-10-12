"""Provider adapters: error mapping, the model policy guard and secret redaction.

Every test here uses an injected ``httpx.MockTransport``; none contacts CSCS or
Hugging Face.
"""

from __future__ import annotations

import json

import httpx
import pytest

from sovra.config import DEFAULT_MODEL, OPTIONAL_8B_MODEL, ProviderSettings, mask_secret
from sovra.providers import (
    AuthError,
    ModelUnavailableError,
    ProviderError,
    ProviderRouter,
    QuotaError,
    check_model_policy,
)

FAKE = "test-key-not-real-0000000000000000000000"


# -- secret redaction ------------------------------------------------------
def test_mask_secret_never_reveals_the_whole_value() -> None:
    masked = mask_secret("sk-abcdefghijklmnop")
    assert masked != "sk-abcdefghijklmnop"
    assert "sk-abcdefghijklmnop" not in masked
    assert masked.startswith("sk-a")
    assert masked.endswith("(len=19)")


def test_mask_secret_fully_masks_short_values() -> None:
    assert mask_secret("abc") == "***"
    assert mask_secret("") == "<unset>"
    assert mask_secret(None) == "<unset>"


def test_public_view_never_contains_the_raw_key() -> None:
    settings = ProviderSettings(
        name="cscs", base_url="https://example.invalid/v1", model=DEFAULT_MODEL,
        credential_env="CSCS_INFERENCE_API_KEY", api_key=FAKE,
    )
    view = settings.public_view()
    assert FAKE not in json.dumps(view)
    assert view["configured"] is True
    assert view["api_key"] != FAKE
    assert not hasattr(settings, "__dict__") or FAKE not in repr(settings)


def test_public_view_marks_an_absent_key_as_unset() -> None:
    settings = ProviderSettings(
        name="huggingface", base_url="https://example.invalid/v1", model=OPTIONAL_8B_MODEL,
        credential_env="HUGGING_FACE_API_KEY", api_key="",
    )
    assert settings.public_view()["configured"] is False
    assert settings.public_view()["api_key"] == "<unset>"


# -- model policy ----------------------------------------------------------
def test_default_70b_model_is_allowed_on_cscs() -> None:
    check_model_policy("cscs", DEFAULT_MODEL, allow_optional_8b=False)


def test_8b_model_is_refused_when_the_optional_flag_is_off() -> None:
    with pytest.raises(ModelUnavailableError) as excinfo:
        check_model_policy("cscs", OPTIONAL_8B_MODEL, allow_optional_8b=False)
    assert "SOVRA_ALLOW_OPTIONAL_8B" in str(excinfo.value)
    assert excinfo.value.error_class == "model_unavailable"


def test_8b_model_is_allowed_when_the_operator_opts_in() -> None:
    check_model_policy("cscs", OPTIONAL_8B_MODEL, allow_optional_8b=True)
    check_model_policy("cscs", "swiss-ai/Apertus-8B-Instruct-2509", allow_optional_8b=True)


def test_the_huggingface_router_refuses_a_70b_model() -> None:
    with pytest.raises(ModelUnavailableError) as excinfo:
        check_model_policy("huggingface", "swiss-ai/Apertus-70B-Instruct-2509", allow_optional_8b=True)
    assert "Apertus 1.5 70B is unavailable there" in str(excinfo.value)


def test_the_router_refuses_an_8b_model_without_any_http_call(settings, router_factory) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    router = router_factory(settings, handler)
    with pytest.raises(ModelUnavailableError):
        router.complete(
            system="s", user="u", mode="claims", input_hash="h", model=OPTIONAL_8B_MODEL
        )
    assert calls == [], "the model policy must be enforced before any request is sent"
    assert router.runs == []


# -- HTTP error mapping ----------------------------------------------------
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_raise_autherror_and_leak_no_credential(settings, router_factory, status) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "invalid token"}})

    router = router_factory(settings, handler)
    with pytest.raises(AuthError) as excinfo:
        router.complete(system="s", user="u", mode="claims", input_hash="h")
    assert excinfo.value.status == status
    assert FAKE not in str(excinfo.value)
    assert "CSCS_INFERENCE_API_KEY" in str(excinfo.value)


@pytest.mark.parametrize("status", [402, 429])
def test_quota_failures_raise_quotaerror(settings, router_factory, status) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "rate limited"}})

    router = router_factory(settings, handler)
    with pytest.raises(QuotaError) as excinfo:
        router.complete(system="s", user="u", mode="claims", input_hash="h")
    assert excinfo.value.status == status
    assert "rate limited" in str(excinfo.value)


def test_a_model_unavailable_body_maps_to_modelunavailableerror(settings, router_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "model not found: nope"}})

    router = router_factory(settings, handler)
    with pytest.raises(ModelUnavailableError) as excinfo:
        router.complete(system="s", user="u", mode="claims", input_hash="h")
    assert "does not serve this model" in str(excinfo.value)


def test_a_transport_failure_raises_a_provider_error(settings, router_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    router = router_factory(settings, handler)
    with pytest.raises(ProviderError) as excinfo:
        router.complete(system="s", user="u", mode="claims", input_hash="h")
    assert excinfo.value.error_class == "transport_error"


def test_a_response_without_choices_is_rejected(settings, router_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    router = router_factory(settings, handler)
    with pytest.raises(ProviderError):
        router.complete(system="s", user="u", mode="claims", input_hash="h")


def test_an_empty_completion_is_recorded_as_a_failure(settings, router_factory, chat_response_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return chat_response_factory("   ")

    router = router_factory(settings, handler)
    with pytest.raises(ProviderError):
        router.complete(system="s", user="u", mode="claims", input_hash="h")
    assert router.runs, "the failed attempt must be recorded"
    assert router.runs[-1].status == "failed"
    assert router.runs[-1].error_class == "empty_response"


# -- fallback policy -------------------------------------------------------
def test_a_failed_primary_records_a_run_and_does_not_switch_provider(
    settings, router_factory, chat_response_factory
) -> None:
    """With fallback off, the call fails visibly instead of silently switching."""
    settings.allow_backup_fallback = False
    settings.backup.enabled = True
    settings.backup.api_key = FAKE

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "upstream unavailable"}})

    router = router_factory(settings, handler)
    with pytest.raises(ProviderError) as excinfo:
        router.complete(system="s", user="u", mode="compare", input_hash="h")
    assert "Backup fallback is off" in str(excinfo.value)
    assert len(router.runs) == 1
    assert router.runs[0].provider == "cscs"
    assert router.runs[0].status == "failed"
    assert router.runs[0].is_backup is False


def test_the_backup_is_used_only_when_it_is_explicitly_enabled(
    settings, router_factory, chat_response_factory
) -> None:
    settings.allow_backup_fallback = True
    settings.backup.enabled = True
    settings.backup.api_key = FAKE

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        if "8B" in body["model"]:
            return chat_response_factory('{"relation": "unrelated"}', model=body["model"])
        return httpx.Response(503, json={"error": {"message": "upstream unavailable"}})

    router = router_factory(settings, handler)
    completion, run = router.complete(system="s", user="u", mode="compare", input_hash="h")
    assert run.is_backup is True
    assert run.provider == "huggingface"
    assert run.downgraded_from == settings.primary.model
    assert completion.model != settings.primary.model
    assert [r.status for r in router.runs] == ["failed", "ok"]


def test_the_backup_requires_both_the_flag_and_a_credential(settings, router_factory) -> None:
    settings.allow_backup_fallback = True
    settings.backup.enabled = True
    settings.backup.api_key = ""  # no credential for the backup

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "upstream unavailable"}})

    router = router_factory(settings, handler)
    with pytest.raises(ProviderError):
        router.complete(system="s", user="u", mode="compare", input_hash="h")
    assert all(run.is_backup is False for run in router.runs)


def test_list_models_parses_the_openai_shape(settings, router_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": DEFAULT_MODEL}, {"id": OPTIONAL_8B_MODEL}, {"no_id": True}]},
        )

    router = router_factory(settings, handler)
    assert router.list_models("cscs") == [DEFAULT_MODEL, OPTIONAL_8B_MODEL]


def test_health_reports_unreachable_without_leaking_the_key(settings, router_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad token"}})

    router = router_factory(settings, handler)
    health = router.health("cscs")
    assert health["reachable"] is False
    assert FAKE not in json.dumps(health)


def test_health_reports_the_configured_model_status(settings, router_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": DEFAULT_MODEL}]})

    router = router_factory(settings, handler)
    health = router.health("cscs")
    assert health["reachable"] is True
    assert health["serves_configured_model"] is True


def test_usage_and_model_are_recorded_on_a_successful_run(
    settings, router_factory, chat_response_factory
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return chat_response_factory('{"relation": "consistent"}')

    router = router_factory(settings, handler)
    _completion, run = router.complete(system="s", user="u", mode="compare", input_hash="h")
    assert run.status == "ok"
    assert run.usage["total_tokens"] == 18
    assert run.latency_ms is not None
    assert run.model == DEFAULT_MODEL
    assert run.parameters["temperature"] == 0.0


def test_unknown_provider_name_is_rejected(settings, router_factory) -> None:
    router = router_factory(settings, lambda request: httpx.Response(200, json={}))
    with pytest.raises(ProviderError):
        router.get("not-a-provider")


@pytest.mark.network
def test_live_provider_access_is_opt_in_and_never_reads_a_credential() -> None:
    """Placeholder for a live check.

    Deliberately does no I/O and reads no credential: a live round trip belongs
    in ``scripts/verify_providers.py``, which is run by a human who knows which
    account the request will be billed to. This test exists so the ``network``
    marker and the skip path are exercised by the suite.
    """
    pytest.skip("live provider checks live in scripts/verify_providers.py")


def test_provider_base_urls_match_the_documented_endpoints() -> None:
    from sovra.config import CSCS_BASE_URL, HF_BASE_URL

    assert CSCS_BASE_URL == "https://api.inference.cscs.ch/v1"
    assert HF_BASE_URL == "https://router.huggingface.co/v1"
