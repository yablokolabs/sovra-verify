# Paste into Freebuff — fresh Sovra Verify build

Create **Sovra Verify — Don't Just Answer. Prove It.**, a new Apertus-powered cross-document consistency auditor. The project has NOT been started. Do not pretend there is existing application progress. Read AGENTS.md and SOVRA_BUILD.md, inspect the destination repository, then implement and verify the product from M0 onward. Preserve this documentation and unrelated files.

The user now has a CSCS inference key and $10 Hugging Face credit. Primary application inference is CSCS, OpenAI-compatible base URL `https://api.inference.cscs.ch/v1`. This configures Sovra Verify, not Freebuff's coding model.

## Credentials already supplied
The user reports both provider credentials are present in `~/.hermes/.env` on the build host. Hugging Face variable: `HUGGING_FACE_API_KEY`. The CSCS variable name has not been confirmed; inspect variable names only and resolve the intended credential without printing values. Prefer the application variable `CSCS_INFERENCE_API_KEY`; map an existing confirmed CSCS credential in memory if named differently. Do not assume a similarly named unrelated key is CSCS.

Load only the required entries with a dotenv parser; never shell-source the file, dump it, copy it into the repository, commit it, package it, include it in model prompts, or print secret-bearing exceptions. Expand `~` for the actual runtime user. If Freebuff is on another host, this path may not exist there; report that explicitly. Preserve the file and unrelated Hermes settings. Never change the coding assistant's provider when configuring the application.

For Docker, use a tested explicit injection method: a local launcher reads required entries and passes only named application credentials into the container environment. Never bake secrets into image layers. Do not pass the entire Hermes env file to Docker: it may contain unrelated secrets. Mask values in logs, subprocess arguments, diagnostics, screenshots and checkpoints. Judges must use their own credentials or documented local inference; the developer key must not ship with the submission.

## No footers anywhere
Do not add footer components, bottom copyright notices, attribution bars, “Powered by”, “Built with”, vendor badges, repeated branding, closing signatures, or decorative trailing sections to any screen, generated document, report, export, landing page, email draft, or PDF. PDF pages must have no running footer, including bottom page-number blocks. Required licensing and provenance belong in dedicated files or substantive content, never a UI/document footer. Preserve upstream LICENSE files; no-footer styling does not remove licensing obligations. Safety and deployment information belongs near relevant controls or in the body. Verify every route and generated output for absence of footers before delivery.

## Execute in order
1. Inventory git state, runtimes, Docker availability, and official template requirements. Initialize the fresh project while preserving `track_2b/` upstream structure. Verify current package documentation before adopting APIs.
2. Resolve CSCS credential name safely. Query `/models` and select an accessible Apertus 1.5 model. Try 8B first with a small synthetic request. Record model, timestamp, status, latency and token usage without secrets. Do not assume JSON schema enforcement, Responses API, tool calls or embedding-model compatibility.
3. Implement upload → extraction → claim identification → scoped comparison → validated citations → review dashboard → export. Deliver the offline UI and fixture parsing independently if inference access fails; label such behavior and do not claim successful Apertus reasoning.
4. Build meaningful evaluation, deterministic citation checks, hostile-input tests, Docker deployment, and reproducible scripts. Verify a fresh-container end-to-end run. Maintain docs/PROGRESS.md, project story and Built With during development.
5. Prepare measured evidence, technical report, two-minute demonstration and submission checklist. Finish all authorized local implementation rather than stopping at a plan. Report blockers precisely.

## Hugging Face fallback
Use `HUGGING_FACE_API_KEY` from the same credential file only after checking official current inference documentation, an actual provider serving the required Apertus model, account entitlement and credit applicability. $10 credit does not prove Apertus is available through the router. Model downloads alone are not inference credits. Do not automatically deploy a paid dedicated endpoint or silently switch providers; obtain permission for new spending. Fail visibly and keep CSCS/local adapters configurable.

## Session and claims
Checkpoint every 30 minutes and before interruption. Hindsight memory bank `sovra-verify` may supplement file checkpoints only if available; do not assume tools exist. Resume from verified file state. Never claim fully offline/air-gapped operation for a CSCS call. No legal/compliance conclusions, automated policy changes, or production document actions.
