import { defineSegment } from 'videowright';
import { mountSceneFrame, settle } from '../../components/scene-frame/index';

let host: HTMLElement | null = null;

const DOCS = [
	{
		name: 'Master supply agreement',
		file: '01_master_supply_agreement.txt',
		sha: 'a3f1c9d2e0b7',
		note: 'text layer, 1 page',
	},
	{
		name: 'Accounts payable policy',
		file: '02_accounts_payable_policy.txt',
		sha: '7d4ba18f2253',
		note: 'text layer, 1 page',
	},
	{
		name: 'Invoice INV-2026-0417',
		file: '03_invoice_INV-2026-0417.txt',
		sha: 'c8915ea40ff2',
		note: 'text layer, 1 page',
	},
	{
		name: 'Amendment No. 2',
		file: '04_amendment_2.txt',
		sha: '1e6d03b7aa48',
		note: 'text layer, 1 page',
	},
];

function card(doc: (typeof DOCS)[number]): string {
	return `
    <div data-ref="card" style="
      border:var(--rule-weight) solid var(--color-border);
      background:var(--color-surface);
      padding:40px 44px;
      opacity:0;
    ">
      <div style="font-family:var(--font-mono); font-size:14px; letter-spacing:0.16em; text-transform:uppercase; color:var(--color-muted);">${doc.file}</div>
      <div style="font-family:var(--font-display); font-size:52px; line-height:1.05; margin-top:24px;">${doc.name}</div>
      <div style="font-family:var(--font-mono); font-size:16px; color:var(--color-muted); margin-top:28px; letter-spacing:0.04em;">sha256 ${doc.sha}</div>
      <div style="font-family:var(--font-mono); font-size:16px; color:var(--color-muted); margin-top:8px; letter-spacing:0.04em;">extraction: ${doc.note}</div>
    </div>
  `;
}

/**
 * Scene 2 — the corpus. Four synthetic documents go in, each hashed and
 * extracted into canonical passages. Scanned pages are refused, not guessed at.
 */
export default defineSegment({
	id: 'sovra-corpus',
	advances: [4.5, 9.0, 13.5, 19.0],
	voiceover:
		'Sovra Verify starts from a corpus. Four synthetic documents go in: a master supply agreement, an accounts payable policy, an invoice, and an amendment. Each file is hashed, and its text is extracted into canonical passages with page and character offsets. Scanned pages are refused, not guessed at.',
	notes: 'Document grid with hash and extraction metadata.',

	mount(el) {
		host = el;
		const frame = mountSceneFrame(el, 'Corpus / four synthetic documents');
		frame.setContent(`
      <div style="position:absolute; left:var(--safe-x); right:var(--safe-x); top:180px;">
        <div data-ref="headline" style="
          font-family:var(--font-display);
          font-size:76px;
          line-height:1.0;
          opacity:0;
        ">Four documents in, <span style="font-style:italic;">nothing trusted</span>.</div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:40px; margin-top:64px;">
          ${DOCS.map(card).join('')}
        </div>

        <div data-ref="footnote" style="
          font-family:var(--font-body);
          font-size:34px;
          line-height:1.4;
          color:var(--color-muted);
          margin-top:48px;
          opacity:0;
        ">Every upload is stored under a random internal name. The supplied filename is never used as a path.</div>
      </div>
    `);
	},

	async play(ctx) {
		const frame = host?.querySelector('scene-frame') as HTMLElement | null;
		const headline = host?.querySelector('[data-ref="headline"]') as HTMLElement | null;
		const cards = Array.from(host?.querySelectorAll('[data-ref="card"]') ?? []) as HTMLElement[];
		const footnote = host?.querySelector('[data-ref="footnote"]') as HTMLElement | null;

		(frame as { reveal?: () => void } | null)?.reveal?.();
		settle(headline, 0);

		await ctx.waitForNext();

		settle(cards[0] ?? null, 0);
		settle(cards[1] ?? null, 120);

		await ctx.waitForNext();

		settle(cards[2] ?? null, 0);
		settle(cards[3] ?? null, 120);

		await ctx.waitForNext();

		settle(footnote, 0);

		await ctx.hold(5500);
	},

	unmount() {
		host = null;
	},
});
