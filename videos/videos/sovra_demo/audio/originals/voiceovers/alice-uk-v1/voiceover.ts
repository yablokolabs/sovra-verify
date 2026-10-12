import type { Voiceover } from 'videowright';

/**
 * Voiceover for the Sovra Verify demo.
 *
 * Provider: ElevenLabs, model eleven_multilingual_v2.
 * Voice: Alice - Clear, Engaging Educator (premade, British, female).
 * audio_meta.json records why: the requested British young female voices are
 * library voices that the free tier refuses through the API (HTTP 402), and voice
 * design is paid-plan only (HTTP 403). The closest usable premade voice was used
 * and no additional spend was authorised.
 *
 * Advance times are segment-relative and derived from the provider word alignment by
 * `node scripts/derive-advances.mjs --write`, the same command that writes the audio
 * track's timing: each reveal sits at the start of the sentence that motivates it
 * (the sentence assigned to each one is recorded in ../../../beat_map.json), a
 * sentence cited twice has its speaking time split evenly, and no advance is below
 * the floor the renderer needs. The renderer treats a segment's last advance as its
 * whole duration, so that final value is the segment's full narration span rather
 * than a point that stops short of the next section; the seven spans sum to 117.432 s,
 * the length of the narration file, so the closing sentence is never clipped.
 */
const voiceover: Voiceover = {
	audio_file: './audio.mp3',
	provider: 'elevenlabs',
	provider_timing_file: './timing.json',
	eleven_labs_voice_id: 'Xb7hH8MSUJpSbSDYk0k2',
	notes: 'Audio 117.4 s, 250 words, 1522 billed characters.',
	timing: {
		perSegment: {
			'sovra-problem': [6.223, 13.56],
			'sovra-corpus': [0.5, 4.075, 8.661, 15.464],
			'sovra-run': [1.185, 9.73, 18.599],
			'sovra-finding': [0.5, 4.691, 11.018, 15.744],
			'sovra-negative': [2.635, 14.245, 21.513],
			'sovra-review-export': [6.073, 12.609],
			'sovra-results': [0.5, 12.167, 19.943],
		},
	},
};

export default voiceover;
