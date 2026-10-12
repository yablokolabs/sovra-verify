#!/usr/bin/env bash
# Restore a file the published videowright 0.1.1 tarball does not ship.
#
# `node_modules/videowright/src/cli/entry/render_entry.ts` imports
# "../../index.js", which resolves to `node_modules/videowright/src/index.js`.
# The published package ships `dist/` and `src/cli/entry/` but no `src/index.js`,
# so Vite's import analysis fails, the render page never signals readiness, and
# `npx videowright render` exits with
# "page.waitForFunction: Timeout 30000ms exceeded".
#
# Run this after `npm install` in this folder, before rendering.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
target="$root/node_modules/videowright/src/index.js"

if [ ! -d "$root/node_modules/videowright" ]; then
  echo "videowright is not installed in $root; run npm install first" >&2
  exit 1
fi

{
  echo "// Local patch: see scripts/patch-videowright.sh for why this file is needed."
  echo "export * from '../dist/index.js';"
} > "$target"

echo "patched $target"
