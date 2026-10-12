# Built With

**Listed tags: 22 of an allowed 25.** Every one is a technology that is actually present in this
repository and was used to produce the delivered artifacts. Nothing is listed because it sounds
impressive, and the section at the end names what was deliberately left out and why - those names
are explanations, not tags.

## Applied for the first time in this project's build

**`apertus`** — `swiss-ai/Apertus-v1.5-70B` is the default model and performed all claim
identification and comparison reasoning. In the delivered demonstration run: 11 real calls, 0
failures, 13,892 tokens, 8 findings and 16 citations that all re-derived from canonical text
(`track_2b/data/evaluation/PROOF.json`).

**`cscs`** — the primary inference provider, `https://api.inference.cscs.ch/v1`. Verified with
`GET /models` (HTTP 200, 11 models) and a real completion.

**`diagram-design`** — produced `docs/diagrams/architecture.html` and its exported SVG and PNG.

**`videowright`** — produced the two-minute demonstration video. Project, segments, narration script
and audio plan are under `videos/`.

**`elevenlabs`** — generated the demonstration narration with `eleven_multilingual_v2`.

**`lightpanda`** — a headless browser that rendered the running interface so the sentences a reviewer
reads could be checked on a live screen rather than inferred from source, and produced the two
screenshots under `docs/demo/screenshots/`. Its CDP server is driven by `scripts/browser_check.py`
(`make ui-check`). It is a development tool: the application neither depends on it nor ships it, and
the check skips cleanly when it is absent.

## Applied as previously established practice

`python`, `fastapi`, `pydantic`, `sqlite`, `docker`, `pytest`, `react`, `typescript`, `vite`,
`pymupdf`, `pypdf`, `httpx`, `make`, `node.js`, `ffmpeg`.

## Roles, stated accurately

| Tag | Role in this project |
|---|---|
| `apertus` | Claim identification and bounded claim comparison |
| `cscs` | Primary hosted inference endpoint |
| `huggingface` | **Reachable but not used for the default model.** Its router serves only `swiss-ai/Apertus-8B-Instruct-2509`; Apertus 1.5 70B is not servable there. The adapter exists and is off by default. |
| `elevenlabs` | Demonstration narration only. The application never calls it. |
| `videowright` | Demonstration video authoring and rendering |
| `diagram-design` | Architecture diagram source |
| `docker` | Packaging and the documented `make run` entry point |
| `pymupdf` | Text-native PDF extraction (license reviewed before adoption) |
| `lightpanda` | Development tooling only: renders the running interface for `make ui-check` and for the delivery screenshots. Not installed with, or called by, the application. |
| `pypdf` | Development tooling only: measures the rendered report's page count and page edges so the no-footer rule can be checked on a PDF rather than hoped for. Not installed in the application image. |

## Deliberately not listed

`openai` — the transport is OpenAI-compatible, but no OpenAI model or service is used. Listing it
would misrepresent where inference happens.

`postgresql`, `pgvector`, `redis`, `kubernetes`, `terraform`, `ocr`, `hindsight`, `mcp`,
`langchain`, `huggingface-inference-endpoints`, cloud platform tags — none of these are implemented
or used. Full-text search and bounded exhaustive comparison over SQLite were sufficient for a corpus
of this size, so no vector database was adopted.

## Evidence for these tags

- Provider evidence: `docs/PROVIDER_VERIFICATION.md`, `track_2b/data/evaluation/PROVIDER_VERIFICATION.json`
- Delivered demonstration run: `track_2b/data/evaluation/PROOF.json` and `PROOF.md`
  (11 calls, 0 failed, 16 citations re-derived from canonical text)
- Evaluation ledger: `track_2b/data/evaluation/RESULTS.json` (`provider_ledger`) with a measured
  accuracy of 0.36 over 25 cases — reported as measured, not as a target met
- Release checks: `make audit` (secret and forbidden-file gate), `make no-footer`, and `make ui-check`
  (the same footer rule plus the coverage sentences, checked on a real browser render; the record is
  `track_2b/data/evaluation/UI_RENDER.json` and the screenshots are `docs/demo/screenshots/`)
- Python dependencies: `track_2b/backend/requirements.txt`
- Frontend dependencies: `track_2b/frontend/package.json`
- Video toolchain: `videos/package.json`, `videos/videos/sovra_demo/`
- Narration record: `videos/videos/sovra_demo/audio/originals/voiceovers/alice-uk-v1/audio_meta.json`
- Diagram source: `docs/diagrams/architecture.html`
