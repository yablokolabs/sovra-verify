# Sovra Verify durable progress

Append-only checkpoint log. Every entry records what was actually run, what it returned, and the one
next action. No credential value appears anywhere in this file.

## Current state — October 12, 2026, Asia/Kolkata

M0 through M4 are implemented and verified on the build host. The application runs, the tests pass,
and real Apertus 1.5 70B inference on CSCS has been exercised end to end with zero non-resolving
citations, both as a host process and inside a fresh container. The demonstration video, diagram,
evaluation harness, technical report PDF, evidence bundle and submission archive exist and have
been inspected.

A public repository was authorized and published: **https://github.com/yablokolabs/sovra-verify**.
Nothing has been submitted to the hackathon portal, and no further external action has been taken.

## Milestones

- [x] M0: scaffold, runtime inventory, safe credential mapping, real model discovery and smoke.
- [x] M1: extraction, validated evidence, Apertus claim identification and comparison, fixtures, tests.
- [x] M2: dashboard, review and export, no-footer inspection.
- [x] M3: evaluation harness, Docker packaging, provider verification, demonstration video.
- [x] M4: technical report PDF, evidence bundle, provider re-verification, submission archive.
- [x] M5: evaluation decomposition, comparison context, and an honest negative result on the fix.
- [x] Publication: public repository at `https://github.com/yablokolabs/sovra-verify`, authorized by the
owner and verified public with 143 files and no credential or work file among them.
- [ ] Submission to the hackathon portal: **not done.**

## Provider status

| Provider | Status |
|---|---|
| CSCS | **Verified.** `GET /models` HTTP 200 with 11 models; `swiss-ai/Apertus-v1.5-70B` answered a real completion in 0.51 s. Primary provider. |
| Hugging Face | **Verified reachable, but not usable for the default model.** The router exposes only `swiss-ai/Apertus-8B-Instruct-2509`; the 1.5 70B mapping reports `status: "error"`. Backup only, off by default. |
| Local / on-premise Apertus | Adapter implemented, **not tested** against real hardware. No claim made. |
| Air-gapped operation | **Not claimed.** CSCS-hosted inference is external-network inference. |

See `docs/PROVIDER_VERIFICATION.md` for the recorded responses.

---

## Checkpoint M0-1 — runtime inventory and credential resolution

```
Timestamp / checkpoint ID:   2026-10-12 13:05 IST / M0-1
Milestone / branch / commit: M0 / no repository yet (git not initialised) / n/a
Actual implemented behavior: none — inventory only
Command / exit code / result:
  python3 --version                      -> 3.12.3
  node --version                         -> v22.23.2   (npm 10.9.8)
  docker --version                       -> 29.8.1     (compose v5.5.1)
  make --version                         -> GNU Make 4.3
  ffmpeg -version                        -> 6.1.1
  sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' ~/.hermes/.env
                                         -> variable NAMES only; exit 0
Model / provider / usage: none
Evidence and dataset versions: none
Blocker: none
No-footer inspection: not yet applicable
Story/tag claim changes: none
One exact next action: create the virtual environment and install backend dependencies.
```

Credential names observed in `~/.hermes/.env` (names only, never values):
`CSCS_INFERENCE_API_KEY`, `HUGGING_FACE_API_KEY`, `ELEVENLABS_API_KEY`, plus unrelated entries.
`CSCS_INFERENCE_API_KEY` matched the intended application variable, so no aliasing was required and
no similarly named unrelated key was assumed to be CSCS.

## Checkpoint M0-2 — real provider discovery and inference smoke

```
Timestamp / checkpoint ID:   2026-10-12 13:12 IST / M0-2
Milestone / branch / commit: M0 / no repository / n/a
Actual implemented behavior: provider discovery and one real completion, no application yet
Command / exit code / result:
  httpx GET  https://api.inference.cscs.ch/v1/models   -> 200, 11 model ids
  httpx POST https://api.inference.cscs.ch/v1/chat/completions
        model=swiss-ai/Apertus-v1.5-70B                -> 200 in 0.51 s
        content="conflict"; usage prompt=62 completion=3 total=65          EXIT 0
  httpx GET  https://router.huggingface.co/v1/models   -> 200, 126 models,
        Apertus entries: only swiss-ai/Apertus-8B-Instruct-2509
  httpx GET  huggingface.co/api/models/swiss-ai/Apertus-v1.5-70B
        -> inferenceProviderMapping featherless-ai status "error" (not servable)
  httpx POST router chat/completions (8B-2509)         -> 200 in 2.23 s, usage 67/2/69
Model / provider / mode / usage / validation failures:
  cscs / swiss-ai/Apertus-v1.5-70B / smoke / 65 tokens / none
Blocker: none
No-footer inspection: not yet applicable
Story/tag claim changes: none
One exact next action: scaffold the application and implement the provider layer with the
70B default and the 8B policy guard.
```

## Checkpoint M1-1 — backend implemented, first real end-to-end run

```
Timestamp / checkpoint ID:   2026-10-12 13:29 IST / M1-1
Milestone / branch / commit: M1 / no repository / n/a
Actual implemented behavior: ingest, citations, claims, comparison, storage, API
Command / exit code / result:
  python -m compileall track_2b/backend/sovra                 -> OK
  inline pipeline run over 2 synthetic documents:
      status=complete claims=15 pairs=1                       EXIT 0
      finding: consistent, 0 resolved citations
Model / provider / mode / usage / validation failures:
  cscs / swiss-ai/Apertus-v1.5-70B / claims+compare / 13 calls recorded / 1 unresolved claim
Blocker: location = candidate pairing → cause = claims were paired on raw free-text predicates
  ("Payment term" vs "Settlement period"), so the 30-day-vs-60-day pair never became a candidate
  → fix = add a controlled-vocabulary normaliser and deduplicate candidates by normalised key.
No-footer inspection: not yet applicable
Story/tag claim changes: none
One exact next action: implement predicate/unit/value normalisation and re-run.
```

## Checkpoint M1-2 — normalisation, clause-number guard, evidence integrity

```
Timestamp / checkpoint ID:   2026-10-12 13:36 IST / M1-2
Milestone / branch / commit: M1 / no repository / n/a
Actual implemented behavior: normalised pairing, clause-reference reclassification, deduplication
Command / exit code / result:
  pytest track_2b/tests -q                                    -> 221 passed, 2 skipped
  inline pipeline run over the 4-document demo corpus:
      status=complete claims=25 pairs=10                      EXIT 0
      citation integrity check: non-exact spans = 0
      usage: 13 calls, 0 failed, 15,650 tokens, 71,543 ms
Model / provider / mode / usage / validation failures:
  cscs / swiss-ai/Apertus-v1.5-70B / claims+compare / 13 ok / none
Blocker: location = citations.resolve_all over a multi-document corpus
  → cause = canonical text was joined per passage across all documents while offsets are per
    document, so a span from the second document was sliced out of the first document's text
  → fix = resolve every span against the canonical text of that passage's own document. This was
    found by the test worker, reproduced with an assertion that every citation equals its
    document's canonical slice, and fixed before any result was reported.
No-footer inspection: source scanned for footer markers; none found
Story/tag claim changes: none
One exact next action: build the React dashboard and export surfaces.
```

## Checkpoint M2-1 — frontend, diagram, video toolchain

```
Timestamp / checkpoint ID:   2026-10-12 13:52 IST / M2-1
Milestone / branch / commit: M2-M3 / no repository yet / n/a
Actual implemented behavior: React + TypeScript dashboard, Markdown/JSON/ZIP export, architecture
  diagram, videowright project with narration audio
Command / exit code / result:
  npm run build (track_2b/frontend)   -> tsc clean, vite build 172.81 kB js / 7.63 kB css   EXIT 0
  python3 .../export_svg.py docs/diagrams/architecture.html  -> architecture.svg            EXIT 0
  rsvg-convert -z 2                  -> architecture.png, 2000x1040, 2849 distinct colours   EXIT 0
  npx tsc --noEmit (videos)          -> clean after adding env.d.ts                          EXIT 0
  ElevenLabs TTS (eleven_multilingual_v2, Alice) -> 200, audio 117.4 s, 250 words           EXIT 0
Model / provider / mode / usage / validation failures:
  elevenlabs / eleven_multilingual_v2 / voiceover / 1,522 billed characters / none
Blocker 1: location = npx videowright render → cause = the published videowright 0.1.1 tarball
  ships dist/ and src/cli/entry/ but no src/index.js, while src/cli/entry/render_entry.ts imports
  "../../index.js"; Vite import analysis fails and the render page never signals readiness
  ("page.waitForFunction: Timeout 30000ms exceeded") → fix = videos/scripts/patch-videowright.sh
  recreates node_modules/videowright/src/index.js re-exporting ../dist/index.js.
Blocker 2: location = ElevenLabs voice selection → cause = the requested British young female
  voices (Amelia, Annie) are library voices and the free tier refuses library voices through the
  API (HTTP 402 paid_plan_required); voice design is paid-plan only (HTTP 403 feature_not_available)
  → fix = use the closest usable premade voice (Alice, British, female) and record the deviation in
  audio_meta.json and the README rather than adding spend, which was not authorised.
Blocker 3: location = first narration take → cause = 304 words ran 138.07 s, over the official
  two-minute limit → fix = rewrite the script to 250 words and regenerate; measured 117.4 s.
No-footer inspection: frontend source and diagram scanned; no markers
Story/tag claim changes: none
One exact next action: run the frozen evaluation and the Docker build.
```

## Checkpoint M3-2 — report PDF, and the no-footer check extended to rendered pages

```
Timestamp / checkpoint ID:   2026-10-12 14:20 IST / M3-2
Milestone / branch / commit: M3 / no repository / n/a
Actual implemented behavior: scripts/render_pdf.cjs and scripts/build_report_pdf.py render
  track_2b/technical_report.md to PDF and then measure it; scripts/pdf_text.py is the shared page
  reader; scripts/check_no_footer.py gained a page-geometry surface.
Command / exit code / result:
  python scripts/build_report_pdf.py
      -> track_2b/technical_report.pdf, 5 pages: 4 body pages + references
         body page limit is 6, so 4 is within budget
         every page measured; lowest text per page p1 59pt, p2 124pt, p3 101pt,
         p4 516pt, p5 508pt, so no fragment sits in the 45pt footer band
  python scripts/check_no_footer.py
      -> PASS: 68 static files, built frontend output, all 5 PDF pages, 4 static HTTP
         routes and 5 live routes with real ids; 0 markers
Model / provider / mode / usage: none (rendering only)
Blocker: location = the first version of the page check reported every page as failing
  → cause = PDF text matrices are page-relative, and the check treated the tm translation as an
    absolute page position → fix = add the text-matrix translation to the current transformation
    matrix before comparing against the footer band. The misreading was found because the reported
    lowest positions were impossible for a page whose body starts at the top.
No-footer inspection: PASS over source, built assets, 5 PDF pages, 4 static and 5 live HTTP routes
Story/tag claim changes: none
One exact next action: rebuild the container and run the whole flow inside it.
```

## Checkpoint M3-3 — fresh-container end-to-end run

```
Timestamp / checkpoint ID:   2026-10-12 16:35 IST / M3-3
Milestone / branch / commit: M3 / no repository / n/a
Actual implemented behavior: scripts/e2e_container.sh starts a fresh container through
  scripts/launch.sh and hands its URL to the same scripts/run_e2e.sh the host run uses
Command / exit code / result:
  make docker-build                     -> EXIT 0, image sovra-verify:local,
                                           manifest list sha256:a270686a50aa666c5dfe2baf5136b2be9a1747e5bb2c529495a563239c4e15c6
  bash scripts/e2e_container.sh         -> EXIT 0
      image config carries no credential variable                      (fail-fast check)
      0 file(s) under /app contain the credential value                 (probe run inside the container)
      analysis 6d271966b36e4587 complete over the 4-document demo corpus
      findings: consistent 1, potential_conflict 3, insufficient_evidence 0, unrelated 0
      claims 24 (20 resolved, 4 unresolved); 2 limitations recorded
      a human review decision was recorded and read back
      exports: analysis.json 28,502 B, bundle.zip 19,489 B, report.md 5,427 B
      no-footer inspection: 5 live routes fetched with real ids; PASS; all three exports clean
Model / provider / mode / usage:
  cscs / swiss-ai/Apertus-v1.5-70B / claims+compare inside the container / 0 failed calls
Blocker: location = compose.yaml interpolates its required variable on every sub-command
  → cause = `docker compose ps` from the verification shell would either fail or force the value
    onto a command line → fix = start once through the launcher, then use plain `docker` against the
    container id for every later step, and run the layer probe inside the container against its own
    environment variable so no value crosses a boundary.
No-footer inspection: PASS over the container's served routes and all generated exports
Story/tag claim changes: Docker packaging moved from planned to observed
One exact next action: re-verify both providers and fix the drift the verification exposed.
```

## Checkpoint M4-1 — both provider credentials re-verified with real inference

```
Timestamp / checkpoint ID:   2026-10-12 16:48 IST / M4-1
Milestone / branch / commit: M4 / no repository / n/a
Actual implemented behavior: scripts/verify_providers.py corrected; provider record refreshed
Command / exit code / result:
  make verify-providers                 -> EXIT 0, overall ok
      cscs:        GET /models 200 in 324 ms, 11 models, configured model served
                   swiss-ai/Apertus-v1.5-70B answered a real completion in 441 ms
                   smoke pair returned potential_conflict with 2 resolved citations
      huggingface: GET /models 200 in 86 ms, 124 models, credential resolved
                   swiss-ai/Apertus-8B-Instruct-2509 answered a real completion in 1,218 ms
                   the 1.5 70B default is NOT servable on the router
  wrote track_2b/data/evaluation/PROVIDER_VERIFICATION.json
Model / provider / mode / usage:
  cscs / swiss-ai/Apertus-v1.5-70B / chat 46 tokens, smoke pair 582 tokens / no failures
  huggingface / swiss-ai/Apertus-8B-Instruct-2509 / chat 42 tokens / backup, still disabled by default
Blocker: location = scripts/verify_providers.py step_pair → cause = it still called
  resolve_all(canonical_text=...), an argument removed when citation resolution was fixed in M1-2 to
  resolve each span against its own document's text → fix = pass canonical_by_document, as the
  application does. No test covered this script, so the drift survived until the script was run.
No-footer inspection: not applicable to this checkpoint
Story/tag claim changes: none; the Hugging Face row keeps its "reachable but not the default model" wording
One exact next action: build the evidence bundle, then audit the tree and the archive for secrets.
```

## Checkpoint M4-2 — evidence bundle, secrets audit and submission archive

```
Timestamp / checkpoint ID:   2026-10-12 17:05 IST / M4-2
Milestone / branch / commit: M4 / no repository / n/a
Actual implemented behavior: scripts/export_proof.py, new scripts/audit_secrets.py and new
  scripts/package_submission.py; make audit added
Command / exit code / result:
  python scripts/export_proof.py --run-demo
      -> analysis 429df808d24f4433 complete; 11 calls, 0 failed; 16 citation spans,
         every span re-derived from canonical text; credential audit clean
         wrote track_2b/data/evaluation/PROOF.json and PROOF.md
      --run-demo was used because the host store held no analysis; cost: 11 calls on the
         default model, the same shape as the run already recorded in M1-2
  make audit                            -> EXIT 0, 143 publishable files (11,825 KiB),
                                           no credential value, key-shaped string or forbidden name
  python scripts/package_submission.py  -> EXIT 0, dist/sovra-verify-submission.zip,
                                           143 members, 10,412 KiB, members match the publishable set
                                           exactly, members re-audited after writing
      contains: Makefile, compose.yaml, Dockerfile, the 5-page report PDF,
                docs/demo/sovra-verify-demo.mp4, the measured evidence under
                track_2b/data/evaluation, and .env.example as an empty template
      contains no: virtualenv, node_modules, work directory, dotenv file or credential
  make test                             -> EXIT 0, 234 passed, 1 skipped
Model / provider / mode / usage:
  cscs / swiss-ai/Apertus-v1.5-70B / claims+compare / 11 calls, 0 failed
Blocker 1: location = the evidence bundle's own tree audit
  → cause = its shape rule matched `sk-abcdefghijklmnop`, a fabricated test literal used to prove
    that masking shortens a value, so it reported three false positives and its own run failed
  → fix = added an entropy guard: a candidate shorter than 20 characters, or carrying no digits,
    is not a live credential. Tests now pin both directions.
Blocker 2: location = the new audit found the new test file itself
  → cause = the test must contain a key-shaped string to prove detection → fix = assemble the
    literal from fragments, the same technique scripts/check_no_footer.py already uses.
Blocker 3: location = scripts/audit_secrets.py is_excluded → cause = "originals" was excluded as a
  directory name anywhere in the path, which dropped the voice-over project's own narration sources
  (videos/videos/sovra_demo/audio/originals/...) from the audit and therefore from the archive, even
  though the README cites them as provenance. The top-level rule exists to keep the uploaded-document
  store out of the published tree, not to hide nested project material → fix = exclude those names
  only at the top level. The publishable set grew from 137 to 143 files, and the archive with it.
No-footer inspection: not applicable to this checkpoint; last full PASS at M3-3
Story/tag claim changes: none yet; the numbers above replace the earlier provisional ones
One exact next action: ask for publication authorization before any repository is created.
```

## Checkpoint M4-3 — public repository published

```
Timestamp / checkpoint ID:   2026-10-12 17:40 IST / M4-3
Milestone / branch / commit: M4 / main / c604e4842e4f6376a8ae3c764cb8d3d9b6a69b51
Actual implemented behavior: the audited tree was committed with no credential, then published
after explicit authorization from the owner
Command / exit code / result:
  git init -b main; git add -A
      staged 143 files; compared against the audit's publishable set -> identical,
      no file staged that the audit excludes and none absent; .env.example carries variable
      names only
  git commit
      message contains no footer, trailer, signature or attribution of any kind
  gh repo create yablokolabs/sovra-verify --public --source=. --remote=origin --push
      -> EXIT 0, https://github.com/yablokolabs/sovra-verify, main tracking origin/main
  gh api repos/yablokolabs/sovra-verify/git/trees/main?recursive=1
      -> 143 blobs, matching the publishable set exactly
      -> no .env, virtualenv, node_modules, work directory, sqlite file, key file or log
      -> technical_report.pdf, PROOF.json, docs/demo/sovra-verify-demo.mp4, Makefile,
         track_2b/Dockerfile and compose.yaml all present
Model / provider / mode / usage: none (packaging and publication only)
Blocker: none
No-footer inspection: PASS immediately before the commit (source, built output, every served route,
  all 5 report PDF pages) and PASS over every generated export
Story/tag claim changes: none
One exact next action: submit to the hackathon portal when the owner says so; nothing is submitted yet.
```

## Checkpoint M5-1 — accuracy investigated: two changes made, measured, and reported as no gain

```
Timestamp / checkpoint ID:   2026-10-12 18:55 IST / M5-1
Milestone / branch / commit: M5 / main / pending
Actual implemented behavior:
  (a) a comparison now receives the other extracted statements of each claim's own document
      (compare.Comparer, MAX_CONTEXT_PASSAGES_PER_SIDE=4), and the claim prompt asks for every
      distinct statement in a passage, including a stated exception or superseding date
      (PROMPT_VERSION -> sovra-prompts-4)
  (b) every compared pair is counted by the relation it was given: candidate_coverage gains
      outcomes, comparisons_without_finding and inconsistencies_reported; the interface states that
      outcome, and a run that reports nothing says so explicitly
  (c) evaluate.py reports accuracy_on_compared_cases, the negative-case clean rate and a diagnostics
      block of case ids, without redefining accuracy
Command / exit code / result:
  pytest track_2b/tests -q                 -> EXIT 0, 248 passed, 1 skipped
      covers the comparison context at the request level, the per-relation coverage counts, the HTTP
      contract that the coverage block agrees with the findings, and the evaluation metrics
  npx tsc --noEmit; npm run build          -> EXIT 0, 174.03 kB js / 7.63 kB css
  make evaluate (real inference)           -> EXIT 0
      cases 25, correct 9, accuracy 0.36          <- UNCHANGED from sovra-prompts-3
      compared cases 14 of 25; accuracy on compared cases 0.6429
      negative cases 10; no inconsistency reported on 8; clean rate 0.80
      false alarms 2 (eval-020, eval-022); missed inconsistency 1 (eval-002)
      provider calls 41 (0 failed), 158.3 s, 37,550 tokens, mean 1,502 per case
      diagnostics: never_compared 11, false_alarm 2, missed_inconsistency 1, silent_negative 8
  make report-pdf                          -> EXIT 0, 4 body pages (limit 6), 0 footer fragments
  npm run build (track_2b/frontend)        -> EXIT 0, 174.03 kB js; the new coverage sentences are
      present in the bundle the backend serves at /app (checked by searching the built asset)
Model / provider / mode / usage:
  cscs / swiss-ai/Apertus-v1.5-70B / claims+compare / 41 calls, 0 failed
Blocker: location = docs/EVALUATION.md, the attributed cause of the five false positives
  → cause = we had written that the exception clause never reached the model, inferred from a
    "same document" skip reason without checking which passage held the clause. The re-run produced
    the model's own cited spans: for eval-018 it quoted "as an exception to Policy 4.1" and still
    called the values incompatible, and for eval-022 it wrote that no exception or effective date was
    provided to reconcile the discrepancy and reported a conflict anyway → fix = the claim is
    corrected in EVALUATION.md, the technical report and the story, with those spans as the evidence.
    The measured result of the two changes is stated as no gain, not as an improvement.
No-footer inspection: PASS over source, built bundle, every served route, all 5 report PDF pages and
  every generated export
Story/tag claim changes: "What we learned" now carries the negative result; tags unchanged
One exact next action: commit and push the corrected claims and the measured negative result.
```

## Checkpoint M6-1 — the interface is verified on a live screen, not only in source

```
Timestamp / checkpoint ID:   2026-10-12 19:30 IST / M6-1
Milestone / branch / commit: M6 / main / pending
Actual implemented behavior:
  scripts/browser_check.py drives the running dashboard in lightpanda (a headless browser whose
  `serve` subcommand exposes the Chrome DevTools Protocol) with nothing injected and no request
  answered locally, then asserts on what the page renders: the interface finished loading its own
  data; the candidate-coverage notice exists and, when pairs were compared, states how they were
  judged; a completed run that reported nothing says so in words; the prototype warning sits next to
  the controls; and neither the rendered text nor the DOM that produced it carries a footer marker
  from scripts/check_no_footer.py's own list. Screenshots and a JSON record are written out.
  `make ui-check` is the no-inference form and `make ui-check-full` clicks "Select all" and "Analyse
  corpus with Apertus" and waits for a real run.
Command / exit code / result:
  make ui-check                      -> EXIT 0 (no inference): 4 documents offered, provider
      reachable, no run on screen so the coverage contract is reported as NOT EXERCISED rather than
      passed, no footer marker in 2,302 rendered characters or 6,514 DOM characters
  make ui-check-full (real inference) -> EXIT 0
      round trip 83.92 s; 56 provider calls, 132,521 tokens, 336.2 s accumulated latency, 0 failed
      run summary: complete, Apertus comparison, prompt sovra-prompts-4, 33 claims, 11 pairs
      coverage on screen: 11 compared pair(s) were judged: 10 potential conflict, 1 consistent
      footer scan: no marker in 13,362 rendered characters or 32,733 DOM characters
      screenshots: docs/demo/screenshots/01-corpus.png, 02-findings.png (both 1500x3000, different
      hashes, 0.0240 vs 0.0275 ink share, so the run is visibly the difference between them)
  repeat of that run                  -> EXIT 0, 0.51 s round trip; the API answers a repeat of the
      same document set from its own stored run, which is why the delivered
      track_2b/data/evaluation/UI_RENDER.json is a repeat and its usage summary is the run's own
  make test                          -> EXIT 0, 260 passed, 1 skipped (12 new tests in
      track_2b/tests/unit/test_browser_check.py cover the coverage contract's branches, the footer
      hit list and the JavaScript-literal escaping, without needing a browser)
  make no-footer                     -> EXIT 0; make audit -> EXIT 0, 150 publishable files
  make report-pdf                    -> EXIT 0, 4 body pages (limit 6), 0 footer fragments
Model / provider / mode / usage:
  cscs / swiss-ai/Apertus-v1.5-70B / claims+compare through the interface
  spend this session: three live interface runs — 42 calls / 99,395 tokens, 56 calls / 132,521 tokens,
  and one whose HTTP response the browser aborted before the fix below (28 calls / 66,274 tokens);
  0 failed calls in all three
Blocker: location = scripts/browser_check.py and the run it drives
  → cause = lightpanda's HTTP timeouts default to 15,000 ms for a transfer and 8,000 ms to connect.
    The analysis endpoint is synchronous and sends nothing for over a minute, so the browser aborted
    the POST, the page kept its empty state, and the check waited for a finish that had already
    happened server-side — a hang that looked like a slow model rather than a failed request.
  → fix = the browser is started with --http-timeout 900000 --http-connect-timeout 30000, the wait
    loop reports progress every 30 s, and a capture is bounded by its own timeout. Verified by the
    next run returning in 83.92 s and rendering the run. The page's getBoundingClientRect and
    scrollHeight answers 100000000 for every element, so the capture uses a fixed 1500x3000 viewport
    rather than measuring the document.
No-footer inspection: PASS over source, built bundle, every served route, all 5 report PDF pages,
  every generated export, and now the live DOM of the rendered dashboard
Story/tag claim changes: story gained the browser-verification paragraphs and the corrected test
  count (260); Built With gained one honest tag (lightpanda, 22 of 25) plus its role and evidence
One exact next action: commit and push the browser check, its tests, the screenshots and the docs.
```

## Checkpoint M6-2 — the delivered video is re-rendered: the mark paints and the narration is not clipped

```
Timestamp / checkpoint ID:   2026-10-12 20:20 IST / M6-2
Milestone / branch / commit: M6 / main / pending
Actual implemented behavior:
  (a) the demo video's opening scene imports its mark instead of pointing at a URL. The render and dev
      servers root themselves in the videowright package and reach this project through an alias, so
      `/brand/sovra-logo.png` resolved against the package and 404'd, leaving an empty box in a scene
      that otherwise looks finished. The asset moved from `videos/public/brand/` (a directory the
      server never served) to `videos/assets/brand/`, `segments/sovra-problem/index.ts` imports it,
      and `videos/env.d.ts` declares the module type. `videos/public/` no longer exists.
  (b) the audio overlay no longer stops short of the narration. The renderer uses a segment's LAST
      advance as that segment's whole duration, but the overlay ended every scene 0.2 s before the
      next narration section began, so the seven values summed to 116.60 s against 117.432 s of audio
      and ffmpeg's `-apad -shortest` truncated the closing words of the last sentence. Each span now
      runs to the next section's first word, and the last runs to the end of the file. This also
      removes up to 1.2 s of accumulated drift between picture and voice.
  (c) the dashboard's header mark: `track_2b/frontend/src/shared/Logo.tsx` builds the URL from Vite's
      base (`/app/`) instead of writing `/sovra-logo.png`, because the backend mounts the build at
      /app and a root-absolute URL asks the server for a file it does not serve. The browser check
      now asserts the URL the page resolved is served as an image, and `check_logo` has unit tests
      for the 404, the missing element and the wrong-content-type cases.
Command / exit code / result:
  npx tsc --noEmit (videos)                -> EXIT 0
  npx videowright render sovra_demo        -> EXIT 0, "timing source: audio_track",
      total frames 7048 (117.5 s)
  ffprobe docs/demo/sovra-verify-demo.mp4  -> duration 117.466667 s, 7048 frames, 1920x1080 @ 60 fps,
      aac audio 117.461 s, 7,201,695 bytes; the file this replaces was 116.633 s, i.e. 0.799 s of
      narration cut. Narration source file: 117.432 s.
  pixel check, frame at t=4.0 s        -> new: 3,062 navy and 1,592 teal pixels inside the mark box
      (crop 364x112 at 128,200), mean 215.6, stdev 58.6 | old delivered: 0 navy pixels, mean 233.7,
      stdev 24.7 — the box was empty and now carries the lockup's own colours
  audio tail, last 4 s mean volume      -> new -16.6 dB, source track.mp3 -16.6 dB (identical),
      old delivered -16.0 dB: the new cut carries the end of the narration, the old one did not
  scene-boundary arithmetic (60 fps)     -> measured from the rendered schedule and compared with
      section_starts.json: +0.007, +0.009, +0.010, +0.016, +0.020, +0.028 s after each narration
      section starts, never before, total 117.467 s covering 117.432 s of narration
  npm run build (frontend)               -> EXIT 0, 174.03 kB js, 7.63 kB css; the built bundle now
      contains src:"/app/sovra-logo.png" (the previous build asked for "/sovra-logo.png")
  make ui-check-full (live run)          -> EXIT 0, PASS
      header mark served: http://127.0.0.1:8098/app/sovra-logo.png -> 200 image/png, 71,892 bytes
      round trip 95.21 s; 14 provider calls, 32,004 tokens, 94.6 s accumulated latency, 0 failed
      run summary: complete, Apertus comparison, prompt sovra-prompts-4, 28 validated claims, 11 pairs
      coverage on screen: 11 compared pair(s) were judged: 10 potential conflict, 1 consistent
      footer scan: no marker in 10,964 rendered characters or 24,567 DOM characters
  Chromium decode check (ad hoc, Playwright from videos/node_modules)
      -> the header mark is present, complete, naturalWidth 1952, naturalHeight 600, rendered box
         44x44; drawn into a canvas it yields 99,456 navy pixels of 1,171,200 — the mark really paints
         in a browser that decodes images, which lightpanda's capture does not
  make test                             -> EXIT 0, 265 passed, 1 skipped (12 of them are
      track_2b/tests/unit/test_browser_check.py, which cover the mark assertion without a browser)
  make no-footer                        -> EXIT 0, PASS (incl. the live-DOM scan); make audit -> EXIT 0,
      154 publishable files
Model / provider / mode / usage:
  cscs / swiss-ai/Apertus-v1.5-70B / claims+compare through the interface
  spend: one live interface run, 14 calls / 32,004 tokens / 94.6 s, 0 failed. The check was expected to
  be answered from the app's stored run (the previous record shows a 0.51 s repeat) and was not, so the
  numbers above are a real run and the delivered UI_RENDER.json is that run's own record, not a repeat.
Blocker: location = videos/segments/sovra-problem/index.ts and videos/videos/sovra_demo/audio/tracks/v1/track.ts
  → cause 1 = a root-absolute asset URL is resolved by whichever server renders the page, and this
    projector's server is not rooted in the project; the path 404'd and the <img> stayed empty, with no
    error anywhere in the render log.
  → cause 2 = the timing overlay assumed a scene's duration was independent of its last advance; the
    renderer's `buildFrameSchedule` advances the clock by exactly that last value, so six scenes each
    ended 0.2 s early and the drift accumulated to 1.2 s while the picture ended 0.83 s before the audio.
  → fix = the mark is imported so the bundler serves the project's own file; the last advance of each
    overlay entry is that scene's full narration span. Both are verified against the rendered MP4
    (pixels and audio level) rather than against the source that produced it.
No-footer inspection: PASS over source, the built bundle, every served route, all report PDF pages, every
  generated export and the live DOM; the video was re-checked for a closing card or branding strip — the
  final scene still ends on the deployment limitation, and the mark still appears once, at the start
Story/tag claim changes: "Challenges" gained the two render defects and their causes, the test count reads
  265, and the README's interface section now quotes the delivered run and the mark assertion; tags unchanged
One exact next action: commit and push the video, the app fix, the refreshed evidence and these docs.
```

## Checkpoint M6-3 — the build prompt is removed from the repository

```
Timestamp / checkpoint ID:   2026-10-12 20:45 IST / M6-3
Milestone / branch / commit: M6 / main / pending
Actual implemented behavior: FREEBUFF_PROMPT.md is no longer part of the repository at the owner's
  request. The file's operating rules are not lost by this: AGENTS.md carries the same directives
  (credential handling, no footers anywhere, evidence and delivery rules) and stays. Three references
  had to move with it so the tree and the checks stay consistent:
    SOVRA_BUILD.md        the repository-layout block listed the prompt beside AGENTS.md and
                          SOVRA_BUILD.md; it now lists the two files that remain
    docs/KIT_MANIFEST.json  the digest record dropped the entry (and every remaining digest was
                          recomputed, because SOVRA_BUILD.md itself changed)
    scripts/check_no_footer.py  the doc allowlist dropped the entry, so the allowlist no longer names
                          a file that is not in the tree
Command / exit code / result:
  git rm FREEBUFF_PROMPT.md             -> removed from the index and the working tree
  grep -rn FREEBUFF_PROMPT              -> the only remaining mentions are in this record; no file,
      check, manifest or document in the tree refers to it any more
  digest check over docs/KIT_MANIFEST.json -> all 8 recorded hashes match the files on disk
  make test -> EXIT 0, 265 passed, 1 skipped
  make no-footer -> EXIT 0, PASS (the allowlist summary no longer names the removed file)
  make audit -> EXIT 0, 153 publishable files at that point (154 before the removal)
  scripts/package_submission.py -> EXIT 0, 153 members, re-opened and audited
Model / provider / mode / usage: none (repository surgery and documentation only; no inference)
Blocker: location = the built archive, then scripts/audit_secrets.py EXCLUDED_DIRS
  → cause = listing the archive turned up three `.serena/` members. The packable set is not computed from
    git's ignore rules but by walking the tree and applying that exclusion list, so a tool directory git
    already ignored in this commit was still packed; an earlier archive had carried two of those files as
    well, and nothing in the audit objected because they hold no credential.
  → fix = `.serena` added to EXCLUDED_DIRS with the reason, the archive rebuilt, and the members verified
    absent. Audited after the fix: 150 publishable files, 150 members, no `.serena` and no prompt file
    inside, every member hash compared against the working tree.
No-footer inspection: PASS over source, the built bundle, every served route, all report PDF pages and
  every generated export
Story/tag claim changes: none; the story never named the prompt file
One exact next action: none — the tree, the checks and the archive agree on the same 150 files.
Recovery: the removed file is one command away from any clone —
  git show 1e134ef:FREEBUFF_PROMPT.md > FREEBUFF_PROMPT.md
```

## Checkpoint M6-4 — the print edition of the report, and the font check that nearly lied

```
Timestamp / checkpoint ID:   2026-10-13 01:57 IST / M6-4
Milestone / branch / commit: M6 / main / pending
Actual implemented behavior: a second edition of the technical report now exists beside the prose one:
  track_2b/technical_report_deck.html -> track_2b/technical_report_deck.pdf, six A4 pages, authored with
  the Frontend Slides skill's "Swiss Modern" preset (Archivo 800 display + Nunito body, pure white and
  black with a single #ff3300 accent, visible column grid, asymmetric geometry). Two deliberate
  deviations from that skill's defaults: its fixed 1920x1080 stage is not used, because this artifact is
  printed and read and the submission caps the report at six pages, and pages flow rather than clip, so
  an overrunning page becomes a seventh page the builder refuses instead of a page that quietly loses
  its last paragraph. Only the page's own section label repeats from page to page; there is no page
  number, running title, document name, attribution or footer on any page.
  scripts/build_report_deck.py builds it and measures the produced PDF, not the renderer's settings:
  page count, a selectable text layer on every page, no fragment below the 51pt body floor, the shared
  footer/attribution marker list applied to every fragment, and the fonts. Archivo and Nunito are
  embedded in the HTML as base64 woff2 (latin subset, SIL OFL 1.1, recorded in
  track_2b/REPORT_FONTS_NOTICE.md) so the render needs no network at all.
Command / exit code / result:
  make report-deck -> EXIT 0
      rendered track_2b/technical_report_deck.pdf (467 KiB)
      PASS page count: 6 of 6
      PASS text layer on every page (words per page: 400, 403, 579, 458, 422, 463)
      PASS every section closes on its own page (6 sections, closing words found on each)
      PASS no text below the body column (lowest fragment per page: p1 172pt, p2 111pt, p3 94pt,
           p4 72pt, p5 140pt, p6 178pt; the floor is 51pt)
      PASS no footer, attribution or copyright marker on any page
      PASS no substitute face in the PDF; 55 embedded face(s) drawn as unnamed glyph programs
           (the only named fonts are the three DejaVu Sans Mono faces inline code uses)
  make report-pdf -> EXIT 0, unchanged: 4 body pages + a reference page, 0 fragments in the footer band
      (the shared renderer change is backward compatible)
  make no-footer -> EXIT 0, PASS: 78 files inspected, and both report PDFs measured page by page
  page geometry, measured in Chromium under print media before the PDF was trusted (ad hoc, /tmp):
      six .page sections, each exactly A4 wide (794px) with 0px horizontal overflow, and no element on
      any page crosses the A4 bottom edge (0 elements past it on all six) — so no content is clipped or
      hidden, which is what the flow layout promises rather than assumes
  content-loss gate, negative test (ad hoc): with a page's last 40 words removed, the new
      "every section closes on its own page" test flags exactly page 4; on the real artifact it passes
  lower-case attribution, negative test (ad hoc, /tmp/lc_deck.html): a line reading "powered by a tool
      vendor" placed inside a rendered page -> EXIT 1, "deck page 1:1: [attribution phrase] 'powered by'".
      The rendered-output scans (both report PDFs and this builder's own page scan) are now matched
      case-insensitively, because a rendered page is output and output should not be able to evade the
      rule by spelling it in lower case. Our own source stays case-sensitive: it is the one place the
      rule is written down, so the sentences that describe it would otherwise flag themselves.
  font gate, negative tests (ad hoc, /tmp copies; no repository file was modified)
      a required family the document never defines -> the render refuses rather than substitutes:
          "not registered: NonexistentFace"
      both @font-face URLs broken -> "failed to decode: Archivo, Nunito"
      the same broken document rendered with the document-level check bypassed -> the PDF names six
          substitute faces (AAAAAA+LiberationSans-Bold, ...) and contains 0 unnamed glyph programs, so
          the PDF-side gate flags the substitution on its own
  coverage gate, negative test (ad hoc, /tmp/nt): a closing footer element written into
      track_2b/technical_report_deck.html -> EXIT 1, "2 marker occurrence(s) found", reported at
      file:line with both the element and the attribution phrase named. The marker cannot be written
      literally in this log either: that same run failed on this file's first draft, which spelled it
      out, so the log now describes the element instead of quoting it.
Model / provider / mode / usage: none (typesetting, checks and documentation; no inference)
Blocker 3: location = the submission archive, then scripts/audit_secrets.py EXCLUDED_DIRS
  → cause = this session's own git worktree (.worktrees/fix-demo-video-clipping, created earlier today)
    sits inside the repository and holds a complete second checkout: 149 files, 22 MiB. The packaging
    walk and the audit both walk the tree and apply that exclusion list rather than git's ignore rules,
    so the archive silently grew from 154 to 303 members. Nothing objected because a duplicate of a
    clean file is still a clean file — the same blind spot that let `.serena` into an earlier archive,
    one directory over. The count printed on every run is what made it visible at all.
  → fix = `.worktrees` added to EXCLUDED_DIRS with the reason, and main's `.gitignore` finally learned
    `.worktrees/` (the earlier session had added that line inside the worktree, where it protected
    nothing). Archive rebuilt: 154 members, 11414 KiB, no worktree member, re-audited after writing.
Blocker 2: location = scripts/build_report_deck.py, the output path banner
  → cause = `--output /tmp/x.pdf` crashed with a ValueError traceback instead of reporting anything,
    because the progress line called Path.relative_to(REPO_ROOT) on a path outside the repository. The
    run was a real check, not a passing one, and a traceback is not a result.
  → fix = the banner falls back to the path as given when it is not inside the repository; the
    negative test above then ran to a verdict (EXIT 1, marker named) instead of crashing.
Blocker 1: location = scripts/build_report_deck.py, font_inventory()
  → cause = the first version read font names out of pypdf's resolved-object table. Chromium writes each
    font dictionary inline inside a page's /Resources instead, so that table holds no font object at
    all: the check reported zero embedded faces and failed a PDF that was in fact typeset correctly. The
    same blind spot would have reported "no fonts" on any document, so it could not have failed
    honestly either — a check that cannot distinguish the good case from the bad one is not a check.
  → fix = walk every page's /Resources, where the fonts actually live, and record subtype plus base name
    per font; the substitution test above then detected the real fallback in the broken copy.
No-footer inspection: PASS — the two report sources are now inside the static scan (SCAN_EXTRA_FILES),
  both report PDFs are measured page by page, and the rendered-output marker match is case-insensitive;
  nothing repeats at the bottom of any page and the only repeated element in the deck is each page's own
  section label (no page number, running title, document name, attribution or footer on any page)
Story/tag claim changes: `frontend-slides` added to docs/BUILT_WITH.md (23 of the allowed 25), described
  as a local authoring skill whose 1920x1080 stage was explicitly not used; README now lists the deck
  edition and the 265-test count it had drifted below
One exact next action: commit and push the deck, the builder, the coverage change and these docs.
Recovery note: the prose edition is unchanged by this work — `make report-pdf` still produces the same
  five-page `track_2b/technical_report.pdf` (4 body pages + the reference page), verified after the
  shared renderer gained its font argument.
```

## Checkpoint template

```text
Timestamp / checkpoint ID:
Milestone / branch / commit:
Actual implemented behavior:
Command / exit code / actual result / durable log:
Model / provider / mode / usage / validation failures:
Evidence and dataset versions:
Blocker: location → cause → fix:
No-footer inspection: routes and outputs checked / result:
Story/tag claim changes:
One exact next action:
```
