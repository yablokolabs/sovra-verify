#!/usr/bin/env node
/**
 * Measure every scene, at every beat, inside the real player.
 *
 * Two things this can catch that reading the source cannot:
 *
 * 1. Overflow. The scenes are absolutely positioned blocks on a fixed
 *    1920x1080 page, so content that is taller than the space it has is simply
 *    cut — the bottom of the page is not scrollable and the export does not
 *    warn. `sovra-negative` lost its last sentence this way.
 * 2. Missing fonts. If the brand faces do not load, the browser substitutes
 *    fallbacks with wider metrics, which both changes the layout and makes the
 *    overflow worse. The font assertions below are what proved the fonts were
 *    never loaded at all.
 *
 * The check drives the project's own dev player through `#/<segment>/<beat>`
 * deep links (the format the player's hash router documents), so it measures
 * the scenes as the render mounts them, not a copy.
 *
 * Usage: node scripts/check-frames.mjs [--port 5199] [--verbose]
 * Exit code 1 when any scene overflows the frame or a font is missing.
 */

import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT = resolve(HERE, '..');
const VIDEO = join(PROJECT, 'videos', 'sovra_demo');
const SLUG = 'sovra_demo';

/** The page the scenes are laid out on, and the rule the content must clear. */
const FRAME = { width: 1920, height: 1080, safeX: 128, safeY: 96 };

const args = process.argv.slice(2);
const portIndex = args.indexOf('--port');
const PORT = portIndex >= 0 ? Number(args[portIndex + 1]) : 5199;
const VERBOSE = args.includes('--verbose');

function read(path) {
	return readFileSync(path, 'utf8');
}

function fail(message) {
	console.error(`[frames] FAIL: ${message}`);
	process.exit(1);
}

/** Segment ids in order, and the reveal count each one has (advances minus span). */
function schedule() {
	const source = read(join(VIDEO, 'timeline.ts'));
	const ids = [...source.matchAll(/\{\s*id:\s*'([^']+)'/g)].map((m) => m[1]);
	if (ids.length === 0) fail('no segments found in timeline.ts');
	const track = read(join(VIDEO, 'audio', 'tracks', 'v1', 'track.ts'));
	const block = track.match(/perSegment:\s*\{([\s\S]*?)\n\t\t\},/)?.[1];
	if (!block) fail('no perSegment block in track.ts');
	const beats = new Map();
	for (const [, id, list] of block.matchAll(/'([^']+)':\s*\[([^\]]+)\]/g)) {
		const values = list.split(',').map((value) => Number(value.trim()));
		beats.set(id, values.length - 1); // the final entry is the span, not a reveal
	}
	return ids.map((id) => ({ id, reveals: beats.get(id) ?? 0 }));
}

/**
 * Start the dev server and return the address it actually bound to.
 *
 * The requested port is only a preference: videowright moves to the next free
 * port and prints the address it settled on, so the address is read back from
 * the server's own output rather than assumed.
 */
async function startDevServer(timeoutMs = 60000) {
	const child = spawn('npx', ['videowright', 'dev', '--port', String(PORT)], {
		cwd: PROJECT,
		stdio: ['ignore', 'pipe', 'pipe'],
		detached: true,
	});
	let log = '';
	child.stdout.on('data', (chunk) => {
		log += String(chunk);
	});
	child.stderr.on('data', (chunk) => {
		log += String(chunk);
	});
	// Kill the whole process group: npx spawns the server as a child of its own.
	process.on('exit', () => {
		try {
			process.kill(-child.pid, 'SIGTERM');
		} catch {
			// already gone
		}
	});
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		const match = log.match(/running at (http:\/\/localhost:\d+)\//);
		if (match) {
			const base = match[1];
			try {
				const response = await fetch(`${base}/video/${SLUG}`);
				if (response.ok) return { child, base, log: () => log };
			} catch {
				// still starting
			}
		}
		await new Promise((done) => setTimeout(done, 250));
	}
	throw new Error(`dev server did not come up\n${log}`);
}

/** Measure the scene body: every visible element's box, in unscaled page px. */
const measure = () => {
	const host = document.getElementById('player-host');
	if (!host) return { error: 'no #player-host' };
	const hostRect = host.getBoundingClientRect();
	const scale = hostRect.width / host.offsetWidth || 1;
	const frame = host.querySelector('scene-frame');
	const body = frame?.querySelector('[data-ref="body"]');
	if (!body) return { error: 'no scene body' };
	const items = [];
	for (const el of body.querySelectorAll('*')) {
		const style = getComputedStyle(el);
		if (style.display === 'none' || style.visibility === 'hidden') continue;
		const rect = el.getBoundingClientRect();
		if (rect.width === 0 && rect.height === 0) continue;
		// A parent at opacity 0 hides its children: only count what is shown.
		let shown = Number(style.opacity) > 0.01;
		for (let parent = el.parentElement; shown && parent && parent !== body; parent = parent.parentElement) {
			if (Number(getComputedStyle(parent).opacity) <= 0.01) shown = false;
		}
		if (!shown) continue;
		items.push({
			ref: el.getAttribute('data-ref') ?? el.tagName.toLowerCase(),
			top: (rect.top - hostRect.top) / scale,
			bottom: (rect.bottom - hostRect.top) / scale,
			left: (rect.left - hostRect.left) / scale,
			right: (rect.right - hostRect.left) / scale,
			opacity: Number(style.opacity),
		});
	}
	return { scale, items, host: { width: host.offsetWidth, height: host.offsetHeight } };
};

/**
 * Whether the brand faces are declared, and whether text actually uses them.
 *
 * `document.fonts.check()` cannot answer the second question: for a family the
 * document never declared, Chrome reports "loaded" because there is nothing to
 * load, which is why the first version of this check passed against a page with
 * no fonts at all. Measuring the same string in the brand family and in the
 * fallback family does answer it — equal widths mean the fallback was used.
 */
const fontState = () => {
	const families = {
		display: 'Instrument Serif',
		body: 'Geist Variable',
		mono: 'JetBrains Mono Variable',
	};
	const declared = [...document.fonts].map((face) => face.family.replace(/["']/g, ''));
	const canvas = document.createElement('canvas').getContext('2d');
	const width = (font) => {
		canvas.font = font;
		return canvas.measureText('Handgloves 1234567890 mmm iii www').width;
	};
	// A family nobody declares resolves to the browser's default font, so it is
	// the baseline every brand family must differ from.
	const baseline = width('72px "__sovra_check_absent__"');
	const result = {};
	for (const [name, family] of Object.entries(families)) {
		const brand = width(`72px "${family}"`);
		result[name] = {
			family,
			declared: declared.includes(family),
			brandWidth: Number(brand.toFixed(2)),
			fallbackWidth: Number(baseline.toFixed(2)),
			inUse: Math.abs(brand - baseline) > 0.5,
		};
	}
	return result;
};

async function main() {
	const { chromium } = await import('playwright');
	const scenes = schedule();
	const server = await startDevServer();
	const base = server.base;
	let browser;
	try {
		browser = await chromium.launch();
		const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
		page.on('pageerror', (error) => console.error(`[frames] page error: ${error.message}`));

		const failures = [];
		for (const scene of scenes) {
			for (let beat = 0; beat <= scene.reveals; beat += 1) {
				const url = `${base}/video/${SLUG}?hideHud=1#/${scene.id}/${beat}`;
				await page.goto(url, { waitUntil: 'load' });
				await page.waitForFunction('window.__VW_PLAYER_READY__ === true', { timeout: 30000 });
				await page.waitForFunction(
					`document.querySelector('#player-host scene-frame [data-ref="body"]') !== null`,
					{ timeout: 30000 },
				);
				// Let the entrance animations finish (the shared settle() is 480 ms).
				await page.waitForTimeout(900);
				const result = await page.evaluate(measure);
				if (result.error) fail(`${scene.id} beat ${beat}: ${result.error}`);
				await page.evaluate(() => document.fonts.ready);
				const fonts = await page.evaluate(fontState);
				const lowest = result.items.reduce((worst, item) => (item.bottom > worst.bottom ? item : worst), {
					bottom: -Infinity,
					ref: 'none',
				});
				const highest = result.items.reduce((worst, item) => (item.top < worst.top ? item : worst), {
					top: Infinity,
					ref: 'none',
				});
				const rightmost = result.items.reduce((worst, item) => (item.right > worst.right ? item : worst), {
					right: -Infinity,
					ref: 'none',
				});
				const bottomLimit = FRAME.height - FRAME.safeY;
				const overflow = lowest.bottom - bottomLimit;
				const rightOverflow = rightmost.right - (FRAME.width - FRAME.safeX);
				const topOverflow = FRAME.safeY - highest.top;
				const missing = Object.entries(fonts)
					.filter(([, face]) => !face.inUse)
					.map(([, face]) => `${face.family} (brand ${face.brandWidth}px vs fallback ${face.fallbackWidth}px)`);
				console.log(
					`[frames] ${scene.id.padEnd(22)} beat ${beat}/${scene.reveals}  ` +
						`content ${highest.top.toFixed(0)}–${lowest.bottom.toFixed(0)} px, right ${rightmost.right.toFixed(0)} px` +
						`  ${overflow > 0 ? `BOTTOM +${overflow.toFixed(0)} px (${lowest.ref})` : 'fits'}` +
						`${rightOverflow > 0 ? `  RIGHT +${rightOverflow.toFixed(0)} px (${rightmost.ref})` : ''}` +
						`${topOverflow > 0 ? `  TOP +${topOverflow.toFixed(0)} px (${highest.ref})` : ''}` +
						`${missing.length > 0 ? `  FONTS MISSING: ${missing.join(', ')}` : ''}`,
				);
				if (VERBOSE) {
					for (const item of result.items.filter((item) => item.bottom > bottomLimit)) {
						console.log(`           ${item.ref}: ${item.top.toFixed(0)}–${item.bottom.toFixed(0)} px`);
					}
				}
				if (overflow > 0) failures.push(`${scene.id} beat ${beat}: ${lowest.ref} reaches ${lowest.bottom.toFixed(0)} px, ${overflow.toFixed(0)} px past the bottom rule`);
				if (rightOverflow > 0) failures.push(`${scene.id} beat ${beat}: ${rightmost.ref} reaches ${rightmost.right.toFixed(0)} px, ${rightOverflow.toFixed(0)} px past the right rule`);
				if (topOverflow > 0) failures.push(`${scene.id} beat ${beat}: ${highest.ref} starts at ${highest.top.toFixed(0)} px, ${topOverflow.toFixed(0)} px above the top rule`);
				if (missing.length > 0) failures.push(`${scene.id} beat ${beat}: fonts not loaded: ${missing.join(', ')}`);
			}
		}
		if (failures.length > 0) {
			console.error(`[frames] ${failures.length} problem(s):`);
			for (const problem of [...new Set(failures)]) console.error(`  - ${problem}`);
			fail('scenes do not fit the frame, or the brand fonts are not loaded');
		}
		console.log(`[frames] PASS: ${scenes.length} scenes fit the frame with the brand fonts loaded`);
	} finally {
		await browser?.close();
		try {
			process.kill(-server.child.pid, 'SIGTERM');
		} catch {
			// already gone
		}
	}
}

main().catch((error) => fail(error.stack ?? String(error)));
