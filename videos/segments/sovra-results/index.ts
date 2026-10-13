import { defineSegment } from 'videowright';
import { mountSceneFrame, settle } from '../../components/scene-frame/index';

let host: HTMLElement | null = null;

const FIGURES = [
	{ value: '4', label: 'documents' },
	{ value: '25', label: 'claims' },
	{ value: '10', label: 'pairs compared' },
	{ value: '13', label: 'calls' },
	{ value: '0', label: 'failed calls' },
	{ value: '15,650', label: 'tokens' },
	{ value: '71.5 s', label: 'provider latency' },
	{ value: '100%', label: 'displayed citations resolved' },
];

function figure(item: (typeof FIGURES)[number]): string {
	return `
    <div data-ref="figure" style="opacity:0;">
      <div style="font-family:var(--font-display); font-size:76px; line-height:0.95;">${item.value}</div>
      <div style="font-family:var(--font-mono); font-size:15px; letter-spacing:0.12em; text-transform:uppercase; color:var(--color-muted); margin-top:16px;">${item.label}</div>
    </div>
  `;
}

/**
 * Scene 7 — measured results and the deployment limit. This is the last scene:
 * it ends on the limitation itself, with no closing card, logo or sign-off.
 */
export default defineSegment({
	id: 'sovra-results',
	advances: [6.0, 14.0, 20.0],
	voiceover:
		'On four documents, every displayed citation resolved to an exact slice of canonical text. CSCS hosted inference is external network inference. A local application calling CSCS is not air gapped, and Swiss inference residency does not establish residency of the whole application. These figures are one run over four synthetic documents, not a general accuracy claim.',
	notes: 'Final scene. Ends on substantive limitation content: no closing card, no sign-off, no branding strip.',

	mount(el) {
		host = el;
		const frame = mountSceneFrame(el, 'Measured / one run, four documents');
		frame.setContent(`
      <div style="position:absolute; left:var(--safe-x); right:var(--safe-x); top:180px;">
        <div data-ref="headline" style="font-family:var(--font-display); font-size:72px; line-height:1.0; opacity:0;">
          What was measured, and <span style="font-style:italic;">what it is not</span>.
        </div>

        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:40px 56px; margin-top:64px;">
          ${FIGURES.map(figure).join('')}
        </div>

        <div data-ref="limit" style="
          margin-top:64px;
          border:var(--rule-weight) solid var(--color-border);
          background:var(--color-surface);
          padding:36px 44px;
          opacity:0;
        ">
          <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Deployment reality</div>
          <div style="font-family:var(--font-body); font-size:34px; line-height:1.45; margin-top:24px; max-width:1500px;">
            CSCS-hosted inference is external-network inference. A local application calling CSCS is <strong>not air-gapped</strong>, and Swiss inference residency does not establish residency of the whole application. These figures are one run over four synthetic documents, not a general accuracy claim.
          </div>
        </div>
      </div>
    `);
	},

	async play(ctx) {
		const frame = host?.querySelector('scene-frame') as HTMLElement | null;
		const headline = host?.querySelector('[data-ref="headline"]') as HTMLElement | null;
		const figures = Array.from(host?.querySelectorAll('[data-ref="figure"]') ?? []) as HTMLElement[];
		const limit = host?.querySelector('[data-ref="limit"]') as HTMLElement | null;

		(frame as { reveal?: () => void } | null)?.reveal?.();
		settle(headline, 0);

		await ctx.waitForNext();

		figures.forEach((item, index) => settle(item, index * 90));

		// The limitation owns a beat of its own: it is the last thing the film
		// says, and before this it appeared two seconds in — while the narration
		// was still reading out the figures and had not yet named CSCS at all.
		await ctx.waitForNext();

		settle(limit, 0);

		await ctx.hold(7000);
	},

	unmount() {
		host = null;
	},
});
