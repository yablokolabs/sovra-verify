/**
 * <scene-frame> — the shared editorial page chrome used by every scene in the
 * Sovra Verify demo. Renders the cream page, the two hairline rules that frame
 * the safe area, and an optional mono eyebrow label.
 *
 * Light DOM on purpose: the frame is not a security boundary, and keeping the
 * slotted content in the light tree lets each segment keep its own inline
 * styles without a shadow-root styling indirection. All class names are
 * prefixed `sf-` so the single injected stylesheet cannot collide with a
 * segment's own markup.
 *
 * Content is supplied explicitly via setContent() rather than read from
 * innerHTML in connectedCallback: reading children at connect time depends on
 * parse order, which differs between the dev player and the render driver.
 */

const TAG = 'scene-frame';

const FRAME_CSS = `
  .sf-root {
    position: relative;
    height: 100%;
    background: var(--color-bg);
    color: var(--color-fg);
    font-family: var(--font-body);
    overflow: hidden;
  }
  .sf-rule-top, .sf-rule-bottom {
    position: absolute;
    left: var(--safe-x);
    right: var(--safe-x);
    height: var(--rule-weight);
    background: var(--color-border);
  }
  .sf-rule-top { top: var(--safe-y); }
  .sf-rule-bottom { bottom: var(--safe-y); }
  .sf-label {
    position: absolute;
    left: var(--safe-x);
    top: calc(var(--safe-y) - 40px);
    font-family: var(--font-mono);
    font-size: 14px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--color-muted);
    opacity: 0;
  }
  .sf-body { position: absolute; inset: 0; }
`;

export class SceneFrame extends HTMLElement {
	private pending: string | null = null;

	connectedCallback(): void {
		if (this.dataset.sfReady === '1') return;
		this.dataset.sfReady = '1';
		const label = this.getAttribute('label') ?? '';
		this.innerHTML = `
      <div class="sf-root">
        <style>${FRAME_CSS}</style>
        <div class="sf-rule-top"></div>
        <div class="sf-rule-bottom"></div>
        ${label ? `<div class="sf-label" data-ref="label">${label}</div>` : ''}
        <div class="sf-body" data-ref="body">${this.pending ?? ''}</div>
      </div>
    `;
		this.pending = null;
	}

	/** Set the scene body. Safe to call before or after connect. */
	setContent(html: string): void {
		const body = this.querySelector('[data-ref="body"]');
		if (body) {
			body.innerHTML = html;
		} else {
			this.pending = html;
		}
	}

	body(): HTMLElement | null {
		return this.querySelector('[data-ref="body"]');
	}

	/** Fade the eyebrow label in. The only chrome motion; the page does not move. */
	reveal(): void {
		const label = this.querySelector('[data-ref="label"]') as HTMLElement | null;
		label?.animate([{ opacity: 0 }, { opacity: 1 }], {
			duration: 480,
			fill: 'forwards',
			easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
		});
	}
}

if (typeof customElements !== 'undefined' && !customElements.get(TAG)) {
	customElements.define(TAG, SceneFrame);
}

/**
 * Mount a scene frame into a host element and return it.
 * Throws rather than silently rendering an unframed scene, so a missing
 * definition surfaces during development instead of at export time.
 */
export function mountSceneFrame(host: HTMLElement, label: string): SceneFrame {
	host.innerHTML = `<${TAG} label="${label}" style="display:block;height:100%"></${TAG}>`;
	const frame = host.querySelector(TAG) as SceneFrame | null;
	if (!frame) {
		throw new Error('scene-frame did not mount');
	}
	return frame;
}

export const FRAME_EASE = 'cubic-bezier(0.16, 1, 0.3, 1)';

/** Shared entrance: settle down 16px while fading in. */
export function settle(
	el: HTMLElement | null,
	delayMs = 0,
	durationMs = 480,
): Animation | null {
	if (!el) return null;
	return el.animate(
		[
			{ opacity: 0, transform: 'translateY(16px)' },
			{ opacity: 1, transform: 'translateY(0)' },
		],
		{ duration: durationMs, delay: delayMs, fill: 'forwards', easing: FRAME_EASE },
	);
}

/** Shared fade-in for labels and static chrome. */
export function fadeIn(el: HTMLElement | null, delayMs = 0, durationMs = 480): Animation | null {
	if (!el) return null;
	return el.animate([{ opacity: 0 }, { opacity: 1 }], {
		duration: durationMs,
		delay: delayMs,
		fill: 'forwards',
		easing: FRAME_EASE,
	});
}

export default SceneFrame;
