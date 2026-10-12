# Provider script (ElevenLabs v2, Amelia)

Generated from voiceover_script/script.md. Section breaks are paragraph breaks; prosody comes from punctuation only, no v3 emotion tags.

Procurement teams compare a supplier agreement, a payment policy and an invoice
by hand. A language model answer that cannot show where it came from is not
usable evidence. Sovra Verify audits the corpus and returns the exact passages.

Sovra Verify starts from a corpus. Four synthetic documents go in: a master
supply agreement, an accounts payable policy, an invoice, and an amendment.
Each file is hashed, and its text is extracted into canonical passages with page
and character offsets. Scanned pages are refused, not guessed at.

Apertus one point five 70 billion, hosted on CSCS, reads the passages and
nominates typed claims. It found 25 claims, and Sovra Verify compared 10
candidate pairs. Thirteen provider calls, none failed, with fifteen thousand six
hundred and fifty tokens and seventy one seconds of latency.

The master supply agreement says payment is due within 30 days of the invoice
date. The accounts payable policy says invoices are settled within 60 days,
under the same effective date. Both quotes are sliced from canonical text at the
recorded offsets. The model never writes the quote.

Two of the pairs are not conflicts. The expedited freight clause sets a 10 day
period as a stated exception, and the amendment changes payment to 45 days,
effective the first of May 2026. Sovra Verify flags potential inconsistencies
for a human reviewer. It does not decide which document wins.

A reviewer confirms or dismisses each finding, and the decision is recorded with
a note. Export carries the source hash, the page, the character offsets, and the
model that produced the run.

On four documents: 25 claims, 10 pairs compared, 13 calls, zero failures, and
every displayed citation resolved to an exact slice of canonical text. CSCS
hosted inference is external network inference, so a local app calling CSCS is
not air gapped.
