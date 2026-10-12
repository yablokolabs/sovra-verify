"""Sovra Verify application configuration.

Provider policy (explicit, never silent):

* primary provider   : CSCS  (`https://api.inference.cscs.ch/v1`)
* default model      : ``swiss-ai/Apertus-v1.5-70B``
* backup provider    : Hugging Face router (opt-in only)
* 8B models          : optional, only when the operator explicitly selects one

The 70B model is never silently replaced by an 8B model. If the configured
model cannot be served the call fails visibly and the failure is recorded.

Credential handling
-------------------
Credentials are read, in order of precedence:

1. the process environment (how Docker and CI inject them), then
2. ``~/.hermes/.env`` through a dotenv parser, for local development.

Only known, named application keys are ever pulled out of that file. The file
is never shell-sourced, dumped, copied into the repository, committed or
included in a model prompt. Values are never logged, and every diagnostic that
mentions a credential passes through :func:`mask_secret`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Exact model identifiers, confirmed against the live providers.
# See docs/PROVIDER_VERIFICATION.md for the recorded evidence.
# --------------------------------------------------------------------------
DEFAULT_MODEL = "swiss-ai/Apertus-v1.5-70B"
OPTIONAL_8B_MODEL = "swiss-ai/Apertus-v1.5-8B"

#: Models on the CSCS key that are Apertus and are *not* thinking variants.
KNOWN_APERTUS_MODELS = (
    "swiss-ai/Apertus-v1.5-70B",
    "swiss-ai/Apertus-v1.5-8B",
    "swiss-ai/Apertus-70B-Instruct-2509",
    "swiss-ai/Apertus-8B-Instruct-2509",
)

#: Models the Hugging Face router actually served for this account, verified
#: with a real request. Apertus 1.5 70B is NOT among them.
KNOWN_HF_MODELS = ("swiss-ai/Apertus-8B-Instruct-2509",)

CSCS_BASE_URL = "https://api.inference.cscs.ch/v1"
HF_BASE_URL = "https://router.huggingface.co/v1"

#: Only these variable names are read out of the Hermes credential file.
HERMES_KEY_ALLOWLIST = (
    "CSCS_INFERENCE_API_KEY",
    "HUGGING_FACE_API_KEY",
    "ELEVENLABS_API_KEY",
)

#: Environment aliases mapped onto the canonical application variable name.
_CSCS_ALIASES = ("CSCS_INFERENCE_API_KEY", "CSCS_API_KEY", "CSCS_INFERENCE_KEY")


def mask_secret(value: str | None) -> str:
    """Return a value that is safe to print in logs, arguments and reports."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-2:]} (len={len(value)})"


def hermes_env_path() -> Path:
    """Expand ``~`` for the user that actually runs the process."""
    override = os.environ.get("SOVRA_HERMES_ENV")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".hermes" / ".env"


def _read_hermes_keys(names: tuple[str, ...]) -> dict[str, str]:
    """Pull only the named entries out of the Hermes env file.

    Returns an empty mapping when the file is absent (for example when the
    application runs on a host that has no Hermes installation) or when
    ``SOVRA_READ_HERMES_ENV=0``.
    """
    if os.environ.get("SOVRA_READ_HERMES_ENV", "1") == "0":
        return {}
    path = hermes_env_path()
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - dependency documented in requirements
        return {}
    try:
        parsed = dotenv_values(str(path))
    except Exception:
        # Never let a parse error bubble up with file contents attached.
        return {}
    found: dict[str, str] = {}
    for name in names:
        raw = parsed.get(name)
        if isinstance(raw, str) and raw.strip():
            found[name] = raw.strip()
    return found


@dataclass(slots=True)
class ProviderSettings:
    """Configuration for one OpenAI-compatible inference provider."""

    name: str
    base_url: str
    model: str
    credential_env: str
    timeout_seconds: float = 180.0
    max_output_tokens: int = 2048
    max_retries: int = 2
    enabled: bool = True
    api_key: str = field(default="", repr=False)

    def public_view(self) -> dict[str, Any]:
        """Configuration safe to show in the UI and in usage records."""
        return {
            "provider": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "credential_env": self.credential_env,
            "api_key": mask_secret(self.api_key) if self.api_key else "<unset>",
            "configured": bool(self.api_key),
            "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
            "max_retries": self.max_retries,
            "enabled": self.enabled,
        }


@dataclass(slots=True)
class Settings:
    """Whole-application settings."""

    primary: ProviderSettings
    backup: ProviderSettings
    local: ProviderSettings
    allow_backup_fallback: bool = False
    allow_optional_8b: bool = False
    data_dir: Path = field(default_factory=lambda: Path("track_2b/data"))
    work_dir: Path = field(default_factory=lambda: Path(".sovra_work"))
    max_documents: int = 10
    max_upload_bytes: int = 10 * 1024 * 1024
    max_extracted_chars: int = 400_000
    max_compare_pairs: int = 60
    max_chunk_chars: int = 3_500
    log_prompt_contents: bool = False
    provider_status: dict[str, Any] = field(default_factory=dict)

    @property
    def default_model(self) -> str:
        return self.primary.model

    def public_view(self) -> dict[str, Any]:
        return {
            "primary_provider": self.primary.name,
            "default_model": self.primary.model,
            "backup_provider": self.backup.name,
            "backup_model": self.backup.model,
            "backup_fallback_enabled": self.allow_backup_fallback,
            "optional_8b_enabled": self.allow_optional_8b,
            "limits": {
                "max_documents": self.max_documents,
                "max_upload_bytes": self.max_upload_bytes,
                "max_extracted_chars": self.max_extracted_chars,
                "max_compare_pairs": self.max_compare_pairs,
            },
            "providers": {
                "cscs": self.primary.public_view(),
                "huggingface": self.backup.public_view(),
                "local": self.local.public_view(),
            },
        }


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def load_settings(*, probe: bool = False) -> Settings:
    """Build the application settings.

    Credentials come from the environment first and from the Hermes file
    second, so containers can inject named keys without the file existing.
    """
    hermes = _read_hermes_keys(HERMES_KEY_ALLOWLIST)

    def credential(env_name: str, aliases: tuple[str, ...] = ()) -> str:
        for candidate in (env_name, *aliases):
            if os.environ.get(candidate, "").strip():
                return os.environ[candidate].strip()
        for candidate in (env_name, *aliases):
            if hermes.get(candidate):
                return hermes[candidate]
        return ""

    primary_model = _env("SOVRA_MODEL", DEFAULT_MODEL)
    backup_model = _env("SOVRA_BACKUP_MODEL", KNOWN_HF_MODELS[0])

    primary = ProviderSettings(
        name="cscs",
        base_url=_env("SOVRA_CSCS_BASE_URL", CSCS_BASE_URL),
        model=primary_model,
        credential_env="CSCS_INFERENCE_API_KEY",
        timeout_seconds=float(_env_int("SOVRA_TIMEOUT_SECONDS", 180)),
        max_output_tokens=_env_int("SOVRA_MAX_OUTPUT_TOKENS", 2048),
        max_retries=_env_int("SOVRA_MAX_RETRIES", 2),
        api_key=credential("CSCS_INFERENCE_API_KEY", _CSCS_ALIASES),
    )
    backup = ProviderSettings(
        name="huggingface",
        base_url=_env("SOVRA_HF_BASE_URL", HF_BASE_URL),
        model=backup_model,
        credential_env="HUGGING_FACE_API_KEY",
        timeout_seconds=float(_env_int("SOVRA_TIMEOUT_SECONDS", 180)),
        max_output_tokens=_env_int("SOVRA_MAX_OUTPUT_TOKENS", 2048),
        max_retries=_env_int("SOVRA_MAX_RETRIES", 2),
        api_key=credential("HUGGING_FACE_API_KEY"),
        # The backup provider is never used unless the operator turns it on.
        enabled=_env_flag("SOVRA_BACKUP_ENABLED", False),
    )
    local = ProviderSettings(
        name="local",
        base_url=_env("SOVRA_LOCAL_BASE_URL", "http://127.0.0.1:8000/v1"),
        model=_env("SOVRA_LOCAL_MODEL", DEFAULT_MODEL),
        credential_env="SOVRA_LOCAL_API_KEY",
        timeout_seconds=float(_env_int("SOVRA_TIMEOUT_SECONDS", 180)),
        max_output_tokens=_env_int("SOVRA_MAX_OUTPUT_TOKENS", 2048),
        max_retries=_env_int("SOVRA_MAX_RETRIES", 2),
        api_key=credential("SOVRA_LOCAL_API_KEY"),
        enabled=_env_flag("SOVRA_LOCAL_ENABLED", False),
    )

    settings = Settings(
        primary=primary,
        backup=backup,
        local=local,
        allow_backup_fallback=_env_flag("SOVRA_ALLOW_BACKUP_FALLBACK", False),
        allow_optional_8b=_env_flag("SOVRA_ALLOW_OPTIONAL_8B", False),
        data_dir=Path(_env("SOVRA_DATA_DIR", "track_2b/data")),
        work_dir=Path(_env("SOVRA_WORK_DIR", ".sovra_work")),
        max_documents=_env_int("SOVRA_MAX_DOCUMENTS", 10),
        max_upload_bytes=_env_int("SOVRA_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
        max_extracted_chars=_env_int("SOVRA_MAX_EXTRACTED_CHARS", 400_000),
        max_compare_pairs=_env_int("SOVRA_MAX_COMPARE_PAIRS", 60),
        max_chunk_chars=_env_int("SOVRA_MAX_CHUNK_CHARS", 3_500),
        log_prompt_contents=_env_flag("SOVRA_LOG_PROMPT_CONTENTS", False),
    )
    settings.provider_status = {
        "hermes_env_path": str(hermes_env_path()),
        "hermes_env_present": hermes_env_path().is_file(),
        "hermes_keys_seen": sorted(hermes),
        "model_policy": {
            "default_model": primary.model,
            "optional_8b_model": OPTIONAL_8B_MODEL,
            "silent_downgrade_allowed": False,
        },
    }
    if probe:  # pragma: no cover - network path, exercised by scripts/verify_providers
        settings.provider_status["note"] = "probe requested"
    return settings
