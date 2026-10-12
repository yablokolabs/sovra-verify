"""Concrete provider adapters and the explicit activation policy."""

from __future__ import annotations

from typing import Any

from ..config import (
    DEFAULT_MODEL,
    OPTIONAL_8B_MODEL,
    ProviderSettings,
    Settings,
)
from ..models import ProviderRun, utcnow
from .base import (
    AuthError,
    Completion,
    ModelUnavailableError,
    OpenAICompatibleProvider,
    Provider,
    ProviderError,
    QuotaError,
)

_ERROR_CLASSES = {
    "auth_error": AuthError,
    "quota_error": QuotaError,
    "model_unavailable": ModelUnavailableError,
}


BACKUP_OFF_NOTE = (
    "Backup fallback is off (SOVRA_ALLOW_BACKUP_FALLBACK=0), so the analysis fails "
    "visibly instead of switching providers."
)


def _raisable_from_run(run: ProviderRun, *, backup_off: bool) -> ProviderError:
    """Rebuild the original error type from a recorded run.

    The caller needs the real class (an auth failure is not the same as a
    transient one) while the message still has to say that no provider switch
    happened. The message never contains a credential value: provider messages
    are already masked at source.
    """
    message = run.error_message or run.error_class or "provider call failed"
    if backup_off:
        message = f"{message} {BACKUP_OFF_NOTE}"
    error_cls = _ERROR_CLASSES.get(run.error_class, ProviderError)
    if error_cls is ProviderError:
        return ProviderError(message, error_class=run.error_class or "provider_error", status=run.http_status)
    return error_cls(message, status=run.http_status)

__all__ = [
    "AuthError",
    "CSCSProvider",
    "Completion",
    "HuggingFaceProvider",
    "LocalProvider",
    "ModelUnavailableError",
    "OpenAICompatibleProvider",
    "Provider",
    "ProviderError",
    "ProviderRouter",
    "QuotaError",
    "build_provider",
    "check_model_policy",
]


class CSCSProvider(OpenAICompatibleProvider):
    """Primary provider: CSCS-hosted Apertus 1.5."""

    name = "cscs"


class HuggingFaceProvider(OpenAICompatibleProvider):
    """Backup provider: the Hugging Face inference router.

    Verified on 2026-10-12: this account's router serves
    ``swiss-ai/Apertus-8B-Instruct-2509`` only. ``swiss-ai/Apertus-v1.5-70B`` is
    mapped to an upstream provider marked ``status: error`` and is not
    servable, so the backup cannot stand in for the 70B default.
    """

    name = "huggingface"


class LocalProvider(OpenAICompatibleProvider):
    """Configurable on-premise / air-gapped Apertus endpoint (OpenAI-compatible)."""

    name = "local"


def build_provider(settings: ProviderSettings) -> OpenAICompatibleProvider:
    if settings.name == "cscs":
        return CSCSProvider(settings)
    if settings.name == "huggingface":
        return HuggingFaceProvider(settings)
    return LocalProvider(settings)


def check_model_policy(provider_name: str, model: str, *, allow_optional_8b: bool) -> None:
    """Refuse silent downgrades.

    The configured default is Apertus 1.5 70B. Selecting an 8B model is allowed
    only when the operator turns it on explicitly. Nothing here ever rewrites a
    70B request into an 8B request.
    """
    if model == DEFAULT_MODEL:
        return
    if "8B" in model.upper() and not allow_optional_8b:
        raise ModelUnavailableError(
            f"model '{model}' is an optional 8B model and SOVRA_ALLOW_OPTIONAL_8B is off; "
            f"the application will not downgrade from {DEFAULT_MODEL} silently. "
            "Set SOVRA_ALLOW_OPTIONAL_8B=1 to select it deliberately.",
            status=None,
        )
    if provider_name == "huggingface" and model not in {OPTIONAL_8B_MODEL, "swiss-ai/Apertus-8B-Instruct-2509"}:
        raise ModelUnavailableError(
            f"the Hugging Face router does not serve '{model}' for this account; "
            "Apertus 1.5 70B is unavailable there. Use CSCS for 70B, or select the "
            "8B backup model explicitly.",
            status=None,
        )


class ProviderRouter:
    """Routes calls to exactly one provider and records what actually happened.

    Fallback to the backup provider happens only when
    ``SOVRA_ALLOW_BACKUP_FALLBACK`` is on *and* the backup is enabled. Every
    attempt, including a refusal to fall back, is written to the run ledger.
    """

    def __init__(self, settings: Settings, *, client: Any = None):
        self.settings = settings
        self._client = client
        self.runs: list[ProviderRun] = []
        self._providers: dict[str, OpenAICompatibleProvider] = {}
        for cfg in (settings.primary, settings.backup, settings.local):
            provider = build_provider(cfg)
            if client is not None:
                provider._client = client  # noqa: SLF001 - deliberate test seam
            self._providers[cfg.name] = provider

    # -- registry ----------------------------------------------------------
    @property
    def active(self) -> OpenAICompatibleProvider:
        return self._providers[self.settings.primary.name]

    @property
    def backup(self) -> OpenAICompatibleProvider:
        return self._providers[self.settings.backup.name]

    def get(self, name: str) -> OpenAICompatibleProvider:
        if name not in self._providers:
            raise ProviderError(f"unknown provider '{name}'", error_class="config_error")
        return self._providers[name]

    # -- behaviour ---------------------------------------------------------
    def list_models(self, provider_name: str | None = None) -> list[str]:
        provider = self.get(provider_name) if provider_name else self.active
        return provider.list_models()

    def health(self, provider_name: str | None = None) -> dict[str, Any]:
        provider = self.get(provider_name) if provider_name else self.active
        return provider.health()

    def complete(
        self,
        *,
        system: str,
        user: str,
        mode: str,
        input_hash: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        model: str | None = None,
        prefer_backup: bool = False,
    ) -> tuple[Completion, ProviderRun]:
        primary = self.active
        chosen_model = model or primary.settings.model
        check_model_policy(
            primary.settings.name,
            chosen_model,
            allow_optional_8b=self.settings.allow_optional_8b,
        )

        run = self._complete_with(
            primary,
            system=system,
            user=user,
            mode=mode,
            input_hash=input_hash,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            model=chosen_model,
            is_backup=False,
        )
        if run.status == "ok":
            self.runs.append(run)
            return self._last_completion, run

        backup = self.backup
        if prefer_backup or (self.settings.allow_backup_fallback and backup.settings.enabled and backup.settings.api_key):
            backup_run = self._complete_with(
                backup,
                system=system,
                user=user,
                mode=mode,
                input_hash=input_hash,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                model=backup.settings.model,
                is_backup=True,
                downgraded_from=primary.settings.model if backup.settings.model != primary.settings.model else "",
            )
            if backup_run.status == "ok":
                self.runs.extend([run, backup_run])
                return self._last_completion, backup_run
            self.runs.extend([run, backup_run])
            raise ProviderError(
                f"primary provider failed ({run.error_class}) and the backup also failed "
                f"({backup_run.error_class}); no silent further fallback is attempted",
                error_class="all_providers_failed",
            )

        self.runs.append(run)
        raise _raisable_from_run(run, backup_off=True)

    # -- internals ---------------------------------------------------------
    def _complete_with(
        self,
        provider: OpenAICompatibleProvider,
        *,
        system: str,
        user: str,
        mode: str,
        input_hash: str,
        temperature: float,
        max_output_tokens: int | None,
        model: str,
        is_backup: bool,
        downgraded_from: str = "",
    ) -> ProviderRun:
        run = provider.new_run(
            mode=mode,
            input_hash=input_hash,
            parameters={
                "temperature": temperature,
                "max_output_tokens": max_output_tokens or provider.settings.max_output_tokens,
                "prompt_chars": len(system) + len(user),
            },
            is_backup=is_backup,
            downgraded_from=downgraded_from,
        )
        try:
            completion = provider.complete(
                system=system,
                user=user,
                mode=mode,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                model=model,
            )
        except ProviderError as exc:
            run.status = "failed"
            run.error_class = exc.error_class
            run.error_message = str(exc)
            run.http_status = exc.status
        except Exception as exc:  # pragma: no cover - defensive
            run.status = "failed"
            run.error_class = "unexpected_error"
            run.error_message = f"{type(exc).__name__}: {exc}"
        else:
            self._last_completion = completion
            run.finished_at = utcnow()
            run.latency_ms = completion.latency_ms
            run.usage = completion.usage
            run.model = completion.model
            run.status = "ok" if completion.text.strip() else "empty"
            if run.status == "empty":
                run.error_class = "empty_response"
                run.error_message = "provider returned an empty completion"
                run.status = "failed"
        if run.finished_at is None:
            run.finished_at = utcnow()
        return run
