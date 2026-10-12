import { defineSegment } from 'videowright';
import { mountSceneFrame, settle } from '../../components/scene-frame/index';

let host: HTMLElement | null = null;

/**
 * Scene 5 — the cases that must NOT be reported as conflicts: a stated
 * exception, and a difference explained by a different effective date.
 */
export default defineSegment({
	id: 'sovra-negative',
	advances: [5.0, 11.0, 20.0],
	voiceover:
		'Two pairs are not conflicts. The expedited freight clause sets a 10 day period as a stated exception, and the amendment changes payment to 45 days, effective 1 May 2026. Sovra Verify flags potential inconsistencies for a human. It does not decide which document wins.',
	notes: 'Negative cases: valid exception and date change. No legal conclusion.',

	mount(el) {
		host = el;
		const frame = mountSceneFrame(el, 'Negative cases / what is not a conflict');
		frame.setContent(`
      <div style="position:absolute; left:var(--safe-x); right:var(--safe-x); top:176px;">
        <div data-ref="headline" style="font-family:var(--font-display); font-size:72px; line-height:1.0; opacity:0;">
          Not every difference is a <span style="font-style:italic;">contradiction</span>.
        </div>

        <div data-ref="cardA" style="
          margin-top:52px;
          border:var(--rule-weight) solid var(--color-border);
          background:var(--color-surface);
          padding:44px 48px;
          display:grid;
          grid-template-columns:280px 1fr;
          gap:48px;
          opacity:0;
        ">
          <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Stated exception</div>
          <div>
            <div style="font-family:var(--font-display); font-size:44px; line-height:1.1;">Expedited freight: 10 days</div>
            <div style="font-family:var(--font-body); font-size:32px; line-height:1.45; color:var(--color-muted); margin-top:20px;">Clause 7.5 says invoices under the expedited freight programme are payable within 10 days, and that Clause 7.2 does not apply to them. It is a carve-out, not a conflict.</div>
          </div>
        </div>

        <div data-ref="cardB" style="
          margin-top:28px;
          border:var(--rule-weight) solid var(--color-border);
          background:var(--color-surface);
          padding:44px 48px;
          display:grid;
          grid-template-columns:280px 1fr;
          gap:48px;
          opacity:0;
        ">
          <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.14em; text-transform:uppercase; color:var(--color-muted);">Different effective date</div>
          <div>
            <div style="font-family:var(--font-display); font-size:44px; line-height:1.1;">Amendment: 45 days, from 2026-05-01</div>
            <div style="font-family:var(--font-body); font-size:32px; line-height:1.45; color:var(--color-muted); margin-top:20px;">A different known effective date explains a different number. The pair is filtered out of the comparison and the count is reported, so it cannot hide a conflict silently.</div>
          </div>
        </div>

        <div data-ref="boundary" style="
          margin-top:44px;
          font-family:var(--font-body);
          font-size:32px;
          line-height:1.45;
          opacity:0;
        ">Sovra Verify flags <strong>potential</strong> inconsistencies for human review. It does not decide which document wins, and it gives no legal or compliance conclusion.</div>
      </div>
    `);
	},

	async play(ctx) {
		const frame = host?.querySelector('scene-frame') as HTMLElement | null;
		const headline = host?.querySelector('[data-ref="headline"]') as HTMLElement | null;
		const cardA = host?.querySelector('[data-ref="cardA"]') as HTMLElement | null;
		const cardB = host?.querySelector('[data-ref="cardB"]') as HTMLElement | null;
		const boundary = host?.querySelector('[data-ref="boundary"]') as HTMLElement | null;

		(frame as { reveal?: () => void } | null)?.reveal?.();
		settle(headline, 0);

		await ctx.waitForNext();

		settle(cardA, 0);

		await ctx.waitForNext();

		settle(cardB, 0);
		settle(boundary, 320);

		// Holds to the 20.0s advance.
		await ctx.hold(9000);
	},

	unmount() {
		host = null;
	},
});
