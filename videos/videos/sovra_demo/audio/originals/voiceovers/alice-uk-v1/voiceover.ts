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
 * Advance times are segment-relative and derived from the provider word alignment:
 * each internal beat is placed at its even share of the segment and then snapped to
 * the nearest sentence boundary within three seconds, so a beat reveals its content
 * as that sentence starts. The renderer treats a segment's last advance as its whole
 * duration, so that final value is the segment's full narration span rather than a
 * point that stops short of the next section; the seven spans sum to 117.432 s, the
 * length of the narration file, so the closing sentence is never clipped.
 */
const voiceover: Voiceover = {
	audio_file: './audio.mp3',
	provider: 'elevenlabs',
	provider_timing_file: './timing.json',
	eleven_labs_voice_id: 'Xb7hH8MSUJpSbSDYk0k2',
	notes: 'Audio 117.4 s, 250 words, 1522 billed characters.',
	timing: {
		perSegment: {
			'sovra-problem': [5.712, 13.56],
			'sovra-corpus': [3.816, 8.15, 11.448, 15.464],
			'sovra-run': [6.133, 12.266, 18.599],
			'sovra-finding': [4.366, 10.508, 15.744],
			'sovra-negative': [7.104, 13.804, 21.513],
			'sovra-review-export': [5.689, 12.609],
			'sovra-results': [11.784, 19.943],
		},
	},
};

export default voiceover;
