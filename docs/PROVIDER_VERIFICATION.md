# Provider verification

All results below were produced on the build host on 2026-10-12 (Asia/Kolkata) by
`scripts/verify_providers.py` and by direct `httpx` calls during M0. No credential value appears in
this file; only whether a variable is present and its masked form.

## Credential resolution

| Variable | Where | Present | Masked form |
|---|---|---|---|
| `CSCS_INFERENCE_API_KEY` | `~/.hermes/.env` | yes | `sk-g...` (len=40) |
| `HUGGING_FACE_API_KEY` | `~/.hermes/.env` | yes | `hf_...` (len=37) |
| `ELEVENLABS_API_KEY` | `~/.hermes/.env` | yes | used only by the video pipeline, never by the application |

`CSCS_INFERENCE_API_KEY` was the intended application variable and did not need aliasing. The file
was read with a dotenv parser; only the named entries were extracted. It was never shell-sourced,
dumped, copied into the repository, or passed to Docker. Loading order in the application is
**process environment first, credential file second**, so a container or CI run can inject a key
without the file existing at all.

## CSCS — primary provider

Endpoint: `https://api.inference.cscs.ch/v1`, bearer auth, OpenAI-compatible chat completions.

### Cross-check against the CSCS documentation

Source: CSCS LLM Inference API service documentation,
`https://docs.cscs.ch/services/inference/api/#llm-inference-api-service`, consulted 2026-10-12.
This is a documentation cross-check, not a substitute for the live calls recorded below.

| Documented fact | Our configuration | Agrees |
|---|---|---|
| Base URL `https://api.inference.cscs.ch/v1` | `CSCS_BASE_URL`, and `SOVRA_CSCS_BASE_URL` default | yes |
| Credential variable `CSCS_INFERENCE_API_KEY` in the documented `curl` examples | `credential_env="CSCS_INFERENCE_API_KEY"` | yes |
| Bearer token on every request | `Authorization: Bearer <key>` in the provider transport | yes |
| `/v1/models` and `/v1/chat/completions` (OpenAI-compatible) | the two endpoints used | yes |

The documentation names the credential variable `CSCS_INFERENCE_API_KEY` itself, which confirms the
application variable name independently of the credential file. The docs also list `/v1/messages`
(Anthropic-compatible) and `/v1/embeddings`; neither is used here.

Two documented properties shaped the design:

- **Apertus v1.5 70B declares a 262,144-token maximum context** and text, image, audio and video input.
  The application does not rely on that headroom: ingestion caps extracted text at 400,000 characters
  and each request is chunked well below the window. The declared context is a provider limit, not a
  budget we verified by filling.
- **The `-thinking` variants are served with tool use disabled.** Sovra Verify does not use tool
  calling, and it selects the non-thinking `swiss-ai/Apertus-v1.5-70B`, so this restriction does not
  affect any code path. It does rule out treating a thinking variant as a drop-in swap.

The documentation states that CSCS does not record user prompts or model responses and that data
does not leave the infrastructure CSCS controls, and it recommends auditing model output. That
matches the application design — untrusted imported documents, deterministic validation of every
cited span, and a human decision on each finding — but it is a statement about the provider's
handling of inference traffic only. It says nothing about where this application stores or hosts
its own documents, and is not presented as a compliance claim.

`GET /models` → **HTTP 200**, 11 models returned:

```
swiss-ai/Apertus-70B-Instruct-2509
swiss-ai/Apertus-8B-Instruct-2509
swiss-ai/Apertus-v1.5-70B
swiss-ai/Apertus-v1.5-70B-thinking
swiss-ai/Apertus-v1.5-8B
swiss-ai/Apertus-v1.5-8B-thinking
google/gemma-4-31B-it
zai-org/GLM-5.2
zai-org/GLM-5.3
moonshotai/Kimi-K2.7-Code
nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16
```

The exact model id selected as the application default is **`swiss-ai/Apertus-v1.5-70B`** — the
non-thinking variant, matching the identifier the provider itself returns.

Real inference check, `POST /chat/completions` with a short synthetic payment-terms pair:

| Field | Value |
|---|---|
| HTTP status | 200 |
| Latency | 0.51 s |
| `model` echoed | `swiss-ai/Apertus-v1.5-70B` |
| Content | `conflict` |
| Usage | `prompt_tokens` 62, `completion_tokens` 3, `total_tokens` 65 |

A successful `/models` call is not treated as proof of inference. This is a separate, real
completion, and the result was non-empty.

## Hugging Face — backup provider

Endpoint: `https://router.huggingface.co/v1`.

`GET /models` → **HTTP 200**, 126 models. Apertus entries in that list:
**only `swiss-ai/Apertus-8B-Instruct-2509`**.

`GET https://huggingface.co/api/models/swiss-ai/Apertus-v1.5-70B?expand[]=inferenceProviderMapping`
→ the only provider mapping is `featherless-ai` with `"status": "error"`. The 1.5 70B model is
therefore **not servable** through this account's router. `swiss-ai/Apertus-v1.5-8B` has an empty
provider mapping.

Real inference check against the one Apertus model the router does expose:

| Field | Value |
|---|---|
| Model | `swiss-ai/Apertus-8B-Instruct-2509` (not 1.5) |
| HTTP status | 200 |
| Latency | 2.23 s |
| Content | `ok` |
| Usage | `prompt_tokens` 67, `completion_tokens` 2, `total_tokens` 69 |
| Echoed model | `swiss-ai/apertus-8b-instruct` |

**Conclusion carried into the code:** the Hugging Face router cannot stand in for the 70B default.
The backup is disabled by default (`SOVRA_BACKUP_ENABLED=0`), automatic fallback is disabled by
default (`SOVRA_ALLOW_BACKUP_FALLBACK=0`), and switching requires both flags. A backup call is
recorded with `is_backup = true` and `downgraded_from` set, so a model change is always visible.

An 8B run is never a silent substitute: `check_model_policy` refuses to select any 8B model unless
`SOVRA_ALLOW_OPTIONAL_8B=1` is set explicitly.

## Re-verification after the citation-resolution fix

The M0 calls above were made before the provider layer and the citation resolver were finished. Both
credentials were therefore re-verified through the application's own script on the same day, with
`make verify-providers` exit 0:

| Check | CSCS | Hugging Face |
|---|---|---|
| `GET /models` | HTTP 200, 11 models, 324 ms | HTTP 200, 124 models, 86 ms |
| Configured model served | `swiss-ai/Apertus-v1.5-70B` present | `swiss-ai/Apertus-8B-Instruct-2509` present |
| Real completion | 441 ms, usage 40/6/46 | 1,218 ms, usage 36/6/42 |
| Echoed model | `swiss-ai/Apertus-v1.5-70B` | `swiss-ai/apertus-8b-instruct` |
| Returned text | `{"ok": true}` | `{"ok": true}` |
| Smoke pair | `potential_conflict`, 2 resolved citations, 582 tokens | not run (backup, disabled) |
| Configured model identical to the default? | yes | no — the router serves the 8B instruct model only |

The model counts move as a provider changes its catalogue: 126 at M0, 124 on re-verification. Neither
number is a capability claim — what matters is the row above it, which did not change.

This re-verification surfaced a real defect in the verification script itself: `step_pair` still
called `citations.resolve_all(canonical_text=...)`, an argument removed when citation resolution was
fixed to resolve each span against its own document's text. The script raised `TypeError` until the
call was corrected to `canonical_by_document`. No automated test covered that script, so the drift
survived until the script was run by hand — which is why the run is part of the release sequence and
not a one-off.

## What was not verified

- No provider call was made with an on-premise or local Apertus endpoint; the `local` adapter exists
  in the provider layer but is untested against real hardware.
- `$10` Hugging Face credit is user-reported. No balance was measured, and no assumption is made
  that credit covers any particular call.
- CSCS rate limits, quotas and token ceilings were not probed to their limits; only ordinary
  requests were made. `429`, `402` and `401` handling is unit-tested against injected responses, not
  against a live refusal from either provider.
- The thinking variants of Apertus 1.5 are listed by the provider but were not selected or tested.
