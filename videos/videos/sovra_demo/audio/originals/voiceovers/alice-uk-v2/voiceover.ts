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
 * than a point that stops short of the next section; the seven spans sum to 115.224 s,
 * the length of the track (the take plus a 0.8 s silent tail), so the closing sentence is never clipped.
 */
const voiceover: Voiceover = {
	audio_file: './audio.mp3',
	provider: 'elevenlabs',
	provider_timing_file: './timing.json',
	eleven_labs_voice_id: 'Xb7hH8MSUJpSbSDYk0k2',
	notes: 'Audio 114.4 s, 247 words, 1536 billed characters.',
	timing: {
		perSegment: {
			'sovra-problem': [6.316, 13.653],
			'sovra-corpus': [0.5, 3.889, 8.289, 13.224],
			'sovra-run': [1.021, 7.058, 13.537],
			'sovra-finding': [0.5, 4.702, 11.018, 15.429],
			'sovra-negative': [2.276, 14.153, 21.212],
			'sovra-review-export': [5.677, 11.157],
			'sovra-results': [0.5, 6.571, 27.012],
		},
	},
};

export default voiceover;
