import { defineSegment } from 'videowright';
import { mountSceneFrame, settle } from '../../components/scene-frame/index';
// The mark is imported, not referenced by URL. The render and dev servers serve
// the videowright entry from the package root, so a root-absolute path into this
// project (e.g. /brand/sovra-logo.png) resolves against the package and 404s.
// Importing it lets Vite serve the project file itself.
import logoUrl from '../../assets/brand/sovra-logo.png';

let host: HTMLElement | null = null;

/**
 * Scene 1 — the problem. Opens on the product mark, then states why an answer
 * without a source is not evidence. The logo appears here and nowhere else.
 */
export default defineSegment({
	id: 'sovra-problem',
	advances: [7.5, 15.0],
	voiceover:
		'Procurement teams compare a supplier agreement, a payment policy and an invoice by hand. A language model answer that cannot show where it came from is not usable evidence. Sovra Verify audits the corpus and returns the exact passages.',
	notes: 'Title card plus problem statement. Logo mark appears once, at the start.',

	mount(el) {
		host = el;
		const frame = mountSceneFrame(el, 'Two minute demo');
		frame.setContent(`
      <div style="position:absolute; left:var(--safe-x); right:var(--safe-x); top:200px;">

        <div data-ref="mark" style="display:flex; align-items:center; gap:40px; opacity:0;">
          <img
            src="${logoUrl}"
            alt="Sovra Verify"
            style="height:112px; width:auto; display:block;"
          />
          <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.16em; text-transform:uppercase; color:var(--color-muted);">
            Cross-document<br />consistency auditor
          </div>
        </div>

        <div data-ref="headline" style="
          font-family:var(--font-display);
          font-size:140px;
          line-height:0.96;
          letter-spacing:-0.01em;
          margin-top:72px;
          opacity:0;
        ">Don't just answer.<br /><span style="font-style:italic;">Prove it</span><span style="color:var(--color-accent);">.</span></div>

        <div data-ref="statement" style="
          font-family:var(--font-body);
          font-size:38px;
          line-height:1.45;
          font-weight:400;
          max-width:1420px;
          margin-top:80px;
          opacity:0;
        ">Procurement teams compare a supplier agreement, a payment policy and an invoice by hand. A model answer that cannot show <em style="font-family:var(--font-display); font-style:italic;">where it came from</em> is not usable evidence.</div>
      </div>
    `);
	},

	async play(ctx) {
		const mark = host?.querySelector('[data-ref="mark"]') as HTMLElement | null;
		const headline = host?.querySelector('[data-ref="headline"]') as HTMLElement | null;
		const statement = host?.querySelector('[data-ref="statement"]') as HTMLElement | null;
		const frame = host?.querySelector('scene-frame') as HTMLElement | null;

		(frame as { reveal?: () => void } | null)?.reveal?.();
		settle(mark, 0);
		settle(headline, 180);

		await ctx.waitForNext();

		settle(statement, 0);

		// Holds to the 15.0s advance so the scene ends when the narration does.
		await ctx.hold(7500);
	},

	unmount() {
		host = null;
	},
});
