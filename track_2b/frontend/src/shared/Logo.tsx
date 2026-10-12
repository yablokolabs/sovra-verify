/**
 * The Sovra Verify mark, shown once in the header.
 *
 * The asset is served from the frontend public directory, so this component
 * must stay in the header and must never be repeated as a bottom-of-page
 * branding strip.
 */
export function Logo() {
  return (
    <img
      className="brand-mark"
      src="/sovra-logo.png"
      alt="Sovra Verify"
      width={44}
      height={44}
      decoding="async"
    />
  )
}
