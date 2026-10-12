"""Provider interface.

Every adapter speaks plain OpenAI-compatible Chat Completions. No adapter
assumes constrained decoding, the Responses API, tool calls or embedding
support: the application validates model output itself with Pydantic.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from ..config import ProviderSettings, mask_secret
from ..models import ProviderRun, utcnow

#: Errors that are worth retrying (transient transport / server problems).
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """A provider failure that is safe to surface (contains no credentials)."""

    def __init__(self, message: str, *, error_class: str = "provider_error", status: int | None = None):
        super().__init__(message)
        self.error_class = error_class
        self.status = status


class AuthError(ProviderError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message, error_class="auth_error", status=status)


class QuotaError(ProviderError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message, error_class="quota_error", status=status)


class ModelUnavailableError(ProviderError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message, error_class="model_unavailable", status=status)


@dataclass(slots=True)
class Completion:
    text: str
    model: str
    usage: dict[str, Any]
    latency_ms: int
    raw_id: str = ""
    finish_reason: str = ""


class Provider(Protocol):
    settings: ProviderSettings

    def list_models(self) -> list[str]:
        ...

    def complete(
        self,
        *,
        system: str,
        user: str,
        mode: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        model: str | None = None,
    ) -> Completion:
        ...

    def health(self) -> dict[str, Any]:
        ...


class OpenAICompatibleProvider:
    """Shared implementation for CSCS, the Hugging Face router and local endpoints."""

    def __init__(self, settings: ProviderSettings, *, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    # -- transport ---------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    def _request_once(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send one request, closing a client we created but never one injected."""
        if self._client is not None:
            return self._client.request(method, url, headers=self._headers(), **kwargs)
        with httpx.Client(timeout=self.settings.timeout_seconds) as client:
            return client.request(method, url, headers=self._headers(), **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.settings.base_url.rstrip('/')}{path}"
        attempts = max(1, self.settings.max_retries + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._request_once(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_error = ProviderError(
                    f"transport error contacting {self.settings.name}: {type(exc).__name__}",
                    error_class="transport_error",
                )
                if attempt + 1 < attempts:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise last_error from None

            if response.status_code in (401, 403):
                raise AuthError(
                    f"{self.settings.name} rejected the credential in "
                    f"{self.settings.credential_env} ({mask_secret(self.settings.api_key)})",
                    status=response.status_code,
                )
            if response.status_code in (402, 429):
                detail = _short_reason(response)
                raise QuotaError(
                    f"{self.settings.name} refused the request as rate-limited or out of credit: {detail}",
                    status=response.status_code,
                )
            if response.status_code in (404, 422) and "model" in response.text.lower():
                raise ModelUnavailableError(
                    f"{self.settings.name} does not serve this model: {_short_reason(response)}",
                    status=response.status_code,
                )
            if response.status_code in RETRYABLE_STATUS:
                last_error = ProviderError(
                    f"{self.settings.name} returned {response.status_code}: {_short_reason(response)}",
                    error_class="transient_error",
                    status=response.status_code,
                )
                if attempt + 1 < attempts:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise last_error
            if response.status_code >= 400:
                raise ProviderError(
                    f"{self.settings.name} returned {response.status_code}: {_short_reason(response)}",
                    status=response.status_code,
                )
            return response
        raise last_error or ProviderError(f"{self.settings.name} request failed")

    # -- interface ---------------------------------------------------------
    def list_models(self) -> list[str]:
        response = self._request("GET", "/models")
        payload = response.json()
        items = payload.get("data", payload if isinstance(payload, list) else [])
        return [str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")]

    def complete(
        self,
        *,
        system: str,
        user: str,
        mode: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        model: str | None = None,
    ) -> Completion:
        chosen = model or self.settings.model
        body: dict[str, Any] = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens or self.settings.max_output_tokens,
        }
        started = time.perf_counter()
        response = self._request("POST", "/chat/completions", json=body)
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            payload = response.json()
        except json.JSONDecodeError:
            raise ProviderError(
                f"{self.settings.name} returned a body that is not JSON", error_class="bad_response"
            ) from None

        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.settings.name} returned no choices", error_class="bad_response")
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        return Completion(
            text=text,
            model=str(payload.get("model") or chosen),
            usage=payload.get("usage") or {},
            latency_ms=latency_ms,
            raw_id=str(payload.get("id") or ""),
            finish_reason=str(choices[0].get("finish_reason") or ""),
        )

    def health(self) -> dict[str, Any]:
        info = self.settings.public_view()
        try:
            models = self.list_models()
            info.update({"reachable": True, "model_count": len(models), "serves_configured_model": self.settings.model in models})
        except ProviderError as exc:
            info.update({"reachable": False, "error_class": exc.error_class, "error_message": str(exc)})
        return info

    # -- bookkeeping -------------------------------------------------------
    def new_run(
        self,
        *,
        mode: str,
        input_hash: str,
        parameters: dict[str, Any] | None = None,
        is_backup: bool = False,
        downgraded_from: str = "",
    ) -> ProviderRun:
        return ProviderRun(
            id=uuid.uuid4().hex[:16],
            provider=self.settings.name,
            model=self.settings.model,
            mode=mode,
            input_hash=input_hash,
            parameters=parameters or {},
            started_at=utcnow(),
            is_backup=is_backup,
            downgraded_from=downgraded_from,
        )


def _short_reason(response: httpx.Response) -> str:
    """A short, credential-free reason string from an error body."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("error", "detail", "message"):
                value = payload.get(key)
                if isinstance(value, dict):
                    value = value.get("message") or value.get("code")
                if isinstance(value, str) and value.strip():
                    return value.strip()[:200]
    except Exception:
        pass
    text = response.text.strip().replace("\n", " ")
    return text[:200] if text else "<empty body>"
