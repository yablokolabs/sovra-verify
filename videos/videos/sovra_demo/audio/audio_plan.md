# Audio Plan

## Plan

VO-only track. Single full-file voiceover placed at 0s, loudness-normalised to broadcast speech level, with a 0.8 s silent tail. The narration carries the whole two-minute demo; there is no music and no sound effects, so nothing competes with the measured numbers being read out.

### Cue 1 — narration (full file, 0s)

```
SOURCE:      audio/originals/voiceovers/alice-uk-v2/audio.mp3
PROVIDER:    elevenlabs (eleven_multilingual_v2)
VOICE:       Alice - Clear, Engaging Educator (premade, British, female)
PLACEMENT:   0s, full file, no trim, 0.8 s silent tail
VOLUME:      0 dB, loudnorm to -16 LUFS integrated, true peak -1.5 dB
FADES:       none
```

ffmpeg snippet:

```
[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,apad=pad_dur=0.8[v0]
```

### Final mix command

```bash
ffmpeg -y \
  -i audio/originals/voiceovers/alice-uk-v2/audio.mp3 \
  -filter_complex "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,apad=pad_dur=0.8[v0]" \
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

### 2026-10-13 — second take recorded: the narration reads the closing card

The closing card carried two sentences the first take never read: that Swiss
inference residency does not establish residency of the whole application, and that
the figures are one run over four synthetic documents rather than a general accuracy
claim. The owner approved a script that reads the card in full and one generation.

Take `alice-uk-v2` replaces `alice-uk-v1` (the first take stays in the repository
history). Same voice and model. 1,536 billed characters, 247 words, 114.4 s. The
first request was refused with `quota_exceeded` (96 credits left, nothing billed);
the take was generated after the owner supplied a key with credits.

To stay inside the two-minute limit the script drops phrases the screen already
shows: "with page and character offsets" in the corpus scene, the token and latency
figures in the run scene, "with a note" and "that produced the run" in the review
scene, and the spoken repeat of the four counts in the results scene.

The take ends 0.4 s after the last spoken sound, which made the film stop on the
last word. The cue now has a 0.8 s silent tail (`apad=pad_dur=0.8`), so the track is
115.224 s at -16.7 LUFS. Advances were re-derived with
`node scripts/derive-advances.mjs --write` and `npm run check` passes.
