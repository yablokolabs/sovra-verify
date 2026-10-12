# Evaluation

All numbers here are measured, not targeted. They come from
`track_2b/data/evaluation/RESULTS.json`, produced by `make evaluate` on 2026-10-12 against real CSCS
inference (`swiss-ai/Apertus-v1.5-70B`). The raw per-case observations and the provider ledger are in
that file.

## Corpus

`track_2b/data/evaluation/pairs.jsonl` — **25 hand-labelled synthetic pairs**, one JSON object per
line. Categories: `conflict`, `consistent`, `unrelated_entity`, `date_change`, `valid_exception`,
`missing_context`, `adversarial`. Three adversarial rows carry prompt-injection payloads in the
document text. The corpus was written before the prompts were tuned and has not been changed since.

Provenance and labelling rules: `track_2b/data/evaluation/LABELS.md`. Everything in it is
hand-written synthetic text; there is no real company, person or document, and no personal data.

## Measured result

```
run_status: complete          duration: 158.3 s
cases: 25                     provider calls: 41 (0 failed)
```

| Expected \ observed | consistent | potential_conflict | insufficient_evidence | unrelated | abstained | failed |
|---|---|---|---|---|---|---|
| consistent | 3 | 3 | 0 | 0 | 2 | 0 |
| potential_conflict | 0 | 6 | 0 | 0 | 1 | 0 |
| insufficient_evidence | 0 | 2 | 0 | 0 | 5 | 0 |
| unrelated | 0 | 0 | 0 | 0 | 3 | 0 |

| Class | Support | Predicted | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| consistent | 8 | 3 | 3 | 0 | 5 | 1.000 | 0.375 | 0.545 |
| potential_conflict | 7 | 11 | 6 | 5 | 1 | 0.545 | 0.857 | 0.667 |
| insufficient_evidence | 7 | 0 | 0 | 0 | 7 | 0.000 | 0.000 | 0.000 |
| unrelated | 3 | 0 | 0 | 0 | 3 | 0.000 | 0.000 | 0.000 |

| Aggregate | Value |
|---|---|
| Accuracy | **0.36** (9 of 25) |
| Abstention rate | **0.44** (11 of 25) |
| Failed requests | **0.00** (0 of 25) — counted separately from abstentions |
| Resolved citation rate on conflict findings | **100 %** (12 of 12 conflicts carried at least one resolved span) |
| Evidence spans kept | 31 |
| Latency per case | mean 5,541.6 ms, median 5,581 ms, max 10,518 ms |
| Tokens per case | mean 1,502.0, total 37,550 |
| Cases that ever reached the model | **14 of 25** — the other 11 formed no candidate pair |
| Accuracy on the cases the model was asked about | **0.6429** (9 of 14) |
| Cases whose expected relation is a negative, with no inconsistency reported | **0.80** (8 of 10) — the absence of a false alarm, not evidence of correctness |
| False alarms (expected a negative, reported a conflict) | **2** (`eval-020`, `eval-022`) |
| Missed inconsistencies (expected a conflict, reported nothing) | **1** (`eval-002`) |

Per-category accuracy: adversarial 100 %, conflict 75 %, consistent 50 %, valid_exception 25 %,
date_change 0 %, missing_context 0 %, unrelated_entity 0 %.

## What these numbers mean, plainly

**The system is not accurate enough to be trusted as an auditor.** 0.36 accuracy on a 25-case corpus
is a weak result and it is reported as measured.

The dominant error is **abstention, not wrong answers**. 11 of 25 cases produced no finding at all,
because the candidate filter in `compare.build_candidates` requires two claims to align on
normalised predicate, unit, entity and effective date before a model comparison is even attempted.
The one-sentence pairs in this corpus frequently produce claims that do not clear that bar, so the
pair is never compared. Abstaining is safe — no unsupported claim reaches a reviewer — but it is not
useful, and it dominates the result.

Conflicts are the strongest class: recall 0.857 with 100 % of reported conflicts carrying a resolved
citation. That is the design working as intended: a conflict without a validated span is discarded,
so reported conflicts are cited.

Precision on conflicts is 0.545: 5 false positives, all of them the model calling a difference a
conflict that the corpus explains. An earlier version of this document attributed them to the
exception clause never reaching the model. **That was wrong, and the model's own output disproves
it.** The comparison prompt carries both claim passages in full, and the model cited the exception
sentence as its own evidence before judging against it:

| Case | The text the model itself quoted | What the model concluded |
|---|---|---|
| `eval-018` | "Expedited freight invoices accepted under Schedule C are settled within 10 days, **as an exception to Policy 4.1**." | `potential_conflict`: "These values are incompatible for the same predicate without an exception noted in Claim A." |
| `eval-019` | "Purchase order PO-4471 **states otherwise**: this order is settled within 45 days." | `potential_conflict`: "...incompatible for the same predicate without an exception." |
| `eval-020` | "Payment within 30 days." / "Payment within 60 days." | `potential_conflict` — although the prompt says to use `insufficient_evidence` when the governing context is missing |
| `eval-022` | "The period is 60 days." / "The period is 30 days." | `potential_conflict` — "no exception or effective date difference is provided to reconcile this discrepancy", i.e. it noticed the missing context and reported a conflict anyway |

These four failures are the model's judgement on evidence it had read and quoted. They are not a
retrieval miss and not a context gap, and passing more context cannot repair them.

`insufficient_evidence` and `unrelated` score 0.00 recall because the system abstains rather than
emitting those relations for most of their cases. Abstention is arguably the honest behaviour for an
unrelated pair — there is nothing to report — but the corpus labels it as a relation to be produced,
so the metric records a miss. That mismatch between the metric and the interface is itself a finding:
the interface should surface "considered and not reported" as a distinct, visible state rather than
letting it look like a failure.

## Where the 16 misses come from

The single accuracy figure hides two different failures, and only one of them is the model's.

| Group | Cases | What happened |
|---|---|---|
| Compared and correct | 9 | — |
| Compared and misjudged | 5 | The model judged a pair and produced a false-positive conflict |
| Never compared | 11 | No candidate pair was ever formed, so no comparison call was made at all |

Of the 14 cases the model actually judged, it was right 9 times — **0.6429 on the subset it was asked
about**. All five of its errors are false-positive `potential_conflict` judgements:

- `eval-017`, `eval-018`, `eval-019` (`valid_exception`) — the corpus expects `consistent` because the
  second statement declares itself an exception or an override. The model read that declaration,
  quoted it as evidence, and reported a conflict anyway.
- `eval-020`, `eval-022` (`missing_context`) — the model asserted a conflict from fragments that state
  no entity, scope or effective date on either side, which the prompt tells it to answer
  `insufficient_evidence`.

The 11 never-compared cases split further:

- **8 of them are labelled `unrelated` (3) or `insufficient_evidence` (5).** For those, producing no
  finding is the desired behaviour — but the corpus records the missing label as an error, and the
  interface has no distinct "considered and not reported" state, so the outcome is silent rather than
  reported. Counting those eight as correct would give 17 of 25, **0.68**. That is a definitional
  change, not a measured improvement, and it is not claimed as one until the interface can show that
  state to a reviewer.
- **4 of the 11 produced only one claim**, so no pair was even possible: two `consistent` cases and one
  `conflict` case were lost at extraction, not at pairing.
- Across the whole corpus the skip reasons are dominated by `same document` (12 occurrences) and
  `different predicates` (16) — the controlled-vocabulary filter refusing pairs it cannot align.

So the 0.36 is not primarily a model-intelligence result. The dominant causes are the conservative
candidate filter, the missing exception context, and a metric that scores a silent-but-correct
negative as an error.

### What was tried, and what it measured

Two changes were implemented and then measured against the same frozen corpus, with real inference
(prompt version `sovra-prompts-4`, 41 calls, 0 failed, 158.3 s, 37,550 tokens):

1. **Comparison context.** A comparison now receives the other extracted statements of each claim's
   own document, so an exception written beside the term it modifies is in front of the model. The
   plumbing is covered by tests that read the prompt that was actually sent.
2. **Extraction coverage.** The claim prompt now asks for every distinct statement in a passage rather
   than the first, and says that a stated exception, delegation or superseding date is itself a claim.

**Neither change moved the headline number: accuracy is still 9 of 25.** No case changed side. The
reason is in the evidence above: for the three exception cases the model already had the exception
text and judged against it, and the 11 never-compared cases are held back by the candidate filter and
by extraction, not by the prompt wording. This is reported as a measured negative result rather than
as an improvement, and the two changes are kept because they are right on their own terms — a model
should see the document it is judging, and a rule-based filter should not be the only thing deciding
what reaches it — not because they helped.

How the counting was changed, and what it is worth:

3. **Every compared pair is now counted by the relation it was given**, and the API and the interface
   state that outcome: how many pairs were compared, what each was judged, and — when no
   inconsistency was reported — that this means nothing was reported, not that nothing was checked.
   `RESULTS.json` now carries `accuracy_on_compared_cases`, the negative-case clean rate and a
   `diagnostics` block naming the case ids behind each bucket, so any of these figures can be checked
   case by case. `accuracy` itself is **not** redefined: counting the 8 silent negatives as correct
   would give 0.68, and that is stated as what it is — a definitional alternative, not a measurement.

A deterministic short-cut was considered and rejected without shipping it: refusing any conflict whose
claims lack entity, scope and effective date. `eval-001`, a correct conflict, also carries no entity,
scope or effective date, so that rule would suppress correct findings as readily as the wrong ones.
The two `missing_context` false alarms need a different fix: a stated rule that an assertion of
incompatibility requires the *values* to be attached to a stated subject or scope in the claim itself,
not merely absent meta-data.

## Honest limitations of this evaluation

- **Small and synthetic.** 25 hand-written cases. This does not establish real-world performance on
  real procurement documents, and no such claim is made.
- **One corpus, one model.** Measured with `swiss-ai/Apertus-v1.5-70B` only. The optional 8B model was
  not benchmarked, so no comparison between them is reported.
- **Single run per prompt version.** No repeated sampling, so no confidence interval and no
  variance estimate. A temperature of 0 was used, which reduces but does not remove run-to-run
  variation. The corpus has now been run twice, on prompt version `sovra-prompts-3` and again on
  `sovra-prompts-4`, and every case landed on the same side both times. That is weak evidence of
  stability, not a measurement of it.
- **Not measured:** dollar cost (no verified price list), human review time, reviewer agreement, or
  false-positive rate on real documents.
- **The demo corpus and the evaluation corpus differ.** The four-document demo run in the README is a
  separate, larger-corpus observation; its numbers are not part of this table and are not a second
  evaluation.
- **Failed requests are zero here, by luck of timing.** Provider failure handling is covered by unit
  tests with injected 401/402/429/503 responses, not by a live refusal.

## Reproducing

```bash
make evaluate                                  # full corpus, real inference
python3 scripts/evaluate.py --limit 4          # quick subset
```

The script writes `track_2b/data/evaluation/RESULTS.json` with the confusion matrix, per-class
metrics, per-case observations, the provider ledger (model, tokens, latency, failures) and the run
status. A partial run still writes what it measured and is labelled `partial`; the denominator is
always every case in the corpus.
