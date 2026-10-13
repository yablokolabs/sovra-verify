# Provider script — take alice-uk-v2

> Sent to elevenlabs, model `eleven_multilingual_v2`, voice "Alice - Clear, Engaging Educator".
> One paragraph per scene, in reading order; prosody comes from punctuation only and no
> model tags are used. This file is the input record for the take, so it is the same
> wording as each scene's `voiceover` field and as `voiceover_script/script.md`.
> `node scripts/derive-advances.mjs --check` fails when either drifts.

Procurement teams compare a supplier agreement, a payment policy and an
invoice by hand. A model answer that cannot show its source is not evidence.
Sovra Verify returns the exact passages.

Four synthetic documents go in: a master supply agreement, an accounts
payable policy, an invoice, and an amendment. Each file is hashed, and its
text becomes canonical passages.

Apertus 1.5 70B, hosted on CSCS, reads the passages and nominates typed
claims: 25 claims found, 10 candidate pairs compared, 13 provider calls,
none failed.

The agreement says payment is due within 30 days of the invoice date. The
policy says invoices are settled within 60 days, under the same effective
date. Both quotes are sliced from canonical text at the recorded offsets.

Two pairs are not conflicts. The expedited freight clause sets a 10 day
period as a stated exception, and the amendment changes payment to 45 days,
effective 1 May 2026. Sovra Verify flags potential inconsistencies for a
human. It does not decide which document wins.

A reviewer confirms or dismisses each finding, and the decision is recorded.
Export carries the source hash, the page, the offsets, and the model.

On four documents, every displayed citation resolved to an exact slice of
canonical text. CSCS hosted inference is external network inference. A local
application calling CSCS is not air gapped, and Swiss inference residency
does not establish residency of the whole application. These figures are one
run over four synthetic documents, not a general accuracy claim.
