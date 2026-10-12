"""Application configuration: default model, provider policy and credential handling."""

from __future__ import annotations

import json

import pytest

from sovra.config import (
    CSCS_BASE_URL,
    DEFAULT_MODEL,
    HF_BASE_URL,
    OPTIONAL_8B_MODEL,
    load_settings,
    mask_secret,
)

#: Variables that could leak a real value from the ambient environment.
_CREDENTIAL_ENV_VARS = (
    "CSCS_INFERENCE_API_KEY",
    "CSCS_API_KEY",
    "CSCS_INFERENCE_KEY",
    "HUGGING_FACE_API_KEY",
    "SOVRA_LOCAL_API_KEY",
    "SOVRA_MODEL",
    "SOVRA_BACKUP_MODEL",
    "SOVRA_ALLOW_BACKUP_FALLBACK",
    "SOVRA_ALLOW_OPTIONAL_8B",
    "SOVRA_BACKUP_ENABLED",
    "SOVRA_LOCAL_ENABLED",
    "SOVRA_CSCS_BASE_URL",
    "SOVRA_HF_BASE_URL",
    "SOVRA_MAX_DOCUMENTS",
    "SOVRA_MAX_UPLOAD_BYTES",
    "SOVRA_HERMES_ENV",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in _CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOVRA_READ_HERMES_ENV", "0")
    return monkeypatch


def test_default_model_is_apertus_1_5_70b() -> None:
    assert DEFAULT_MODEL == "swiss-ai/Apertus-v1.5-70B"
    assert OPTIONAL_8B_MODEL == "swiss-ai/Apertus-v1.5-8B"


def test_primary_provider_is_cscs_and_backup_is_huggingface(clean_env) -> None:
    settings = load_settings()
    assert settings.primary.name == "cscs"
    assert settings.primary.base_url == CSCS_BASE_URL
    assert settings.primary.model == DEFAULT_MODEL
    assert settings.default_model == DEFAULT_MODEL
    assert settings.backup.name == "huggingface"
    assert settings.backup.base_url == HF_BASE_URL


def test_backup_and_optional_8b_are_off_by_default(clean_env) -> None:
    settings = load_settings()
    assert settings.allow_backup_fallback is False
    assert settings.allow_optional_8b is False
    assert settings.backup.enabled is False
    assert settings.local.enabled is False


def test_silent_downgrade_is_disallowed_in_the_reported_policy(clean_env) -> None:
    settings = load_settings()
    policy = settings.provider_status["model_policy"]
    assert policy["default_model"] == DEFAULT_MODEL
    assert policy["silent_downgrade_allowed"] is False


def test_hermes_file_is_not_read_when_disabled(clean_env) -> None:
    settings = load_settings()
    assert settings.primary.api_key == ""
    assert settings.provider_status["hermes_keys_seen"] == []
    # The path is still reported so an operator can see where a key would come from.
    assert settings.provider_status["hermes_env_path"].replace("\\", "/").endswith(".hermes/.env")


def test_environment_supplies_the_credential_and_wins(clean_env) -> None:
    clean_env.setenv("CSCS_INFERENCE_API_KEY", "test-key-not-real-aaaa")
    settings = load_settings()
    assert settings.primary.api_key == "test-key-not-real-aaaa"
    assert settings.primary.public_view()["configured"] is True


def test_cscs_alias_names_are_accepted(clean_env) -> None:
    clean_env.setenv("CSCS_API_KEY", "test-key-not-real-bbbb")
    settings = load_settings()
    assert settings.primary.api_key == "test-key-not-real-bbbb"


def test_model_override_is_honoured(clean_env) -> None:
    clean_env.setenv("SOVRA_MODEL", OPTIONAL_8B_MODEL)
    clean_env.setenv("SOVRA_ALLOW_OPTIONAL_8B", "1")
    settings = load_settings()
    assert settings.primary.model == OPTIONAL_8B_MODEL
    assert settings.allow_optional_8b is True


def test_limits_have_documented_defaults(clean_env) -> None:
    settings = load_settings()
    assert settings.max_documents == 10
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.max_compare_pairs > 0
    assert settings.max_chunk_chars > 0


def test_limits_can_be_lowered_by_the_environment(clean_env) -> None:
    clean_env.setenv("SOVRA_MAX_DOCUMENTS", "3")
    clean_env.setenv("SOVRA_MAX_UPLOAD_BYTES", "2048")
    settings = load_settings()
    assert settings.max_documents == 3
    assert settings.max_upload_bytes == 2048


def test_invalid_numeric_environment_value_falls_back_to_the_default(clean_env) -> None:
    clean_env.setenv("SOVRA_MAX_DOCUMENTS", "not-a-number")
    assert load_settings().max_documents == 10


def test_public_view_never_contains_a_raw_credential(clean_env) -> None:
    secret = "test-key-not-real-cccc-1234567890"
    clean_env.setenv("CSCS_INFERENCE_API_KEY", secret)
    clean_env.setenv("HUGGING_FACE_API_KEY", "test-key-not-real-dddd")
    payload = json.dumps(load_settings().public_view())
    assert secret not in payload
    assert "test-key-not-real-dddd" not in payload
    assert "CSCS_INFERENCE_API_KEY" in payload  # the variable *name* is fine to show


def test_public_view_blocks_are_keyed_by_provider(clean_env) -> None:
    view = load_settings().public_view()
    assert view["primary_provider"] == "cscs"
    assert view["backup_provider"] == "huggingface"
    assert view["backup_fallback_enabled"] is False
    assert set(view["providers"]) == {"cscs", "huggingface", "local"}


def test_mask_secret_is_used_for_every_reported_credential(clean_env) -> None:
    secret = "test-key-not-real-eeee"
    clean_env.setenv("CSCS_INFERENCE_API_KEY", secret)
    view = load_settings().public_view()
    assert view["providers"]["cscs"]["api_key"] == mask_secret(secret)
    assert view["providers"]["cscs"]["api_key"] != secret
