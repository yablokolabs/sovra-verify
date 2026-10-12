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
