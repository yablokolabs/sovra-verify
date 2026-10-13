import { defineSegment } from 'videowright';
import { mountSceneFrame, settle } from '../../components/scene-frame/index';

let host: HTMLElement | null = null;

const STATS = [
	{ value: '4', label: 'documents' },
	{ value: '25', label: 'claims identified' },
	{ value: '10', label: 'candidate pairs compared' },
	{ value: '13', label: 'provider calls' },
];

function stat(item: (typeof STATS)[number]): string {
	return `
    <div data-ref="stat" style="opacity:0;">
      <div style="font-family:var(--font-display); font-size:132px; line-height:0.9;">${item.value}</div>
      <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted); margin-top:20px;">${item.label}</div>
    </div>
  `;
}

/**
 * Scene 3 — the real run. Measured only: model, provider, call count, token
 * usage and latency come from the recorded provider runs of one analysis.
 */
export default defineSegment({
	id: 'sovra-run',
	advances: [5.0, 11.0, 20.0],
	voiceover:
		'Apertus 1.5 70B, hosted on CSCS, reads the passages and nominates typed claims: 25 claims found, 10 candidate pairs compared, 13 provider calls, none failed.',
	notes: 'Provider run metadata. Every number is measured, none estimated.',

	mount(el) {
		host = el;
		const frame = mountSceneFrame(el, 'Analysis / real CSCS inference');
		frame.setContent(`
      <div style="position:absolute; left:var(--safe-x); right:var(--safe-x); top:180px;">
        <div data-ref="headline" style="font-family:var(--font-display); font-size:76px; line-height:1.0; opacity:0;">
          Apertus reads the corpus, <span style="font-style:italic;">then we check it</span>.
        </div>

        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:48px; margin-top:96px;">
          ${STATS.map(stat).join('')}
        </div>

        <div data-ref="meta" style="
          margin-top:104px;
          border-top:var(--rule-weight) solid var(--color-border);
          padding-top:40px;
          display:grid;
          grid-template-columns:repeat(3, 1fr);
          gap:48px;
          opacity:0;
        ">
          <div>
            <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Primary provider</div>
            <div style="font-family:var(--font-mono); font-size:28px; margin-top:16px;">CSCS</div>
            <div style="font-family:var(--font-mono); font-size:22px; color:var(--color-muted); margin-top:8px;">api.inference.cscs.ch/v1</div>
          </div>
          <div>
            <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Model</div>
            <div style="font-family:var(--font-mono); font-size:28px; margin-top:16px;">swiss-ai/Apertus-v1.5-70B</div>
            <div style="font-family:var(--font-mono); font-size:22px; color:var(--color-muted); margin-top:8px;">8B selectable, never automatic</div>
          </div>
          <div>
            <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Recorded usage</div>
            <div style="font-family:var(--font-mono); font-size:28px; margin-top:16px;">15,650 tokens &middot; 0 failed</div>
            <div style="font-family:var(--font-mono); font-size:22px; color:var(--color-muted); margin-top:8px;">11,168 in &middot; 4,482 out</div>
            <div style="font-family:var(--font-mono); font-size:22px; color:var(--color-muted); margin-top:8px;">71.5 s of provider latency</div>
          </div>
        </div>
      </div>
    `);
	},

	async play(ctx) {
		const frame = host?.querySelector('scene-frame') as HTMLElement | null;
		const headline = host?.querySelector('[data-ref="headline"]') as HTMLElement | null;
		const stats = Array.from(host?.querySelectorAll('[data-ref="stat"]') ?? []) as HTMLElement[];
		const meta = host?.querySelector('[data-ref="meta"]') as HTMLElement | null;

		(frame as { reveal?: () => void } | null)?.reveal?.();
		settle(headline, 0);

		await ctx.waitForNext();

		stats.forEach((item, index) => settle(item, index * 120));

		await ctx.waitForNext();

		settle(meta, 0);

		await ctx.hold(9000);
	},

	unmount() {
		host = null;
	},
});
