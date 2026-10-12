"""Shared fixtures for the Sovra Verify test suite.

Two hard rules hold for every test here:

* **No test touches the network.** The ``network`` marker is skipped unless
  ``SOVRA_RUN_NETWORK_TESTS=1`` is set. Provider behaviour is exercised through
  an injected ``httpx.MockTransport``.
* **No test reads or prints a real credential.** An autouse fixture forces
  ``SOVRA_READ_HERMES_ENV=0`` so the developer credential file is never parsed
  during a test run. Only obviously fake values such as ``test-key-not-real``
  are used.

The injected test client deserves a note. ``OpenAICompatibleProvider._request``
wraps every call in ``with self._client_for() as client:``, which closes an
injected client after the first request. A plain injected ``httpx.Client``
therefore works once and fails afterwards, so :class:`InjectedTestClient` keeps
the ``httpx.MockTransport`` and builds a fresh ``httpx.Client`` per request
while exposing the no-op context-manager protocol the provider expects.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx
import pytest

TESTS_DIR = Path(__file__).resolve().parent
TRACK_DIR = TESTS_DIR.parent
BACKEND_DIR = TRACK_DIR / "backend"
FRONTEND_DIR = TRACK_DIR / "frontend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sovra.config import (  # noqa: E402
    CSCS_BASE_URL,
    DEFAULT_MODEL,
    HF_BASE_URL,
    OPTIONAL_8B_MODEL,
    ProviderSettings,
    Settings,
)
from sovra.providers import ProviderRouter  # noqa: E402
from sovra.storage import Storage  # noqa: E402

#: Canned backup model. Never the 70B default, so a fallback is visible.
BACKUP_MODEL = "swiss-ai/Apertus-8B-Instruct-2509"

#: Credential-looking but obviously fake. Never a real value.
FAKE_KEY = "test-key-not-real-0000000000000000000000"

PASSAGE_REF_RE = re.compile(r'passage_id="([^"]+)"[^\n]*offsets=\[(\d+),\s*(\d+)\]')


# --------------------------------------------------------------------------
# pytest configuration
# --------------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: requires real network access (skipped by default)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("SOVRA_RUN_NETWORK_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="network test: set SOVRA_RUN_NETWORK_TESTS=1 to enable")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _never_read_real_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's credential file out of every test."""
    monkeypatch.setenv("SOVRA_READ_HERMES_ENV", "0")


# --------------------------------------------------------------------------
# transport-level doubles
# --------------------------------------------------------------------------
class InjectedTestClient:
    """A ``httpx.MockTransport`` wrapper safe to use across several requests."""

    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []
        self._transport = httpx.MockTransport(self._dispatch)

    def _dispatch(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def request(self, method: str, url: str, **kwargs):
        with httpx.Client(transport=self._transport, timeout=5.0) as client:
            return client.request(method, url, **kwargs)

    # The provider wraps each call in ``with``; these keep it reusable.
    def __enter__(self) -> "InjectedTestClient":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def close(self) -> None:  # pragma: no cover - never needs real teardown
        return None


def chat_body(content: str, *, model: str = DEFAULT_MODEL, finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def chat_response(
    content: str,
    *,
    status_code: int = 200,
    model: str = DEFAULT_MODEL,
    finish_reason: str = "stop",
) -> httpx.Response:
    return httpx.Response(
        status_code, json=chat_body(content, model=model, finish_reason=finish_reason)
    )


def json_response(payload: dict, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def request_body(request: httpx.Request) -> dict:
    """Decode a captured request body, tolerating bodies that have none."""
    raw = request.content.decode("utf-8") if request.content else ""
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def request_messages(request: httpx.Request) -> tuple[str, str]:
    """Return (system, user) text from a captured chat-completions request."""
    messages = request_body(request).get("messages") or []
    system = messages[0].get("content", "") if messages else ""
    user = messages[1].get("content", "") if len(messages) > 1 else ""
    return system, user


def claims_from_prompt(user: str) -> dict:
    """Build one synthetic claim per passage referenced in a claim prompt."""
    claims = []
    for block in user.split('- passage_id="')[1:]:
        passage_id = block.split('"', 1)[0]
        offsets = re.search(r"offsets=\[(\d+),\s*(\d+)\]", block)
        if not offsets:
            continue
        days = re.search(r"(\d{1,4})\s*days", block)
        claims.append(
            {
                "passage_id": passage_id,
                "subject": "unknown",
                "predicate": "payment term",
                "value": days.group(1) if days else "unknown",
                "unit": "days",
                "scope": "unknown",
                "effective_date": "unknown",
                "quote_start": int(offsets.group(1)),
                "quote_end": int(offsets.group(2)),
            }
        )
    return {"claims": claims}


def compare_from_prompt(user: str) -> dict:
    """Claim a potential conflict and cite the first two referenced passages."""
    spans = [
        {"passage_id": pid, "start_offset": int(start), "end_offset": int(end)}
        for pid, start, end in PASSAGE_REF_RE.findall(user)[:2]
    ]
    return {
        "relation": "potential_conflict",
        "reasoning": "Synthetic mock: the stated payment periods differ under the same predicate.",
        "cited_spans": spans,
        "limitations": ["synthetic mock output, not a model judgement"],
    }


def canned_handler(request: httpx.Request) -> httpx.Response:
    """Dispatch canned claim/compare JSON based on the system message."""
    if request.method == "GET" and request.url.path.rstrip("/").endswith("/models"):
        return json_response({"data": [{"id": DEFAULT_MODEL}, {"id": BACKUP_MODEL}]})
    system, user = request_messages(request)
    model = request_body(request).get("model", DEFAULT_MODEL)
    if "procurement-document analyst" in system:
        return chat_response(json.dumps(claims_from_prompt(user)), model=model)
    return chat_response(json.dumps(compare_from_prompt(user)), model=model)


def failing_handler(status_code: int = 401):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "synthetic failure"}})

    return handler


# --------------------------------------------------------------------------
# object factories
# --------------------------------------------------------------------------
def build_settings(tmp_path: Path, **overrides) -> Settings:
    """Settings with fabricated credentials and no retry sleeps."""
    primary = ProviderSettings(
        name="cscs",
        base_url=CSCS_BASE_URL,
        model=DEFAULT_MODEL,
        credential_env="CSCS_INFERENCE_API_KEY",
        api_key=FAKE_KEY,
        max_retries=0,
        timeout_seconds=5.0,
    )
    backup = ProviderSettings(
        name="huggingface",
        base_url=HF_BASE_URL,
        model=BACKUP_MODEL,
        credential_env="HUGGING_FACE_API_KEY",
        api_key="",
        enabled=False,
        max_retries=0,
        timeout_seconds=5.0,
    )
    local = ProviderSettings(
        name="local",
        base_url="http://127.0.0.1:8000/v1",
        model=DEFAULT_MODEL,
        credential_env="SOVRA_LOCAL_API_KEY",
        api_key="",
        enabled=False,
        max_retries=0,
        timeout_seconds=5.0,
    )
    kwargs: dict = {
        "primary": primary,
        "backup": backup,
        "local": local,
        "work_dir": tmp_path / "work",
        "data_dir": tmp_path / "data",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


@pytest.fixture
def make_settings(tmp_path: Path):
    def factory(**overrides) -> Settings:
        return build_settings(tmp_path, **overrides)

    return factory


@pytest.fixture
def settings(make_settings) -> Settings:
    return make_settings()


@pytest.fixture
def storage(settings: Settings) -> Storage:
    store = Storage(settings.work_dir / "sovra.sqlite3")
    yield store
    store.close()


@pytest.fixture
def injected_client():
    return InjectedTestClient


@pytest.fixture
def chat_response_factory():
    return chat_response


@pytest.fixture
def router_factory(injected_client):
    def factory(settings: Settings, handler) -> ProviderRouter:
        return ProviderRouter(settings, client=injected_client(handler))

    return factory


@pytest.fixture
def canned_handler_fn():
    """The canned claim/compare handler, as a fixture so it is reusable."""
    return canned_handler


@pytest.fixture
def failing_handler_fn():
    """A handler that fails every call, as a fixture."""
    return failing_handler


@pytest.fixture
def canned_router(settings: Settings, router_factory) -> ProviderRouter:
    return router_factory(settings, canned_handler)


@pytest.fixture
def api_client(make_settings, monkeypatch):
    """A FastAPI TestClient whose provider layer is fully offline."""
    from fastapi.testclient import TestClient

    import sovra.api as api_module

    def factory(**overrides):
        settings = make_settings(**overrides)
        settings.work_dir.mkdir(parents=True, exist_ok=True)
        store = Storage(settings.work_dir / "sovra.sqlite3")

        def offline_router(router_settings, **_kwargs):
            return ProviderRouter(router_settings, client=InjectedTestClient(canned_handler))

        monkeypatch.setattr(api_module, "ProviderRouter", offline_router)
        app = api_module.create_app(settings, storage=store)
        return TestClient(app), settings, store

    created: list[Storage] = []

    def tracked_factory(**overrides):
        client, settings, store = factory(**overrides)
        created.append(store)
        return client, settings

    yield tracked_factory
    for store in created:
        store.close()


# --------------------------------------------------------------------------
# reusable source fixtures (synthetic only)
# --------------------------------------------------------------------------
AGREEMENT_TEXT = (
    "Clause 7.2 Payment terms\n"
    "The Buyer shall pay each undisputed invoice within 30 days of the invoice date.\n"
)
POLICY_TEXT = (
    "Policy 4.1 Standard settlement period\n"
    "All supplier invoices are settled within 60 days of the invoice date.\n"
)


@pytest.fixture
def two_document_corpus(settings, storage):
    """Ingest two synthetic documents and return their ids."""
    from sovra.pipeline import SovraService

    service = SovraService(settings, storage, ProviderRouter(settings))
    first = service.ingest(filename="agreement.txt", data=AGREEMENT_TEXT.encode(), mime="text/plain")
    second = service.ingest(filename="policy.txt", data=POLICY_TEXT.encode(), mime="text/plain")
    return first.document.id, second.document.id
