/**
 * The Sovra Verify mark, shown once in the header.
 *
 * The asset is served from the frontend public directory, so this component
 * must stay in the header and must never be repeated as a bottom-of-page
 * branding strip.
 *
 * The path is built from Vite's base rather than written as "/sovra-logo.png":
 * the backend mounts the build at /app, so a root-absolute URL asks the server
 * for a file it does not serve and the header rendered a broken image. The base
 * is '/app/', which makes this resolve to /app/sovra-logo.png in the build and
 * in the dev server alike.
 */
export function Logo() {
  return (
    <img
      className="brand-mark"
      src={`${import.meta.env.BASE_URL}sovra-logo.png`}
      alt="Sovra Verify"
      width={44}
      height={44}
      decoding="async"
    />
  )
}
