# Voiceover script — Sovra Verify two-minute demo

Assembled from each segment's `voiceover` field. Regenerate with
`npx videowright script --write` from the Videowright project root.

Narration pace: measured at 2.2 words per second (Alice, ElevenLabs
`eleven_multilingual_v2`). The script below is the trimmed version; the first
generation ran 138 s and was cut to fit the official two-minute limit.

| Segment | Words | Measured narration |
|---|---|---|
| sovra-problem | 31 | 13.4 s |
| sovra-corpus | 33 | 13.2 s |
| sovra-run | 31 | 13.9 s |
| sovra-finding | 37 | 14.8 s |
| sovra-negative | 45 | 16.7 s |
| sovra-review-export | 31 | 13.4 s |
| sovra-results | 41 | 17.5 s |
| **Total** | **249** | **102.9 s** |

## sovra-problem

Procurement teams compare a supplier agreement, a payment policy and an invoice
by hand. A model answer that cannot show its source is not evidence. Sovra
Verify returns the exact passages.

## sovra-corpus

Four synthetic documents go in: a master supply agreement, an accounts payable
policy, an invoice, and an amendment. Each file is hashed, and its text becomes
canonical passages with page and character offsets.

## sovra-run

Apertus 1.5 70B, hosted on CSCS, reads the passages and nominates typed claims:
25 claims found, 10 candidate pairs compared, 13 provider calls, none failed,
15,650 tokens, 71 seconds of latency.

## sovra-finding

The agreement says payment is due within 30 days of the invoice date. The policy
says invoices are settled within 60 days, under the same effective date. Both
quotes are sliced from canonical text at the recorded offsets.

## sovra-negative

Two pairs are not conflicts. The expedited freight clause sets a 10 day period
as a stated exception, and the amendment changes payment to 45 days, effective
1 May 2026. Sovra Verify flags potential inconsistencies for a human. It does
not decide which document wins.

## sovra-review-export

A reviewer confirms or dismisses each finding, and the decision is recorded with
a note. Export carries the source hash, the page, the offsets, and the model
that produced the run.

## sovra-results

On four documents: 25 claims, 10 pairs compared, 13 calls, zero failures, and
every displayed citation resolved to an exact slice of canonical text. CSCS
hosted inference is external network inference, so a local app calling CSCS is
not air gapped.
