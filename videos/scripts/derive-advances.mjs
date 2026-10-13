#!/usr/bin/env node
/**
 * Derive every segment's advance times from the recorded narration alignment.
 *
 * Why this exists
 * ---------------
 * The renderer takes a segment's `advances` as one array and uses it twice: the
 * entries before the last are the moments a scene reveals its next beat, and the
 * LAST entry is the whole segment's duration. A scene with N `waitForNext()`
 * calls therefore needs exactly N + 1 entries — one per reveal, plus the span.
 *
 * When that arithmetic is maintained by hand, one short array is invisible: the
 * render still succeeds, the scene still shows, and the reveal that had no entry
 * is simply never drawn. That is what happened to `sovra-finding`, whose verdict
 * panel was authored but never appeared.
 *
 * So the numbers are computed here instead: the sentences of each segment's
 * recorded paragraph come from the provider's own word alignment, the beat
 * mapping says which sentence opens which reveal, and the span is the distance
 * to the next segment's first word. `--check` fails when the committed timing
 * files disagree with what this produces, which is what makes a re-record a
 * one-command regeneration rather than a manual re-timing.
 *
 * Usage:
 *   node scripts/derive-advances.mjs            # print the table and the check
 *   node scripts/derive-advances.mjs --write    # rewrite track.ts + voiceover.ts
 *   node scripts/derive-advances.mjs --check    # exit non-zero if they differ
 */

import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT = resolve(HERE, '..');
const VIDEO = join(PROJECT, 'videos', 'sovra_demo');

/** Sentence ordinals, per segment, that open each reveal — 0-based, in order. */
const BEAT_MAP_FILE = join(VIDEO, 'beat_map.json');

/**
 * Smallest advance the renderer accepts.
 *
 * A scene whose first reveal belongs on the narration's first word derives a
 * beat of 0 s, and the renderer refuses it: `validateTiming` requires every
 * advance to be a positive finite number, so a render fails outright rather
 * than drawing the reveal. Beats are therefore held at 50 ms — three frames at
 * 60 fps, the same instant to any viewer — and each later beat stays at least
 * this far past the one before it.
 */
const MIN_BEAT = 0.05;

/**
 * Earliest a segment's first reveal may appear.
 *
 * A scene arrives on a crossfade, and the 400 ms fade is still running when a
 * beat fires at the start of the segment: the render driver then reads the
 * active segment, finds the outgoing one still current, and aborts the whole
 * render with "Segment \"sovra-corpus\" transitioned at advance index 0 but
 * advances array has more entries". Holding the first reveal until the fade is
 * over — 0.5 s, the 400 ms fade plus a 100 ms margin — keeps the picture a
 * fraction of a screenshot behind the voice and lets the render finish.
 */
const MIN_FIRST_BEAT = 0.5;

function read(path) {
	return readFileSync(path, 'utf8');
}

function fail(message) {
	console.error(`[derive] FAIL: ${message}`);
	process.exit(1);
}

/** Segment ids in timeline order, read from the timeline itself. */
function segmentOrder() {
	const source = read(join(VIDEO, 'timeline.ts'));
	const ids = [...source.matchAll(/\{\s*id:\s*'([^']+)'/g)].map((m) => m[1]);
	if (ids.length === 0) fail('no segments found in timeline.ts');
	return ids;
}

/** One segment's declared voiceover text and how many reveals it waits for. */
function segmentSpec(id) {
	const source = read(join(PROJECT, 'segments', id, 'index.ts'));
	const voiceover = source.match(/voiceover:\s*\n?\s*'((?:[^'\\]|\\.)*)'/s);
	if (!voiceover) fail(`segment "${id}" has no voiceover text`);
	// Every reveal in a scene is one `await ctx.waitForNext()`.
	const waits = [...source.matchAll(/await\s+ctx\.waitForNext\(\)/g)].length;
	if (waits === 0) fail(`segment "${id}" never calls waitForNext()`);
	return { voiceover: voiceover[1].replace(/\\'/g, "'"), waits };
}

/** The recorded take: one alignment file, and the paragraph text it read. */
function alignment() {
	const root = join(VIDEO, 'audio', 'originals', 'voiceovers');
	const takes = existsSync(root)
		? readdirSync(root).filter((name) => existsSync(join(root, name, 'timing.json')))
		: [];
	if (takes.length !== 1) {
		fail(`expected exactly one recorded take under ${root}, found ${takes.length}`);
	}
	const timing = JSON.parse(read(join(root, takes[0], 'timing.json')));
	const text = timing.characters.join('');
	const paragraphs = text.split('\n\n');
	const starts = timing.character_start_times_seconds;
	const ends = timing.character_end_times_seconds;
	if (starts.length !== text.length || ends.length !== text.length) {
		fail('the alignment arrays do not line up with the character list');
	}
	// Character index at which each paragraph begins.
	let cursor = 0;
	const paragraphSpan = paragraphs.map((paragraph) => {
		const from = cursor;
		cursor += paragraph.length + 2; // the "\n\n" separator
		return { from, to: from + paragraph.length - 1 };
	});
	return { take: takes[0], text, paragraphs, starts, ends, paragraphSpan, fileEnd: ends[ends.length - 1] };
}

/** Sentence spans inside one paragraph: text, first character, last character. */
function sentences(paragraph) {
	const out = [];
	const pattern = /[^.!?]+[.!?]+(?:\s|$)/g;
	let match;
	while ((match = pattern.exec(paragraph)) !== null) {
		out.push({ text: match[0].trim(), from: match.index, to: match.index + match[0].trim().length - 1 });
	}
	if (out.length === 0) out.push({ text: paragraph.trim(), from: 0, to: paragraph.trim().length - 1 });
	return out;
}

function round(value, places = 3) {
	return Number(value.toFixed(places));
}

function derive() {
	const order = segmentOrder();
	const align = alignment();
	if (align.paragraphs.length !== order.length) {
		fail(
			`the recorded take has ${align.paragraphs.length} paragraph(s) but the timeline has ` +
				`${order.length} segment(s); the narration and the scene list disagree`,
		);
	}
	const beatMap = JSON.parse(read(BEAT_MAP_FILE));
	// The film ends exactly with the audio file, so the final span runs to the
	// track's own length rather than to the last character's end time.
	const trackLength = Number(read(join(VIDEO, 'audio', 'tracks', 'v1', 'track.ts')).match(/length_s:\s*([0-9.]+)/)?.[1]);
	if (!Number.isFinite(trackLength)) fail('could not read length_s from track.ts');

	const segments = order.map((id, index) => {
		const spec = segmentSpec(id);
		const paragraph = align.paragraphs[index];
		const span = align.paragraphSpan[index];
		const spanStart = align.starts[span.from];
		const spanEnd = index + 1 < order.length ? align.starts[align.paragraphSpan[index + 1].from] : align.fileEnd;
		const parts = sentences(paragraph);

		const beats = beatMap[id];
		if (!Array.isArray(beats)) fail(`beat_map.json has no entry for "${id}"`);
		if (beats.length !== spec.waits) {
			fail(
				`segment "${id}" waits for ${spec.waits} reveal(s) but beat_map.json lists ${beats.length}; ` +
					`the array needs ${spec.waits + 1} entries (one per reveal, plus the span)`,
			);
		}
		for (const beat of beats) {
			if (!Number.isInteger(beat) || beat < 0 || beat >= parts.length) {
				fail(`segment "${id}" beat ${beat} is outside its ${parts.length} sentence(s)`);
			}
		}

		// Sentence speaking time, shared evenly when several beats cite one sentence.
		const citations = new Map();
		for (const beat of beats) citations.set(beat, (citations.get(beat) ?? 0) + 1);
		const used = new Map();
		const advances = beats.map((beat) => {
			const part = parts[beat];
			const share = used.get(beat) ?? 0;
			used.set(beat, share + 1);
			const from = align.starts[span.from + part.from];
			const to = align.ends[span.from + part.to] ?? from;
			return round(from + ((to - from) * share) / citations.get(beat) - spanStart);
		});
		advances.push(round((index + 1 < order.length ? spanEnd : trackLength) - spanStart));
		for (let i = 0; i < advances.length - 1; i += 1) {
			// The first scene has no incoming transition to wait for.
			const floor = i === 0 ? (index === 0 ? MIN_BEAT : MIN_FIRST_BEAT) : advances[i - 1] + MIN_BEAT;
			advances[i] = round(Math.max(advances[i], floor));
		}
		if (advances[0] < MIN_FIRST_BEAT && index > 0) {
			fail(`segment "${id}" would reveal its first beat at ${advances[0]} s, inside the incoming transition`);
		}
		for (const [i, value] of advances.entries()) {
			if (!Number.isFinite(value) || value <= 0) {
				fail(`segment "${id}" derived advances[${i}] = ${value}; the renderer rejects non-positive advances`);
			}
		}
		for (let i = 1; i < advances.length; i += 1) {
			if (advances[i] <= advances[i - 1]) {
				fail(`segment "${id}" derived non-increasing advances: ${advances.join(', ')}`);
			}
		}
		if (advances.length !== spec.waits + 1) {
			fail(`segment "${id}" derived ${advances.length} advances for ${spec.waits} reveal(s)`);
		}

		return {
			id,
			waits: spec.waits,
			span: [round(spanStart), round(spanEnd)],
			spanEndSeconds: round(index + 1 < order.length ? spanEnd : trackLength),
			sentences: parts.length,
			beats,
			advances,
			paragraph: paragraph.trim(),
			field: spec.voiceover,
			words: paragraph.trim().split(/\s+/).length,
			reveals: beats.map((beat) => `${parts[beat].text.slice(0, 58)}…`),
		};
	});

	const total = round(segments.reduce((sum, segment) => sum + segment.advances.at(-1), 0));
	return { align, segments, total, take: align.take };
}

function formatBlock(segments, indent) {
	return segments
		.map((segment) => `${indent}'${segment.id}': [${segment.advances.join(', ')}],`)
		.join('\n');
}

function expectedTrack(segments) {
	return `\t\tperSegment: {\n${formatBlock(segments, '\t\t\t')}\n\t\t},`;
}

function expectedVoiceover(segments) {
	return `\t\tperSegment: {\n${formatBlock(segments, '\t\t\t')}\n\t\t},`;
}

function replacePerSegment(source, block) {
	const pattern = /\t\tperSegment: \{[\s\S]*?\n\t\t\},/;
	if (!pattern.test(source)) fail('could not find the perSegment block to replace');
	return source.replace(pattern, block);
}

/**
 * The voiceover script as Markdown, for docs and for review against the audio.
 *
 * The vendor `videowright script` command cannot assemble this project's script:
 * it imports every segment module in Node, and the shared scene frame defines a
 * custom element at module scope, so the import dies on `HTMLElement is not
 * defined`. The sections below therefore come from the recorded take itself —
 * each section is the paragraph the provider was given and read, with the span
 * the film gives it — and the timing check fails when the narration and the
 * declared text drift apart.
 */
function assembleScript(segments, take, align) {
	const words = segments.reduce((sum, segment) => sum + segment.words, 0);
	const seconds = segments.reduce((sum, segment) => sum + segment.advances.at(-1), 0);
	const pace = (words / seconds).toFixed(2);
	const wrap = (text) => {
		const lines = [];
		let line = '';
		for (const word of text.split(' ')) {
			if (`${line} ${word}`.trim().length > 76) {
				lines.push(line);
				line = word;
			} else {
				line = line ? `${line} ${word}` : word;
			}
		}
		if (line) lines.push(line);
		return lines.join('\n');
	};
	const rows = segments
		.map((segment) => `| ${segment.id} | ${segment.words} | ${segment.advances.at(-1).toFixed(2)} s |`)
		.join('\n');
	const sections = segments
		.map((segment) => `## ${segment.id}\n\n${wrap(segment.paragraph)}`)
		.join('\n\n');
	return `# Voiceover script — Sovra Verify two-minute demo

This is the narration as recorded, in the order the film plays it. Each section
is one paragraph of the provider input; the table's spans are the segment
lengths derived from the provider's word alignment, so each section ends exactly
where the next paragraph's first word begins. Assembled by
\`scripts/derive-advances.mjs\`; \`--check\` fails when this file, the segment
\`voiceover\` fields and the recorded take stop agreeing.

Narration pace: measured at ${pace} words per second over the recorded take
(${take}, ElevenLabs \`eleven_multilingual_v2\`). The first generation ran 138 s
and was cut to fit the official two-minute demonstration limit.

| Segment | Words | Recorded span |
|---|---|---|
${rows}
| **Total** | **${words}** | **${seconds.toFixed(2)} s** |

${sections}
`;
}

/**
 * The provider script: the exact text a text-to-speech take is generated from,
 * one paragraph per scene, in reading order.
 *
 * It is kept separate from script.md because the two are allowed to differ in
 * spelling — a provider may be given `one point five 70 billion` where the
 * spoken script writes `1.5 70B` — but not in wording. Generating it here is
 * what stops the two from describing different takes, which is how the film
 * ended up playing one script while its paper trail described another.
 */
function assembleProviderScript(segments, take) {
	const meta = JSON.parse(read(join(VIDEO, 'audio', 'originals', 'voiceovers', take, 'audio_meta.json')));
	const wrap = (text) => {
		const lines = [];
		let line = '';
		for (const word of text.split(' ')) {
			if (`${line} ${word}`.trim().length > 76) {
				lines.push(line);
				line = word;
			} else {
				line = line ? `${line} ${word}` : word;
			}
		}
		if (line) lines.push(line);
		return lines.join('\n');
	};
	const body = segments
		.map((segment) => wrap(segment.field ?? segment.paragraph))
		.join('\n\n');
	return `# Provider script — take ${take}

> Sent to ${meta.provider}, model \`${meta.model_id}\`, voice "${meta.voice_name}".
> One paragraph per scene, in reading order; prosody comes from punctuation only and no
> model tags are used. This file is the input record for the take, so it is the same
> wording as each scene's \`voiceover\` field and as \`voiceover_script/script.md\`.
> \`node scripts/derive-advances.mjs --check\` fails when either drifts.

${body}
`;
}

/**
 * The rendered-timing table in PLAN.md.
 *
 * It is the table a reader uses to see where the picture is against the voice,
 * and it was hand-copied from the timing files once — which is how it came to
 * describe a schedule the film no longer used. Generating it keeps the document
 * and the artifact from diverging again.
 */
function assemblePlanTable(segments, total) {
	const rows = segments
		.map(
			(segment) =>
				`| ${segment.id} | [${segment.advances.join(', ')}] | ` +
				`${segment.span[0].toFixed(2)} – ${segment.spanEndSeconds.toFixed(2)} s |`,
		)
		.join('\n');
	return `| Segment | Rendered advances | Narration span |\n|---|---|---|\n${rows}\n| **Total** | | **${total.toFixed(3)} s** |`;
}

const PLAN_TABLE = /\| Segment \| Rendered advances \| Narration span \|\n\|---\|---\|---\|\n(?:\|[^\n]*\n?)+/;

function replacePlanTable(source, block) {
	if (!PLAN_TABLE.test(source)) fail('could not find the rendered-timing table in PLAN.md');
	return source.replace(PLAN_TABLE, `${block}\n`);
}

function main() {
	const write = process.argv.includes('--write');
	const check = process.argv.includes('--check') || write;
	const { segments, total, take, align } = derive();

	console.log(`[derive] take: ${take} — ${align.text.length} chars, ${total.toFixed(3)} s`);
	console.log(
		`[derive] ${'segment'.padEnd(22)} ${'waits'.padStart(5)} ${'sent'.padStart(5)}  span (s)          advances (s)`,
	);
	for (const segment of segments) {
		console.log(
			`[derive] ${segment.id.padEnd(22)} ${String(segment.waits).padStart(5)} ` +
				`${String(segment.sentences).padStart(5)}  ${segment.span[0].toFixed(2)}–${segment.span[1].toFixed(2)}`.padEnd(73) +
				` ${segment.advances.join(', ')}`,
		);
	}
	console.log(`[derive] ${segments.length} segment(s), ${total.toFixed(3)} s of picture`);

	const targets = [
		{
			path: join(VIDEO, 'audio', 'tracks', 'v1', 'track.ts'),
			replace: (source) => replacePerSegment(source, expectedTrack(segments)),
		},
		{
			path: join(VIDEO, 'audio', 'originals', 'voiceovers', take, 'voiceover.ts'),
			replace: (source) => replacePerSegment(source, expectedVoiceover(segments)),
		},
		{
			path: join(VIDEO, 'voiceover_script', 'script.md'),
			replace: () => assembleScript(segments, take, align),
		},
		{
			path: join(VIDEO, 'audio', 'originals', 'voiceovers', take, 'provider_script.md'),
			replace: () => assembleProviderScript(segments, take),
		},
		{
			path: join(VIDEO, 'PLAN.md'),
			replace: (source) => replacePlanTable(source, assemblePlanTable(segments, total)),
		},
	];
	const stale = targets.filter((target) => target.replace(read(target.path)) !== read(target.path));

	if (write) {
		for (const target of stale) writeFileSync(target.path, target.replace(read(target.path)));
		console.log(`[derive] wrote ${stale.length} file(s): ${stale.map((t) => t.path.split('/').pop()).join(', ')}`);
		return;
	}
	if (!check) return;

	for (const target of stale) {
		const before = read(target.path).split('\n');
		const after = target.replace(read(target.path)).split('\n');
		const at = before.findIndex((line, index) => line !== after[index]);
		console.error(
			`[derive] ${target.path} is stale at line ${at + 1}:\n` +
				`  committed: ${JSON.stringify(before[at])}\n` +
				`  derived:   ${JSON.stringify(after[at])}`,
		);
	}
	if (stale.length > 0) {
		fail(`${stale.length} file(s) disagree with the recorded narration; run with --write`);
	}
	console.log('[derive] PASS: advance times and script agree with the recorded narration');
}

main();
