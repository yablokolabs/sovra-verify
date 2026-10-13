# Voiceover script — Sovra Verify two-minute demo

This is the narration as recorded, in the order the film plays it. Each section
is one paragraph of the provider input; the table's spans are the segment
lengths derived from the provider's word alignment, so each section ends exactly
where the next paragraph's first word begins. Assembled by
`scripts/derive-advances.mjs`; `--check` fails when this file, the segment
`voiceover` fields and the recorded take stop agreeing.

Narration pace: measured at 2.14 words per second over the recorded take
(alice-uk-v2, ElevenLabs `eleven_multilingual_v2`). The first generation ran 138 s
and was cut to fit the official two-minute demonstration limit.

| Segment | Words | Recorded span |
|---|---|---|
| sovra-problem | 31 | 13.65 s |
| sovra-corpus | 28 | 13.22 s |
| sovra-run | 25 | 13.54 s |
| sovra-finding | 38 | 15.43 s |
| sovra-negative | 45 | 21.21 s |
| sovra-review-export | 24 | 11.16 s |
| sovra-results | 56 | 27.01 s |
| **Total** | **247** | **115.22 s** |

## sovra-problem

Procurement teams compare a supplier agreement, a payment policy and an
invoice by hand. A model answer that cannot show its source is not evidence.
Sovra Verify returns the exact passages.

## sovra-corpus

Four synthetic documents go in: a master supply agreement, an accounts
payable policy, an invoice, and an amendment. Each file is hashed, and its
text becomes canonical passages.

## sovra-run

Apertus 1.5 70B, hosted on CSCS, reads the passages and nominates typed
claims: 25 claims found, 10 candidate pairs compared, 13 provider calls,
none failed.

## sovra-finding

The agreement says payment is due within 30 days of the invoice date. The
policy says invoices are settled within 60 days, under the same effective
date. Both quotes are sliced from canonical text at the recorded offsets.

## sovra-negative

Two pairs are not conflicts. The expedited freight clause sets a 10 day
period as a stated exception, and the amendment changes payment to 45 days,
effective 1 May 2026. Sovra Verify flags potential inconsistencies for a
human. It does not decide which document wins.

## sovra-review-export

A reviewer confirms or dismisses each finding, and the decision is recorded.
Export carries the source hash, the page, the offsets, and the model.

## sovra-results

On four documents, every displayed citation resolved to an exact slice of
canonical text. CSCS hosted inference is external network inference. A local
application calling CSCS is not air gapped, and Swiss inference residency
does not establish residency of the whole application. These figures are one
run over four synthetic documents, not a general accuracy claim.
