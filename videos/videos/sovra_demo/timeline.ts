import '../../styles/editorial-mono/fonts.css';
import '../../styles/editorial-mono/tokens.css';
import type { Timeline } from 'videowright';
import defaultAudioTrack from './audio/tracks/v1/track';

/**
 * Sovra Verify — two-minute demo.
 *
 * Editorial Mono. Seven scenes: the problem, the corpus, the real Apertus run,
 * the finding with its evidence, the negative cases, review and export, then
 * the measured results and the deployment limit. The last scene ends on the
 * limitation itself; there is no closing card.
 *
 * Audio: VO-only track v1, ElevenLabs narration, 117.4 s.
 */
const timeline: Timeline = {
	meta: {
		title: "Sovra Verify — Don't Just Answer. Prove It.",
	},
	segments: [
		{ id: 'sovra-problem' },
		{ id: 'sovra-corpus', transition: 'fade' },
		{ id: 'sovra-run', transition: 'fade' },
		{ id: 'sovra-finding', transition: 'fade' },
		{ id: 'sovra-negative', transition: 'fade' },
		{ id: 'sovra-review-export', transition: 'fade' },
		{ id: 'sovra-results', transition: 'fade' },
	],
	default_audio_track: defaultAudioTrack,
};

export default timeline;
