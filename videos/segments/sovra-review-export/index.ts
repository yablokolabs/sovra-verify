import { defineSegment } from 'videowright';
import { mountSceneFrame, settle } from '../../components/scene-frame/index';

let host: HTMLElement | null = null;

/**
 * Scene 6 — human review and export. Review states are review states, never a
 * legal resolution; export carries provenance for every quoted span.
 */
export default defineSegment({
	id: 'sovra-review-export',
	advances: [6.0, 14.0],
	voiceover:
		'A reviewer confirms or dismisses each finding, and the decision is recorded. Export carries the source hash, the page, the offsets, and the model.',
	notes: 'Review states and the export bundle. No legal resolution wording.',

	mount(el) {
		host = el;
		const frame = mountSceneFrame(el, 'Review / export');
		frame.setContent(`
      <div style="position:absolute; left:var(--safe-x); right:var(--safe-x); top:196px;">
        <div data-ref="review" style="opacity:0;">
          <div style="display:flex; align-items:baseline; gap:40px;">
            <div style="font-family:var(--font-display); font-size:72px; line-height:1.0;">A person still decides.</div>
            <div style="font-family:var(--font-mono); font-size:22px; color:var(--color-muted);">finding 06 &middot; pending</div>
          </div>

          <div style="display:flex; gap:28px; margin-top:64px;">
            <div style="font-family:var(--font-mono); font-size:24px; letter-spacing:0.08em; padding:20px 36px; border:var(--rule-weight) solid var(--color-fg);">confirmed for review</div>
            <div style="font-family:var(--font-mono); font-size:24px; letter-spacing:0.08em; padding:20px 36px; border:var(--rule-weight) solid var(--color-border); color:var(--color-muted);">dismissed</div>
            <div style="font-family:var(--font-mono); font-size:24px; letter-spacing:0.08em; padding:20px 36px; border:var(--rule-weight) solid var(--color-border); color:var(--color-muted);">reset to pending</div>
          </div>

          <div style="font-family:var(--font-body); font-size:32px; line-height:1.45; color:var(--color-muted); margin-top:44px; max-width:1300px;">A review note and the reviewer are stored with the finding. Review states describe what a person did, not what is legally correct.</div>
        </div>

        <div data-ref="export" style="
          margin-top:96px;
          border-top:var(--rule-weight) solid var(--color-border);
          padding-top:48px;
          display:grid;
          grid-template-columns:1fr 1fr;
          gap:72px;
          opacity:0;
        ">
          <div>
            <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Export bundle</div>
            <div style="display:flex; gap:24px; margin-top:28px; font-family:var(--font-mono); font-size:26px;">
              <span>JSON</span><span style="color:var(--color-muted);">/</span><span>Markdown</span><span style="color:var(--color-muted);">/</span><span>ZIP</span>
            </div>
          </div>
          <div>
            <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Each finding carries</div>
            <div style="font-family:var(--font-body); font-size:32px; line-height:1.5; margin-top:28px;">source hash, page, character offsets, provider, model, prompt version, review status, and the recorded failures and limitations.</div>
          </div>
        </div>
      </div>
    `);
	},

	async play(ctx) {
		const frame = host?.querySelector('scene-frame') as HTMLElement | null;
		const review = host?.querySelector('[data-ref="review"]') as HTMLElement | null;
		const exportBlock = host?.querySelector('[data-ref="export"]') as HTMLElement | null;

		(frame as { reveal?: () => void } | null)?.reveal?.();
		settle(review, 0);

		await ctx.waitForNext();

		settle(exportBlock, 0);

		// Holds to the 14.0s advance.
		await ctx.hold(8000);
	},

	unmount() {
		host = null;
	},
});
