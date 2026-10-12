"""Comparison context and outcome counting.

Two behaviours added after the evaluation showed the model judging a difference
without ever being shown the sentence that explained it:

* the other extracted statements of a claim's own document are sent with the
  comparison, because an exception or a superseding date is normally written beside
  the term it modifies and same-document claims are never paired;
* every compared pair is counted by the relation it was given, so a run that reports
  no inconsistency states that it looked and found none.

Nothing here contacts a provider: the transport is an ``httpx.MockTransport``, and
the prompt that was actually sent is captured from the handler.
"""

from __future__ import annotations

import json
import re

import httpx

from sovra.claims import with_normalized_keys
from sovra.compare import MAX_CONTEXT_PASSAGES_PER_SIDE, Candidate, Comparer
from sovra.config import DEFAULT_MODEL
from sovra.models import Claim, Passage
from sovra.providers import ProviderRouter

CONTEXT_HEADER_A = "Other statements in claim A's document (context):"
CONTEXT_HEADER_B = "Other statements in claim B's document (context):"
PASSAGES_HEADER = "Available passages:"


class RecordingClient:
    """A client over one mock transport that records every prompt it sent."""

    def __init__(self, content: str):
        self.prompts: list[str] = []
        self._content = content
        self._transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        messages = body.get("messages") or []
        if len(messages) > 1:
            self.prompts.append(str(messages[1].get("content", "")))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-context-test",
                "object": "chat.completion",
                "model": DEFAULT_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": self._content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            },
        )

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        with httpx.Client(transport=self._transport, timeout=5.0) as client:
            return client.request(method, url, **kwargs)

    def __enter__(self) -> "RecordingClient":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def close(self) -> None:
        return None


def make_passage(passage_id: str, document_id: str, text: str) -> Passage:
    return Passage(
        id=passage_id,
        document_id=document_id,
        page=1,
        text=text,
        start_offset=0,
        end_offset=len(text),
    )


def make_claim(claim_id: str, document_id: str, passage_id: str, value: str = "30 days") -> Claim:
    return with_normalized_keys(
        Claim(
            id=claim_id,
            document_id=document_id,
            subject="unknown",
            predicate="Payment term",
            value=value,
            unit="days",
            scope="unknown",
            effective_date="unknown",
            source_passage_id=passage_id,
            quote_start=0,
            quote_end=10,
            quote="quote text",
        )
    )


def section(message: str, header: str, until: str) -> str:
    """The prompt text between two headers."""
    start = message.index(header) + len(header)
    end = message.index(until, start)
    return message[start:end]


def build(settings, content: str, *, siblings: list[Passage] | None) -> tuple[object, RecordingClient]:
    """Run one comparison and return (outcome, the client that saw the prompt)."""
    left = make_claim("c-left", "doc-a", "doc-a-p0")
    right = make_claim("c-right", "doc-b", "doc-b-p0", value="60 days")
    passages = {
        "doc-a-p0": make_passage(
            "doc-a-p0", "doc-a", "Clause 7.2 The Buyer shall pay within 30 days of the invoice date."
        ),
        "doc-b-p0": make_passage(
            "doc-b-p0", "doc-b", "Policy 4.1 All supplier invoices are settled within 60 days."
        ),
    }
    for passage in siblings or []:
        passages[passage.id] = passage

    client = RecordingClient(content)
    router = ProviderRouter(settings, client=client)
    comparer = Comparer(router, settings, extractor=None)  # type: ignore[arg-type]
    context = None
    if siblings is not None:
        context = {
            "doc-a": [passages["doc-a-p0"], *siblings],
            "doc-b": [passages["doc-b-p0"]],
        }
    outcome = comparer.compare(
        analysis_id="analysis-1",
        candidates=[Candidate(left, right, 1.0, "")],
        passages_by_id=passages,
        canonical_by_document={
            "doc-a": passages["doc-a-p0"].text,
            "doc-b": passages["doc-b-p0"].text,
        },
        document_names={"doc-a": "agreement.txt", "doc-b": "policy.txt"},
        context_by_document=context,
    )
    return outcome, client


def test_sibling_statements_of_the_same_document_reach_the_model(settings) -> None:
    sibling = make_passage(
        "doc-a-c9",
        "doc-a",
        "Clause 9.1 Expedited freight is settled within 10 days, as an exception to clause 7.2.",
    )
    _, client = build(
        settings, '{"relation": "consistent", "cited_spans": []}', siblings=[sibling]
    )
    sent = client.prompts[-1]
    context_a = section(sent, CONTEXT_HEADER_A, CONTEXT_HEADER_B)
    assert "doc-a-c9" in context_a
    assert "Expedited freight" in context_a
    # Citable, so it is listed among the available passages too.
    assert "doc-a-c9" in sent[sent.index(PASSAGES_HEADER) :]
    # The two claims under comparison are not repeated as their own context.
    assert "doc-a-p0" not in context_a
    assert "doc-b-p0" not in context_a


def test_absent_context_is_stated_rather_than_left_blank(settings) -> None:
    _, client = build(settings, '{"relation": "consistent", "cited_spans": []}', siblings=None)
    assert "none: this document carries no other extracted statement" in client.prompts[-1]


def test_context_is_capped_per_side(settings) -> None:
    siblings = [
        make_passage(f"doc-a-c{i}", "doc-a", f"Clause 9.{i} A separate statement number {i}.")
        for i in range(1, 8)
    ]
    _, client = build(settings, '{"relation": "consistent", "cited_spans": []}', siblings=siblings)
    sent = client.prompts[-1]
    context_a = section(sent, CONTEXT_HEADER_A, CONTEXT_HEADER_B)
    rendered = set(re.findall(r"doc-a-c\d+", context_a))
    assert len(rendered) == MAX_CONTEXT_PASSAGES_PER_SIDE
    # Nothing from the other document leaks into this side's context.
    assert "doc-a-c7" not in context_a


def test_every_judged_pair_is_counted_by_the_relation_it_was_given(settings) -> None:
    outcome, _ = build(
        settings, '{"relation": "consistent", "cited_spans": []}', siblings=None
    )
    assert outcome.outcomes == {"consistent": 1}
    assert outcome.without_finding == 0


def test_a_comparison_without_a_usable_judgement_is_counted_separately(settings) -> None:
    outcome, _ = build(settings, "this is not JSON at all", siblings=None)
    assert outcome.findings == []
    assert outcome.outcomes == {}
    assert outcome.without_finding == 1
