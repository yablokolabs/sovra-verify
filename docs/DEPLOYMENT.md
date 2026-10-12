# Deployment

## Modes, and which ones are actually verified

| Mode | Status |
|---|---|
| Local application + CSCS-hosted inference | **Verified.** This is the mode the delivered run used. |
| Docker-packaged local application + CSCS-hosted inference | **Verified.** `scripts/e2e_container.sh` built the image, started a fresh container through `scripts/launch.sh`, ran the full HTTP flow inside it and inspected the generated exports. See the recorded result below. |
| Configurable on-premise Apertus endpoint | **Adapter implemented, not tested.** The `local` provider speaks OpenAI-compatible Chat Completions against `SOVRA_LOCAL_BASE_URL`, but no real on-premise endpoint was available to test against. Not claimed as working. |
| Full Swiss-cloud application deployment | **Not attempted.** Hosting, storage, network residency and jurisdiction were not established, so no claim is made. |
| Air-gapped operation | **Not claimed.** See below. |

### Why air-gapped is not claimed

CSCS-hosted inference is external-network inference. A local web application that calls
`https://api.inference.cscs.ch/v1` is not air-gapped, and Swiss inference residency does not
establish residency of the whole application: the SQLite database, the stored originals, the exports
and any logs remain wherever the operator put them, under the operator's responsibility. CSCS
documentation states that prompts and responses are not recorded by CSCS and that inference data
stays within its infrastructure. That covers the inference call, not the application.

## Credentials

The application reads credentials in this order:

1. **the process environment** — `CSCS_INFERENCE_API_KEY`, `HUGGING_FACE_API_KEY`, `SOVRA_LOCAL_API_KEY`
2. **`~/.hermes/.env`** via a dotenv parser, for local development on the build host

Only the named application keys are extracted from that file. It is never shell-sourced, dumped,
copied into the repository, committed, packaged into an image, or included in a model prompt. Values
are masked everywhere they could reach a log, a subprocess argument, a diagnostic or a report
(`sovra.config.mask_secret`). Set `SOVRA_READ_HERMES_ENV=0` to disable the file entirely.

**Judges must use their own credentials.** No developer key ships with this repository. Set
`CSCS_INFERENCE_API_KEY` in your environment, or place it in your own `~/.hermes/.env`, or point
`SOVRA_CSCS_BASE_URL` at your own OpenAI-compatible Apertus endpoint.

### Docker

`scripts/launch.sh` is the tested explicit injection method. It reads **only**
`CSCS_INFERENCE_API_KEY` and `HUGGING_FACE_API_KEY` out of `~/.hermes/.env`, prints only a masked
form (`sk-g... (len=40)`), and passes the variables into the container **by name**, so the value
travels through the environment rather than through a file, an argument or an image layer.

`compose.yaml` deliberately has **no `env_file`**. Pointing `env_file` at `~/.hermes/.env` would pass
every unrelated secret in that file into the container, so it is not done. Secrets are never baked
into an image layer: the Dockerfile's frontend and runtime stages copy only source, and a build-time
guard fails the build if a credential-shaped string or a credential file is present under the
application tree.

### Recorded fresh-container run

```
make docker-build            -> image sovra-verify:local, EXIT 0
bash scripts/e2e_container.sh -> EXIT 0
  image config carries no credential variable                    (fail-fast check)
  0 file(s) under /app contain the credential value              (probe run inside the container)
  analysis 6d271966b36e4587 complete over the 4-document demo corpus
  24 claims, 20 resolved; 4 findings; a human review decision recorded and read back
  exports: analysis.json 28,502 B, bundle.zip 19,489 B, report.md 5,427 B, all footer-free
```

The container is started once through the launcher, and every later step uses plain `docker`
against the container id, because `compose.yaml` requires its credential variable for *any*
sub-command. The layer probe runs inside the container against the container's own environment
variable, so no credential value is ever placed on a command line or written to a log.

## Publishing checks

Two checks gate anything that leaves this host:

```
make audit                                    # secret and forbidden-file gate
python3 scripts/package_submission.py         # build and re-audit the submission archive
```

`make audit` compares the publishable tree against the real credential values, looks for
key-shaped strings independently of any known value, refuses `.env`-family and key files, and opens
every archive in the tree to scan its members. `scripts/package_submission.py` builds the archive
from exactly that publishable set, refuses to pack a flagged file, and re-opens the archive
afterwards to audit what was actually written. The recorded result is 143 publishable files and a
143-member archive at `dist/sovra-verify-submission.zip`, both clean.

## Cost

- CSCS inference is used through the account's own credential. **No verified price list was
  available, so no cost per case or total spend is reported.** Reporting a dollar figure without a
  verified price would be an invented number.
- The Hugging Face account is on a free tier with a user-reported $10 credit balance. That balance was
  not measured, and no dedicated paid endpoint was deployed.
- `max_output_tokens`, a bounded comparison cap (`SOVRA_MAX_COMPARE_PAIRS`, default 60), a chunk cap
  and a total extracted-text budget bound the work done per analysis. Retries are capped at two with
  backoff, and only transient errors are retried; an authentication or quota error fails immediately.

## Security notes for operators

- Imported documents are untrusted data. Their text can never choose a provider, a URL, a tool or a
  file path, and the prompts state this explicitly.
- `SOVRA_LOG_PROMPT_CONTENTS` is off by default, so document text does not reach the default logs.
- Uploads are stored under random internal names; the supplied filename is never used as a path.
  Encrypted PDFs and oversized files are rejected with an explicit reason, and a scanned PDF reports
  "OCR not implemented" rather than producing empty evidence.
- Do not send sensitive real documents to any provider without authorisation and an appropriate data
  review. A pilot should use a deidentified, consenting corpus.

## Known gaps

- The local/on-premise provider adapter has never been pointed at a real endpoint.
- No authentication is implemented on the API. It is a single-user local prototype and must not be
  exposed to a network without one.
- The container run used the credential injected at run time on this host. A judge must supply their
  own, and that path is documented above rather than exercised with someone else's key.
- The submission archive is built and audited locally. It has not been uploaded anywhere.
