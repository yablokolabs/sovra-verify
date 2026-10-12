# Audio Plan

## Plan

VO-only track. Single full-file voiceover placed at 0s, loudness-normalised to broadcast speech level. The narration carries the whole two-minute demo; there is no music and no sound effects, so nothing competes with the measured numbers being read out.

### Cue 1 — narration (full file, 0s)

```
SOURCE:      audio/originals/voiceovers/alice-uk-v1/audio.mp3
PROVIDER:    elevenlabs (eleven_multilingual_v2)
VOICE:       Alice - Clear, Engaging Educator (premade, British, female)
PLACEMENT:   0s, full file, no trim
VOLUME:      0 dB, loudnorm to -16 LUFS integrated, true peak -1.5 dB
FADES:       none
```

ffmpeg snippet:

```
[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v0]
```

### Final mix command

```bash
ffmpeg -y \
  -i audio/originals/voiceovers/alice-uk-v1/audio.mp3 \
  -filter_complex "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v0]" \
  -map "[v0]" -c:a libmp3lame -q:a 2 \
  audio/tracks/v1/track.mp3
```

## Log

### 2026-10-12 — VO-only plan created

Single narration cue. Audio measured at 117.4 s across 250 words, which fits the official two-minute demonstration limit. The first generation ran 138 s and was rewritten shorter before this plan was written; the 138 s take is not used and is not referenced by any cue.

Voice selection note: the brief asked for a British young female voice. The British young female voices in the account are ElevenLabs library voices, and the free tier refuses library voices through the API (HTTP 402 `paid_plan_required`). Voice design and voice cloning are paid-plan only as well (HTTP 403 `feature_not_available`). No additional spend was authorised, so the closest usable premade voice was used: Alice, British and female. This deviation is recorded in `audio_meta.json` next to the audio.

### 2026-10-12 — the declared script reconciled to the take that was recorded

The take above is the trimmed one: the first generation ran 138 s and was cut to fit
the two-minute limit. What was kept in the project was the longer draft — each
segment's `voiceover` field, `voiceover_script/script.md` and this folder's
`provider_script.md` all described the 138 s text, not the 117.4 s take. The film
played one script while every file next to it described another.

All three now carry the recorded text. The fields, `script.md` and
`provider_script.md` are written by `node scripts/derive-advances.mjs --write` from
the take itself, and `node scripts/check-audio.mjs` fails if any of them stops
matching the provider's word alignment — so the same drift cannot happen again
silently. Advance times were re-derived at the same time, which is what gives
`sovra-finding` its verdict beat and `sovra-results` a beat for its closing card.

## Pending take — not recorded, awaiting approval

The closing card carries two sentences the narration never reads: that Swiss
inference residency does not establish residency of the whole application, and that
the figures are one run over four synthetic documents rather than a general accuracy
claim. A second take would read them. Nothing has been sent to the provider; the text
below is a proposal.

Budget, using this voice's measured pace on the delivered take
(12.86 characters per second, 2.13 words per second):

| | Characters | Estimated | Words |
|---|---|---|---|
| Delivered take (measured) | 1,510 | 117.4 s | 250 |
| This draft (measured by count) | 1,465 | 114.4 s | 244 |
| Limit | | 120 s | |

It covers both missing sentences and stays 5.6 s inside the limit by trimming
prose the screen already shows: the four document names sit on four cards in the
corpus scene, the token and latency figures sit in the results grid, and the
"every displayed citation resolved" line is the grid's 100% figure. No claim the
screen does not make has been dropped.

A new take costs one generation at roughly the delivered take's 1,522 billed
characters, and its length can differ from the estimate by a few seconds; if it
lands above 118 s the copy has to be cut again, which is a second generation. The
draft is held 5.6 s short of the limit to leave room for that.

Proposed text, one paragraph per scene, in reading order:

```
Teams compare a supplier agreement, a payment policy and an invoice by hand. An
answer that cannot show its source is not evidence. Sovra Verify returns the exact
passages.

Four synthetic documents go in: an agreement, a policy, an invoice and an amendment.
Each file is hashed into canonical passages with page and character offsets.

Apertus 1.5 70B, hosted on CSCS, reads the passages and nominates claims: 25 claims
found, 10 candidate pairs compared, 13 provider calls, none failed.

The agreement sets payment at 30 days from the invoice date. The policy says invoices
are settled within 60 days, under the same effective date. Both quotes are sliced
from canonical text at the recorded offsets.

Two pairs are not conflicts. An expedited freight clause sets a 10 day period as a
stated exception, and the amendment changes payment to 45 days from 1 May 2026.
Sovra Verify flags potential inconsistencies for a human. It does not decide which
document wins.

A reviewer confirms or dismisses each finding, and the decision is recorded with a
note. Export carries the source hash, the page, the offsets, and the model that
produced the run.

On four documents: 25 claims, 10 pairs compared, 13 calls, zero failures. CSCS hosted
inference is external network inference, so a local app calling CSCS is not air
gapped. Swiss inference residency does not make the whole application Swiss. These
figures are one run over four synthetic documents, not a general accuracy claim.
```

On approval the workflow is: write these paragraphs into the seven `voiceover`
fields, generate the take, save it as take `alice-uk-v2` with its `audio_meta.json`
and alignment, re-cut the track with the loudnorm command above, then run
`node scripts/derive-advances.mjs --write`, which re-times every scene from the new
alignment, and `npm run check`, which fails if any file still describes the old one.
