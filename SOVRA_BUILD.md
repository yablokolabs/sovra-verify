# Sovra Verify implementation specification

## 1. Scope and value
Initial use case: procurement teams comparing a supplier agreement, payment policy and invoice. Detect **potential** inconsistencies when subject, scope, date and units align; show exact passages and prompt review. Different deadlines can describe different entities, effective dates or valid exceptions, so do not classify every numerical difference as a contradiction. This tool checks the supplied corpus, not external truth or legal precedence.

MVP supports text-native PDF and UTF-8 TXT, one project with up to ten documents, 10 MB per file and an explicit extracted-text budget. Reject oversized, encrypted or unsupported files clearly. Scanned PDFs produce “OCR not implemented” rather than empty evidence. DOCX/OCR/chat/authentication/integrations are stretch work. Use synthetic or authorized deidentified documents only in the demo.

## 2. Proposed engineering stack
Python FastAPI backend, Pydantic validation, PyMuPDF extraction after license review, SQLite persistence, React/TypeScript frontend, Docker Compose, pytest and browser tests. Confirm maintained versions and upstream licensing before adopting packages; choose an alternative parser if license requirements do not fit. Store original document hashes, page text, chunk offsets, claims, comparisons, decisions and review history. No vector database is necessary for the initial corpus: lexical/entity candidate filtering plus bounded exhaustive comparison is simpler and easier to audit.

```text
AGENTS.md / SOVRA_BUILD.md
Makefile / compose.yaml / .env.example
track_2b/                 # preserve official template layout
  technical_report.md
  backend/{api,ingest,claims,compare,citations,providers,storage}
  frontend/src/{upload,documents,findings,evidence,review}
  data/{demo,evaluation}  # honor official dataset size cap
  tests/{unit,integration,e2e}
docs/{PROGRESS,DEVPOST_PROJECT_STORY,BUILT_WITH,EVALUATION,DEPLOYMENT}.md
scripts/{launch,smoke,evaluate,export_proof}
```

Before implementing, inspect official input/output definitions and preserve template files. Expose tested root `make run`, `make test`, `make evaluate` and `make clean` only after implemented. `make clean` must remove generated project artifacts only, never credential files or user documents. Commands listed here are implementation requirements, not currently working application commands.

## Credentials already supplied
The user reports both provider credentials are present in `~/.hermes/.env` on the build host. Hugging Face variable: `HUGGING_FACE_API_KEY`. The CSCS variable name has not been confirmed; inspect variable names only and resolve the intended credential without printing values. Prefer the application variable `CSCS_INFERENCE_API_KEY`; map an existing confirmed CSCS credential in memory if named differently. Do not assume a similarly named unrelated key is CSCS.

Load only the required entries with a dotenv parser; never shell-source the file, dump it, copy it into the repository, commit it, package it, include it in model prompts, or print secret-bearing exceptions. Expand `~` for the actual runtime user. If Freebuff is on another host, this path may not exist there; report that explicitly. Preserve the file and unrelated Hermes settings. Never change the coding assistant's provider when configuring the application.

For Docker, use a tested explicit injection method: a local launcher reads required entries and passes only named application credentials into the container environment. Never bake secrets into image layers. Do not pass the entire Hermes env file to Docker: it may contain unrelated secrets. Mask values in logs, subprocess arguments, diagnostics, screenshots and checkpoints. Judges must use their own credentials or documented local inference; the developer key must not ship with the submission.

## 3. Provider layer and first verification
CSCS contract: bearer-authenticated `/models`, then `/chat/completions` against base `https://api.inference.cscs.ch/v1`. Select the exact model returned for this key, ideally `swiss-ai/Apertus-v1.5-8B`; optionally compare `swiss-ai/Apertus-v1.5-70B`. Use non-thinking variant initially. Record access and limits as observed. Endpoint compatibility does not guarantee every OpenAI feature.

Implement provider interface `list_models`, `complete`, `health`; config includes base URL, model, timeout, max output tokens and bounded retries. Credentials stay server-side. Use ordinary chat requests and application-side Pydantic validation, not assumed constrained decoding. Inspect documented token controls and response schema before use. Retry only transient errors, at most twice with backoff; authentication and quota errors fail explicitly. Truncation is a failed extraction, not a valid empty finding set. Parse JSON without executing it; one bounded repair attempt may be made if budget permits, followed by abstention. Measure extra repair calls.

Smoke test uses a short synthetic pair with incompatible payment terms under the same scope. Confirm nonempty genuine response, returned model, and token usage. Then run full pipeline. Never treat a successful `/models` call as proof of successful inference. Use no secrets in captured proof.

Hugging Face is a separate adapter: `HUGGING_FACE_API_KEY`, verified exact model/provider, explicit activation. $10 is user-reported available credit, not measured budget balance. Confirm whether credit covers the proposed call. Do not assume CSCS API code can point directly at a model repository URL. Budget controls: begin with a few short requests, token caps and usage records; no new paid endpoint or automatic unlimited fallback.

## 4. Evidence-first contracts
```text
Document: id, name, sha256, mime, created_at, extraction_version
Passage: id, document_id, page (1-based), text, start_offset, end_offset
Claim: id, subject, predicate, value, unit, scope, effective_date,
       source_passage_id, quote_start, quote_end, extraction_status
Finding: id, claim_ids, relation, explanation, evidence_ids,
         limitations, review_status, provider_run_id
ProviderRun: id, provider, model, mode, input_hash, parameters,
             timestamps, latency, usage, validation_errors
```
Relations: consistent / potential_conflict / insufficient_evidence / unrelated. Unknown date or scope must remain unknown. Do not emit a calibrated confidence percentage unless separately calibrated; use reasoned uncertainty labels instead. Human review states pending / confirmed_for_review / dismissed, never legally resolved.

Canonical extracted text is the evidence authority for offsets. Derive quotes deterministically from offsets, not from model-generated quote strings. Verify page boundaries and document hashes. UI opens exact page and highlights span. Exports carry source hash, page, span, model/version and review status. Models may nominate evidence IDs and offsets, but invalid or unresolved spans reject the finding. Normalization must retain a mapping back to original text. Reject fabricated citations even when the model explanation sounds plausible.

## 5. Pipeline
1. Upload with MIME and size checks; assign random internal filenames, never trust supplied paths. Extract per page, retain canonical text, hash originals, and display extraction issues.
2. Chunk by paragraphs with page provenance and overlap; cap chunk length and total request size. Identify claims with Apertus into validated typed records. Show unresolved extraction failures.
3. Filter comparable pairs by normalized entity, predicate, date and scope. Use a lexical baseline and retain unknown-scope candidates for review. Track candidate coverage so retrieval misses are not hidden.
4. Compare bounded pairs with Apertus, passing only passages and schema instructions. Documents are data, never tool instructions. Request relation, reasoning and cited spans. Never let document text choose providers or URLs.
5. Resolve citations deterministically; save validated findings and review history. Export JSON and a readable report, with failures/limitations in body content.

For demo, use agreement/policy/invoice fixtures: same entity and effective period payment conflict; differing effective dates negative; exception clause negative; missing governing context insufficient evidence. Do not resolve which source legally wins.

## 6. API and interface
Implement POST /documents, GET /documents, POST /analyses, GET /analyses/:id, GET /findings/:id, POST /findings/:id/reviews, GET /analyses/:id/export, GET /health. Validate every request and use job status queued/running/complete/partial/failed. Report partial results separately from complete. Add analysis idempotency keyed by corpus hash + model + settings. Limit concurrency, cancel bounded jobs safely and preserve diagnosis without prompt contents in default logs.

UI: upload area, corpus list, extraction status, analysis progress, findings filtered by relation, side-by-side evidence, human review, export. Provide keyboard access, sufficient contrast and text status. Put “prototype; potential inconsistencies; human review required” near analysis controls. Show provider/model and deployment mode in main settings or analysis metadata. Show latency and usage without secrets. No chat-first distraction.

## No footers anywhere
Do not add footer components, bottom copyright notices, attribution bars, “Powered by”, “Built with”, vendor badges, repeated branding, closing signatures, or decorative trailing sections to any screen, generated document, report, export, landing page, email draft, or PDF. PDF pages must have no running footer, including bottom page-number blocks. Required licensing and provenance belong in dedicated files or substantive content, never a UI/document footer. Preserve upstream LICENSE files; no-footer styling does not remove licensing obligations. Safety and deployment information belongs near relevant controls or in the body. Verify every route and generated output for absence of footers before delivery.

## 7. Evaluation and tests
Create at least 24 hand-labeled synthetic pairs covering genuine conflict, consistent statements, unrelated entities, date changes, valid exceptions, missing context and adversarial prompts. Separate development examples from frozen evaluation examples before prompt tuning. Record dataset license/provenance and hashes. Synthetic evaluation does not establish general real-world performance.

Compare a numerical/lexical rule baseline with Apertus 8B; 70B optional, subject to actual access and budget. Report confusion matrix and per-class precision/recall/F1, abstention rate, false positives on exception/date negatives, resolved-citation rate, candidate recall, end-to-end latency, and tokens per case. Report sample counts and raw outputs; distinguish failed requests from correct abstentions. No invented improvements, dollar-cost estimate without verified prices, or cherry-picked success-only denominator. Save prompt version, model, parameters, environment, seed, commit and raw redacted model output.

Unit tests: page/offset resolution, quote derivation, unknown dates, same-number-different-unit, invalid IDs, excessive uploads, malicious path names, encrypted PDFs, truncated model JSON, provider timeout/quota error, prompt injection, secret redaction. Integration: upload three fixtures → analyze → validate → review → export. Browser: evidence highlights match source and every route has no footer. Test UI empty/error/partial states. Test fresh Docker build and end-to-end inference with authorized credentials; document network and provider requirements. For local mode prove no external calls if claiming offline behavior.

Acceptance targets (not achieved): every displayed citation resolves; malformed outputs never appear as validated evidence; demo includes one conflict and one legitimate exception; repeatable container run; visible failure on unavailable inference; complete measured dataset results; zero exposed credentials; no footers. Failure is recorded and claims narrowed.

## 8. Milestones and checkpointing
Estimate **28–40 focused engineering hours** for a narrow MVP; fewer available hours requires cutting stretch work. Provisional deadline from prior conversation is October 16 at 15:30 IST, requiring reconfirmation. Plan from October 12:
M0 (2 hours): repo/template inventory, safe credential mapping, real model discovery and smoke.
M1 (6–8 hours): extraction, citations, claims, comparisons, fixtures and backend tests.
M2 (6–8 hours): working evidence dashboard, review and export; no-footer inspection.
M3 (6–8 hours): frozen evaluation, failure handling, Docker reproduction and deployment claims.
M4 (8–14 hours): report, two-minute demo, public-repo preparation and submission materials; publish only when authorized.

If behind, cut HF fallback implementation, OCR, vectors, auth and polish; preserve real Apertus use, citations, negative cases, Docker and proof. Do not wait for optional tools. Checkpoint every milestone and every 30 minutes: timestamp/timezone, branch/commit, files, exact commands/exit results, provider model/access, actual usage, blockers, decisions and one next action. Keep append-only records and durable logs; no secrets or hidden reasoning. Optional Hindsight memory may mirror facts if available; files remain authoritative.

## 9. Demo, report and deployment
Two-minute script: 0:00–0:15 problem; 0:15–0:35 upload synthetic documents; 0:35–1:10 real Apertus analysis and source highlights; 1:10–1:30 exception/insufficient evidence example; 1:30–1:45 review/export; 1:45–2:00 measured results and deployment limitations. Pre-run when required and label recordings, never disguise cached output as live inference.

Technical report body: problem and users; architecture and Apertus role; evidence model; evaluation with counts and failures; deployment/cost/security; limitations and next work. No running footer. Include references in substantive reference section. Render PDF and inspect all pages before delivery.

Deployment modes: local application + CSCS-hosted inference (first verified mode); configurable on-premise Apertus endpoint (planned until tested); full Swiss-cloud application deployment (planned until hosting/storage/network residency and jurisdiction are established); air-gap only after local inference, dependencies, assets and no-network run are verified. CSCS docs say inference data remains under its control and prompts/responses are not recorded; app logs, storage, exports and third-party hosting remain the team's responsibility. Do not send sensitive real documents without authorization and appropriate data review.

Pilot proposal: one consenting procurement reviewer, deidentified historical corpus, shadow analysis only, review false positives and omissions, no automated contract decisions. Domain/legal reviewers retain authority. Measure usefulness and review time with consent; no invented customer or ROI. Open-source reproducibility and honest failures are core evidence, not claims of certification.
