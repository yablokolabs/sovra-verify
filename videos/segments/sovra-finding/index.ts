import { defineSegment } from 'videowright';
import { mountSceneFrame, settle } from '../../components/scene-frame/index';

let host: HTMLElement | null = null;

type Side = {
	ref: string;
	doc: string;
	page: number;
	start: number;
	end: number;
	claim: string;
	before: string;
	operative: string;
	after: string;
};

/**
 * Both spans, their offsets and their quotations come from one recorded run
 * against the demo corpus. The quote text shown is the canonical slice at those
 * offsets; the model never authored it.
 */
const LEFT: Side = {
	ref: 'left',
	doc: '01_master_supply_agreement.txt',
	page: 1,
	start: 342,
	end: 531,
	claim: 'payment_period = 30 days',
	before: 'Clause 7.2 Payment terms. The Buyer shall pay each undisputed invoice ',
	operative: 'within 30 days of the invoice date',
	after: '. Payments shall be made in CHF by bank transfer to the account stated on the invoice.',
};

const RIGHT: Side = {
	ref: 'right',
	doc: '02_accounts_payable_policy.txt',
	page: 1,
	start: 239,
	end: 430,
	claim: 'payment_period = 60 days',
	before: 'Policy 4.1 Standard settlement period. All supplier invoices are settled ',
	operative: 'within 60 days of the invoice date',
	after: '. Finance Operations processes the payment run on the last working day of each month.',
};

function column(side: Side): string {
	return `
    <div data-ref="${side.ref}" style="opacity:0;">
      <div style="font-family:var(--font-mono); font-size:16px; letter-spacing:0.12em; text-transform:uppercase; color:var(--color-muted);">
        ${side.doc} &middot; page ${side.page} &middot; offsets [${side.start}, ${side.end}]
      </div>

      <div style="
        font-family:var(--font-mono);
        font-size:26px;
        margin-top:28px;
        padding:14px 20px;
        background:var(--color-surface);
        border-left:var(--rule-weight) solid var(--color-border);
        display:inline-block;
      ">${side.claim}</div>

      <div style="
        font-family:var(--font-body);
        font-size:32px;
        line-height:1.5;
        margin-top:36px;
      ">${side.before}<span style="color:var(--color-accent); font-weight:600;">${side.operative}</span>${side.after}</div>
    </div>
  `;
}

/**
 * Scene 4 — the conflict. Two claims, same effective date, incompatible values,
 * each with the exact canonical span and character offsets that carry it.
 */
export default defineSegment({
	id: 'sovra-finding',
	advances: [5.0, 10.0, 15.0, 20.0],
	voiceover:
		'The agreement says payment is due within 30 days of the invoice date. The policy says invoices are settled within 60 days, under the same effective date. Both quotes are sliced from canonical text at the recorded offsets.',
	notes: 'The genuine conflict. Offsets and quotes are from the recorded run.',

	mount(el) {
		host = el;
		const frame = mountSceneFrame(el, 'Finding / potential conflict');
		frame.setContent(`
      <div style="position:absolute; left:var(--safe-x); right:var(--safe-x); top:176px;">
        <div data-ref="headline" style="font-family:var(--font-display); font-size:72px; line-height:1.0; opacity:0;">
          Same scope. Same effective date. <span style="font-style:italic;">Two deadlines.</span>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:72px; margin-top:88px;">
          ${column(LEFT)}
          ${column(RIGHT)}
        </div>

        <div data-ref="verdict" style="
          margin-top:80px;
          border-top:var(--rule-weight) solid var(--color-border);
          padding-top:36px;
          display:flex;
          align-items:baseline;
          gap:40px;
          opacity:0;
        ">
          <div style="font-family:var(--font-mono); font-size:26px; letter-spacing:0.12em; text-transform:uppercase; color:var(--color-accent);">potential_conflict</div>
          <div style="font-family:var(--font-body); font-size:32px; line-height:1.4; color:var(--color-muted); max-width:1180px;">The spans are derived from offsets, not from text the model wrote. A finding whose spans do not resolve is rejected before it is shown.</div>
        </div>
      </div>
    `);
	},

	async play(ctx) {
		const frame = host?.querySelector('scene-frame') as HTMLElement | null;
		const headline = host?.querySelector('[data-ref="headline"]') as HTMLElement | null;
		const left = host?.querySelector('[data-ref="left"]') as HTMLElement | null;
		const right = host?.querySelector('[data-ref="right"]') as HTMLElement | null;
		const verdict = host?.querySelector('[data-ref="verdict"]') as HTMLElement | null;

		(frame as { reveal?: () => void } | null)?.reveal?.();
		settle(headline, 0);

		await ctx.waitForNext();

		settle(left, 0);

		await ctx.waitForNext();

		settle(right, 0);

		await ctx.waitForNext();

		settle(verdict, 0);

		await ctx.hold(5000);
	},

	unmount() {
		host = null;
	},
});
