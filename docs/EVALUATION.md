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
run_status: complete          duration: 133.5 s
cases: 25                     provider calls: 39 (0 failed)
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
| Resolved citation rate on conflict findings | **100 %** (11 of 11 conflicts carried at least one resolved span) |
| Evidence spans kept | 28 |
| Latency per case | mean 5,076.6 ms, median 5,392 ms, max 8,788 ms |
| Tokens per case | mean 1,259.5, total 31,487 |

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

Precision on conflicts is 0.545: 5 false positives. Those are the exception and date-change cases,
where the model called an explained difference a conflict. Two distinct causes are visible in the
per-case rows:

1. `valid_exception` cases lose the clause that states the exception, because the exception clause and
   the differing term usually live in the same document, and two claims from the same document are
   never paired. The comparison therefore cannot see the carve-out it is being asked to respect.
2. `date_change` cases that do reach comparison are judged on the values alone when the effective
   dates were not extracted as `unknown` versus known.

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

Of the 14 cases the model actually judged, it was right 9 times — **0.64 on the subset it was asked
about**. All five of its errors are false-positive `potential_conflict` judgements on a case the corpus
labels `consistent` (a stated exception) or `insufficient_evidence` (no governing context):

- `eval-017`, `eval-018`, `eval-019` (`valid_exception`) — **the exception clause was never in front of
the model.** For `eval-017` the candidate filter dropped the carve-out with the reason `same document`,
so the comparison saw the two differing terms and not the exception that explains them.
- `eval-020`, `eval-022` (`missing_context`) — the model asserted a conflict from fragments that state
no entity, scope or effective date on either side.

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

### Three levers, with what each is worth and what it costs

1. **Pass the exception context into the comparison** — the other statements of a claim's own document,
   at least the same-predicate carve-outs. Targets `eval-017`/`018`/`019`. Ceiling +3 (0.48). Costs a
   prompt and candidate change plus a re-run to measure.
2. **Recover the one-claim cases at extraction** — 4 cases never had a pair to judge. Targets
   `eval-002` (a real conflict) and `eval-007`/`008`. Ceiling +3 (0.48). Costs a schema and prompt
   change plus a re-run.
3. **Surface "considered and not reported"** and score the silent negatives correctly. Targets the 8
   negative cases (0.68 when combined with the current 9 correct). Costs interface and scoring work and
   **no inference**; it is a definitional change and both numbers must be reported.

A deterministic short-cut was considered and rejected without measuring it: refusing any conflict whose
claims lack entity, scope and effective date. `eval-001`, a correct conflict, also has no entity, scope
or effective date in its claims, so that rule would suppress correct findings as readily as the wrong
ones. It is not implemented.

## Honest limitations of this evaluation

- **Small and synthetic.** 25 hand-written cases. This does not establish real-world performance on
  real procurement documents, and no such claim is made.
- **One corpus, one model.** Measured with `swiss-ai/Apertus-v1.5-70B` only. The optional 8B model was
  not benchmarked, so no comparison between them is reported.
- **Single run.** No repeated sampling, so no confidence interval and no variance estimate. A
  temperature of 0 was used, which reduces but does not remove run-to-run variation.
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
