## Inspiration

Procurement teams compare a supplier agreement, an accounts payable policy and the invoice that cites it by reading the same numbers in three places. The work is slow, and the failure mode is not "no answer" — it is a confident answer nobody can check. A language model that says two documents conflict, without showing the sentence it read, hands the reviewer a new thing to verify rather than a saved step.

Sovra Verify exists to test one idea: that a model's useful contribution here is reading and judging, while the evidence has to come from somewhere the model cannot author. We wanted to know whether that split holds up when a real model is in the loop, so we built it and measured it instead of arguing about it.

## What it does

Sovra Verify audits a corpus of up to ten text-native documents (PDF or UTF-8 TXT) and reports **potential** inconsistencies for human review. It hashes each original, extracts canonical text with page and character provenance, identifies typed claims with Apertus, compares bounded claim pairs, and resolves every citation deterministically against canonical text.

The model nominates a passage id and an offset pair. The application slices the quote. A finding whose spans do not resolve is rejected before it can reach the interface or a report, so a plausible-sounding fabricated citation cannot become evidence. A reviewer then confirms a finding for review or dismisses it, and the export carries the source hash, page, offsets, model and review state.

It reports potential inconsistencies **in the supplied corpus**. It does not check external truth, does not decide which document legally wins, and does not give legal or compliance advice. A different effective date or a stated exception is treated as an explanation rather than a conflict.

## How we built it

Python 3.12 and FastAPI for the backend, Pydantic for every contract, PyMuPDF for text-native PDF extraction, SQLite for persistence, and a React and TypeScript dashboard built with Vite and served by the backend at `/app`. Docker packaging is multi-stage, and the whole thing is driven by a root Makefile.

Apertus 1.5 70B on CSCS is the primary inference provider via the OpenAI-compatible Chat Completions endpoint at `https://api.inference.cscs.ch/v1`. The provider layer is an interface with `list_models`, `complete` and `health`, implemented by CSCS, a Hugging Face router adapter and a configurable local endpoint. Every call writes a provider run recording provider, model, mode, latency, token usage, error class and validation errors.

The comparison step pairs only cross-document claims whose normalised predicate, unit, entity and effective date align, deduplicates pairs that describe the same difference, and compares bounded pairs with Apertus. The deterministic rule extractor runs alongside the model as a baseline, and its claims are dropped only when a validated model claim already covers the same passage with the same normalised predicate and value.

Dashboard and evidence view are React; the architecture diagram was drawn with diagram-design; the two-minute demonstration was authored with Videowright with ElevenLabs narration.

## Challenges we ran into

**Free-text predicates hid a real conflict.** The first end-to-end run found the documents consistent. Apertus described the same concept as "Payment term" in one document and "Settlement period" in the other, so the pairing filter never put the 30-day and 60-day claims in the same comparison. Fixed by normalising predicates, units, values and entities into a controlled vocabulary that keeps the raw wording for display, and by deduplicating candidates so one conflict is reported once rather than once per paraphrase.

**Clause numbers were being read as amounts.** "Clause 4.1" and "Policy 6.2" produced claims with predicate `amount` and values `4.1` and `6.2`, which then compared against each other and generated pure noise. Fixed by requiring a currency or a two-decimal amount for a monetary claim, and by reclassifying any value that appears next to a clause keyword as `clause_reference` so it can never pair as an amount.

**Citations resolved against the wrong document.** With more than one document, canonical text was being joined per passage across the whole corpus while offsets are per document, so a span from the second document was sliced out of the first document's text. This was caught by a test that asserts every produced citation equals its own document's canonical slice. Fixed by resolving each span against its own document's canonical text. Every displayed citation in the delivered run now resolves to an exact slice; the count of mismatches is zero.

**The published video tool could not render.** videowright 0.1.1 ships `dist/` and `src/cli/entry/` but no `src/index.js`, while its own render entry imports `../../index.js`, so Vite import analysis failed and the render timed out waiting for the page. Fixed with a small local patch script that recreates the missing re-export.

**The requested voice was not available on the free tier.** The brief asked for a British young female voice. Those voices are ElevenLabs library voices and the free tier refuses library voices through the API (HTTP 402), and voice design is paid-plan only (HTTP 403). Rather than add spend that was not authorised, we used the closest usable premade voice — British and female — and recorded the deviation next to the audio instead of quietly ignoring it.

## Accomplishments that we're proud of

Real inference, not a mock. The delivered demonstration run used `swiss-ai/Apertus-v1.5-70B` on CSCS for 11 calls with zero failures, 13,892 tokens and 68.9 s of provider latency, and produced 27 claims and 8 compared pairs across four synthetic documents. The whole flow was then re-run end to end inside a freshly built container, with the credential injected only at run time.

**Every displayed citation resolves to an exact slice of canonical text** — checked mechanically, zero mismatches, and the check is part of the test suite rather than a claim in a document.

Nothing silently degrades. The 70B model is never replaced by an 8B model; the backup provider cannot be reached without two explicit flags; a failed run is marked `failed` or `partial` with its failure list visible, so an empty finding list never masquerades as "no inconsistencies". 234 tests pass, covering offset resolution, fabricated spans, hostile filenames, encrypted and scanned PDFs, truncated model JSON, provider 401/402/429/503 handling, prompt injection and credential redaction. Two release checks run the same way: `make no-footer` measures the source, the built bundle, every served route and every page of the report PDF, and `make audit` refuses to let a credential value, a key-shaped string or a `.env` file reach the publishable tree or the submission archive.

And we measured the result honestly: 0.36 accuracy on a 25-case frozen corpus, with 44 % abstention. That number is in the README and in the evaluation report, not hidden.

## What we learned

**Retrieval, not reasoning, was the bottleneck.** Abstention, not a wrong answer, dominated the evaluation result: 11 of 25 cases were never compared because the candidate filter did not consider the pair alignable. Only 14 cases ever reached the model, and it was right on 9 of those. The model was rarely the thing that failed; the pairing step was, together with exception context we never showed it.

**A test found the most serious bug.** The cross-document citation defect would have produced quotes from the wrong document that still looked plausible in the interface. It was caught by an assertion, not by reading the code, and it is the reason the citation check is now a required test rather than a manual inspection.

**Constraints made the design better.** Not being allowed to silently downgrade from 70B, and not being allowed to let the model author a quote, forced the evidence model to be explicit — and made "the call failed" a first-class outcome instead of something papered over by a fallback.

**Honest scoring is uncomfortable and worth it.** Writing 0.36 next to a project we spent the day on is less pleasant than writing the demo-run numbers only. It is also the only version of the result that tells a reader whether to trust the tool.

## What's next for Sovra Verify - Don't Just Answer. Prove It.

The next work is the bottleneck the evaluation identified, not new features: improve candidate coverage so an alignable pair is not missed, and surface "considered and not reported" as a visible state so abstention stops looking like failure. After that, the exception and date-change false positives need document-level context — the clause that states an exception usually lives in the same document as the term it modifies, and same-document claims are currently never paired.

Beyond that: an authorised, deidentified historical procurement corpus reviewed by a consenting domain expert, measuring false positives and omissions against that reviewer's judgement rather than against our own labels; DOCX and OCR support, which needs a licensing review first; and a tested on-premise or air-gapped Apertus deployment, which is currently an untested adapter and is not claimed as working. No customer, ROI, legal conclusion or production deployment is claimed anywhere in this project.
