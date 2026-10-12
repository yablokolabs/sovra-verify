# Plan: Sovra Verify — Don't Just Answer. Prove It.

## Purpose

- Audience: hackathon judges and a technical reviewer who has not seen the application.
- Takeaway: Sovra Verify audits a small document corpus for potential
  inconsistencies, and every claim it shows is anchored to a span that was
  derived deterministically from canonical extracted text.
- Constraints / hard guidelines:
  - Two minutes. Narration target 115-125 seconds.
  - The Sovra Verify logo appears once, on the opening scene, as a mark next to
    the product name. It never appears in a closing frame.
  - No closing attribution of any kind: no closing card, no rights notice, no
    "Powered by", no "Built with", no attribution bar, no vendor badge, no page
    numbers, no sign-off. The last scene ends on the deployment limitation.
  - Only measured numbers. No customer, no ROI, no accuracy percentage, no
    "production ready", no certification, no legal or compliance conclusion.
  - No secret, key or endpoint token anywhere in the video.

## Style

- Active style: `editorial-mono`
- Notes:
  - One deliberate deviation from the style's "one red accent per scene" rule,
    recorded here rather than made silently: in `sovra-finding` the accent marks
    the two conflicting values (`30 days`, `60 days`). That is a single device
    with a single meaning, the point of the scene, and it is confined to that one
    scene. Every other scene uses the accent at most once.
  - The style's "no logo placeholder" guidance for CTA scenes is moot here: there
    is no CTA scene and no closing card.

## Audio intent

- Voiceover: yes
- Sound effects: no
- Background music: no
- Notes: single continuous narration read to the scene schedule in the
  `advances` arrays. A young British female voice, calm and considered, matching
  the editorial register. VO-only track, no mix.

## Segment outline

1. `sovra-problem` — the opening mark and the problem: an answer without a source
   is not evidence.
2. `sovra-corpus` — four synthetic documents in, each hashed and extracted into
   canonical passages; hostile or unscannable input refused.
3. `sovra-run` — the real Apertus 1.5 70B run on CSCS, with the measured call
   count, token usage and latency.
4. `sovra-finding` — the genuine conflict: agreement 30 days versus policy 60
   days, same effective date, each with its canonical span and offsets.
5. `sovra-negative` — the stated exception and the different effective date, plus
   the explicit statement that a human decides.
6. `sovra-review-export` — review states and the export bundle with provenance.
7. `sovra-results` — measured figures and the deployment limitation. Final scene.

## Timing

`advances` are segment-relative seconds, and the renderer uses the **last**
entry of a segment's array as that segment's whole duration: it walks the
schedule frame by frame and advances its clock by that value before the next
segment mounts.

Two layers are involved. The `advances` written in each `segments/<id>/index.ts`
are the schedule the scenes were authored against, before a voice existed:

| Segment | Declared advances | Scene length |
|---|---|---|
| sovra-problem | [7.5, 15.0] | 15 s |
| sovra-corpus | [4.5, 9.0, 13.5, 19.0] | 19 s |
| sovra-run | [5.0, 11.0, 20.0] | 20 s |
| sovra-finding | [5.0, 10.0, 15.0, 20.0] | 20 s |
| sovra-negative | [5.0, 11.0, 20.0] | 20 s |
| sovra-review-export | [6.0, 14.0] | 14 s |
| sovra-results | [6.0, 14.0] | 14 s |
| **Total** | | **122 s** |

Script word count 304. At the reference pace of 150 words per minute
(2.5 words per second) that is 121.6 seconds of narration, which matches the
122 second scene schedule to within half a second. See
`voiceover_script/script.md` for the per-segment count.

That 122 s schedule is a plan, not the delivered timing. The recorded
narration came in at 117.432 s, so `audio/tracks/v1/track.ts` overlays the
alignment-derived schedule on top of the declared advances, and that is what
the render uses:

| Segment | Rendered advances | Narration span |
|---|---|---|
| sovra-problem | [5.712, 13.56] | 0.0 – 13.56 s |
| sovra-corpus | [3.816, 8.15, 11.448, 15.464] | 13.56 – 29.024 s |
| sovra-run | [6.133, 12.266, 18.599] | 29.024 – 47.623 s |
| sovra-finding | [4.366, 10.508, 15.744] | 47.623 – 63.367 s |
| sovra-negative | [7.104, 13.804, 21.513] | 63.367 – 84.88 s |
| sovra-review-export | [5.689, 12.609] | 84.88 – 97.489 s |
| sovra-results | [11.784, 19.943] | 97.489 – 117.432 s |
| **Total** | | **117.432 s** |

Each span runs to the next section's first word, and the last runs to the end
of the file, so the seven durations sum to exactly the narration length and no
spoken word falls past the picture. At 60 fps the per-segment frame rounding
puts each scene boundary within 30 ms of its section start and none before it.

`waitForNext()` is placed at every point where the narration moves to a new
subject, so re-recording the voice only changes timing data and never requires
rewriting a segment. `hold()` is used only for entrance lead-in and for the
dwell inside a beat after its last reveal.

## Script

Full script, with per-segment word counts: `voiceover_script/script.md`.

### sovra-problem

Procurement teams compare a supplier agreement, a payment policy and an invoice
by hand. A language model answer that cannot show where it came from is not
usable evidence. Sovra Verify audits the corpus and returns the exact passages.

### sovra-corpus

Sovra Verify starts from a corpus. Four synthetic documents go in: a master
supply agreement, an accounts payable policy, an invoice, and an amendment.
Each file is hashed, and its text is extracted into canonical passages with page
and character offsets. Scanned pages are refused, not guessed at.

### sovra-run

Apertus one point five 70 billion, hosted on CSCS, reads the passages and
nominates typed claims. It found 25 claims, and Sovra Verify compared 10
candidate pairs. Thirteen provider calls, none failed, with fifteen thousand six
hundred and fifty tokens and seventy one seconds of latency.

### sovra-finding

The master supply agreement says payment is due within 30 days of the invoice
date. The accounts payable policy says invoices are settled within 60 days,
under the same effective date. Both quotes are sliced from canonical text at the
recorded offsets. The model never writes the quote.

### sovra-negative

Two of the pairs are not conflicts. The expedited freight clause sets a 10 day
period as a stated exception, and the amendment changes payment to 45 days,
effective the first of May 2026. Sovra Verify flags potential inconsistencies
for a human reviewer. It does not decide which document wins.

### sovra-review-export

A reviewer confirms or dismisses each finding, and the decision is recorded with
a note. Export carries the source hash, the page, the character offsets, and the
model that produced the run.

### sovra-results

On four documents: 25 claims, 10 pairs compared, 13 calls, zero failures, and
every displayed citation resolved to an exact slice of canonical text. CSCS
hosted inference is external network inference, so a local app calling CSCS is
not air gapped.

## Measured facts used on screen

From one recorded analysis over the four synthetic demo documents:

- Provider `cscs`, model `swiss-ai/Apertus-v1.5-70B`, base `https://api.inference.cscs.ch/v1`.
- 4 documents, 25 claims, 10 candidate pairs compared, 13 provider calls.
- 0 failed calls. 15,650 total tokens: 11,168 prompt, 4,482 completion.
- 71.5 s of total provider latency.
- Conflict spans: agreement document page 1 offsets [342, 531];
  policy document page 1 offsets [239, 430].

Anything not on this list is not stated in the video.

---

## Log

### 2026-10-12 — Initial scaffold

- Created segments: `sovra-problem`, `sovra-corpus`, `sovra-run`,
  `sovra-finding`, `sovra-negative`, `sovra-review-export`, `sovra-results`.
- Created shared component `components/scene-frame` (cream page, hairline rules,
  mono eyebrow label, shared `settle()` and `fadeIn()` entrance helpers). Used by
  all seven scenes, which is why it was extracted rather than inlined.
- Timeline: 7 segments, style `editorial-mono`, fade between scenes.
- Voiceover: drafted to the official two-minute script shape, 304 words,
  estimated 121.6 s at 150 words per minute against a 122 s scene schedule.
- Logo: the mark on `sovra-problem` only. No closing card.
- Deliberate deviation logged under Style: the accent marks two values in
  `sovra-finding`, because they are the single point of that scene.

### 2026-10-12 — Render defects found and fixed

Two defects were visible in the first rendered MP4 and are fixed here.

- **The mark never appeared.** `sovra-problem` pointed at `/brand/sovra-logo.png`.
  The dev and render servers root themselves in the videowright package and serve
  this project through an alias, so a root-absolute path into the project resolved
  against the package and 404'd; the `<img>` rendered as an empty box. The asset now
  lives in `assets/brand/sovra-logo.png` and the segment imports it, so Vite serves
  the project's own file. `videos/public/` no longer exists.
- **The picture stopped 0.83 s before the narration did.** The overlay in
  `track.ts` ended each segment 0.2 s before the next section began, on the
  assumption that a segment's duration was independent of its last advance. It is
  not: the renderer takes the last advance as the whole segment duration, so the
  seven values summed to 116.60 s against 117.432 s of audio and ffmpeg's
  `-shortest` clipped the closing words of the last sentence. Each span now runs to
  the next section's first word (and to the end of the file for the last segment),
  which also removes up to 1.2 s of accumulated drift between picture and voice.
  Re-rendered length and the audit of the delivered MP4 are recorded in
  `docs/PROGRESS.md`.
