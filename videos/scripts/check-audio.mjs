#!/usr/bin/env node
/**
 * Check the narration against the artifacts that claim to describe it.
 *
 * The failure this exists for: the recorded take was trimmed to fit the
 * two-minute limit, the scene files kept the longer draft, and nothing noticed.
 * The film played one script while `script.md`, the segment `voiceover` fields
 * and the provider script described another, so the last scene showed a card
 * whose sentences the narrator never read. Text that is only ever copied by hand
 * drifts; each claim below is measured against the provider's own word
 * alignment, which is the only record of what was actually said.
 *
 * Checks:
 *   1. the take, the rendered track and the alignment all exist
 *   2. durations agree: the track file, the module's `length_s`, audio_meta and
 *      the take, and the film's segment spans sum to the file
 *   3. the alignment sits inside the audio: no clipped onset, and the tail after
 *      the last spoken character is neither absent nor long
 *   4. section_starts.json marks the paragraph starts the alignment has
 *   5. every segment's declared text is the paragraph that was recorded
 *   6. the provider script is that same text
 *   7. the rendered track's loudness matches the level audio_plan.md records
 *
 * Usage: node scripts/check-audio.mjs
 */

import { readFileSync, existsSync } from 'node:fs';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT = resolve(HERE, '..');
const VIDEO = join(PROJECT, 'videos', 'sovra_demo');
const TAKE = join(VIDEO, 'audio', 'originals', 'voiceovers', 'alice-uk-v1');
const TRACK = join(VIDEO, 'audio', 'tracks', 'v1', 'track.mp3');

const problems = [];

function read(path) {
	return readFileSync(path, 'utf8');
}

function note(ok, message) {
	if (ok) {
		console.log(`[audio] ok    ${message}`);
	} else {
		console.log(`[audio] FAIL  ${message}`);
		problems.push(message);
	}
}

function duration(file) {
	const out = execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'json', file]);
	return JSON.parse(out.toString()).format.duration;
}

/** Collapse whitespace and case so wrapped Markdown can be compared to a field. */
function normalize(text) {
	return text.replace(/\s+/g, ' ').trim().toLowerCase();
}

function firstDivergence(a, b) {
	let at = 0;
	while (at < Math.min(a.length, b.length) && a[at] === b[at]) at += 1;
	return `at char ${at}: recorded "${b.slice(Math.max(0, at - 30), at + 50)}" vs declared "${a.slice(Math.max(0, at - 30), at + 50)}"`;
}

function main() {
	for (const file of [join(TAKE, 'audio.mp3'), TRACK, join(TAKE, 'timing.json'), join(TAKE, 'audio_meta.json')]) {
		if (!existsSync(file)) {
			console.error(`[audio] FAIL  missing ${file}`);
			process.exit(1);
		}
	}
	const meta = JSON.parse(read(join(TAKE, 'audio_meta.json')));
	const timing = JSON.parse(read(join(TAKE, 'timing.json')));
	const track = read(join(VIDEO, 'audio', 'tracks', 'v1', 'track.ts'));

	const takeSeconds = Number(duration(join(TAKE, 'audio.mp3')));
	const trackSeconds = Number(duration(TRACK));
	const lengthS = Number(track.match(/length_s:\s*([0-9.]+)/)[1]);
	const spans = [...track.matchAll(/'([^']+)':\s*\[([^\]]+)\]/g)].map(([, id, list]) => ({
		id,
		values: list.split(',').map((value) => Number(value.trim())),
	}));
	const filmSeconds = spans.reduce((sum, span) => sum + span.values.at(-1), 0);

	note(Math.abs(trackSeconds - lengthS) < 0.05, `track file ${trackSeconds.toFixed(3)} s matches length_s ${lengthS}`);
	note(Math.abs(takeSeconds - meta.audio_seconds) < 0.15, `take ${takeSeconds.toFixed(3)} s matches audio_meta ${meta.audio_seconds} s`);
	note(Math.abs(filmSeconds - trackSeconds) < 0.05, `segment spans sum to ${filmSeconds.toFixed(3)} s, the track is ${trackSeconds.toFixed(3)} s`);

	// The alignment is the record of what was said, so it has to sit inside the audio.
	const text = timing.characters.join('');
	const starts = timing.character_start_times_seconds;
	const ends = timing.character_end_times_seconds;
	note(text.length === meta.characters_billed, `alignment covers ${text.length} characters, audio_meta bills ${meta.characters_billed}`);
	note(starts[0] <= 0.3, `narration starts at ${starts[0].toFixed(3)} s (no clipped onset)`);
	const lastEnd = ends[ends.length - 1];
	const tail = trackSeconds - lastEnd;
	note(tail >= 0.02 && tail <= 1.0, `the take keeps ${tail.toFixed(3)} s of tail after the last spoken character`);

	// Paragraph starts: what the segment spans were derived from.
	const paragraphs = text.split('\n\n');
	const sections = JSON.parse(read(join(TAKE, 'section_starts.json')));
	let cursor = 0;
	const boundaries = paragraphs.map((paragraph) => {
		const from = cursor;
		cursor += paragraph.length + 2;
		return { from, seconds: starts[from] };
	});
	for (const [index, boundary] of boundaries.entries()) {
		const id = spans[index]?.id;
		const section = sections[id];
		if (!section) {
			note(false, `section_starts.json has no entry for ${id}`);
			continue;
		}
		const okStart = Math.abs(section.start_seconds - boundary.seconds) < 0.01 && section.char_start === boundary.from;
		note(okStart, `section_starts.json ${id} marks character ${section.char_start} at ${section.start_seconds} s (alignment: ${boundary.from} at ${boundary.seconds.toFixed(3)} s)`);
	}

	// Declared narration vs the paragraph that was recorded.
	const ids = spans.map((span) => span.id);
	ids.forEach((id, index) => {
		const source = read(join(PROJECT, 'segments', id, 'index.ts'));
		const field = source.match(/voiceover:\s*\n?\s*'((?:[^'\\]|\\.)*)'/s)?.[1].replace(/\\'/g, "'");
		if (field === undefined) {
			note(false, `${id} has no voiceover field`);
			return;
		}
		const recorded = paragraphs[index];
		note(normalize(field) === normalize(recorded), `${id} declares the recorded paragraph${normalize(field) === normalize(recorded) ? '' : ` (${firstDivergence(normalize(field), normalize(recorded))})`}`);
	});

	// The provider script is the input record for the take, so it is the same text.
	// Headings and blockquote notes carry provenance, not narration.
	const provider = read(join(TAKE, 'provider_script.md'));
	const body = provider
		.split('\n')
		.filter((line) => !/^\s*(#|>)/.test(line))
		.join('\n');
	note(normalize(body) === normalize(text), `provider_script.md is the recorded text${normalize(body) === normalize(text) ? '' : ` (${firstDivergence(normalize(body), normalize(text))})`}`);

	// Loudness, measured: the plan records the level the mix command targets.
	const plan = read(join(VIDEO, 'audio', 'audio_plan.md'));
	const target = Number(plan.match(/loudnorm=I=(-?[0-9.]+)/)?.[1]);
	const measured = spawnSync(
		'ffmpeg',
		['-hide_banner', '-i', TRACK, '-af', `loudnorm=I=${target}:TP=-1.5:LRA=11:print_format=json`, '-f', 'null', '-'],
		{ encoding: 'utf8' },
	);
	// The filter's JSON report is the last brace block ffmpeg writes to stderr.
	const block = (measured.stderr.match(/\{[^{}]*\}/g) ?? []).pop();
	if (!block) {
		note(false, 'could not read a loudness measurement out of ffmpeg');
		process.exit(1);
	}
	const integrated = Number(JSON.parse(block).input_i);
	note(Math.abs(integrated - target) <= 2, `measured loudness ${integrated} LUFS against the plan's ${target} LUFS`);

	if (problems.length > 0) {
		console.error(`[audio] FAIL: ${problems.length} problem(s)`);
		process.exit(1);
	}
	console.log('[audio] PASS: the declared narration, the provider script and the recorded take agree');
}

main();
