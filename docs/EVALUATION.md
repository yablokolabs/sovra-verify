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
