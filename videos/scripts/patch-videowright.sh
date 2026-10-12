#!/usr/bin/env bash
# Restore files the published videowright 0.1.1 tarball does not ship.
#
# The package ships `dist/` and part of `src/cli/entry/`, but three modules the
# entry code imports from `src/` are missing from the tarball, so Vite's import
# analysis fails and the page never boots:
#
#   src/index.js                     imported by every entry file
#   src/timeline/resolveTiming.js    imported by the dev video view
#   src/types.js                     imported by the dev homepage view
#
# The symptoms differ by entry point, which is why they read as two bugs:
#
#   `npx videowright render` — the render page never signals readiness and the
#   command exits with "page.waitForFunction: Timeout 30000ms exceeded".
#
#   `npx videowright dev` — the browser reports HTTP 500 for
#   `/views/video_view.ts`, the video area stays empty, and
#   `window.__VW_PLAYER_READY__` is never set.
#
# Each shim re-exports the compiled module from `dist/`, so behaviour is the
# vendor's own compiled code and nothing is reimplemented here.
#
# Run this after `npm install` in this folder, before the dev server or a render.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -d "$root/node_modules/videowright" ]; then
  echo "videowright is not installed in $root; run npm install first" >&2
  exit 1
fi

# target relative to the package root | module to re-export, relative to the target
shims=(
  "src/index.js|../dist/index.js"
  "src/types.js|../dist/types.js"
  "src/timeline/resolveTiming.js|../../dist/timeline/resolveTiming.js"
)

patched=0
for shim in "${shims[@]}"; do
  target="$root/node_modules/videowright/${shim%%|*}"
  source="${shim##*|}"
  # The re-export is resolved by Vite relative to the shim, so check it there.
  # The shim's own directory may not exist yet, so resolve the path by hand.
  mkdir -p "$(dirname "$target")"
  if [ ! -f "$(cd "$(dirname "$target")" && pwd)/${source}" ]; then
    echo "missing ${source} next to ${shim%%|*} in the installed package; nothing written" >&2
    exit 1
  fi
  {
    echo "// Local shim: see scripts/patch-videowright.sh for why this file is needed."
    echo "export * from '${source}';"
  } > "$target"
  echo "patched ${target#"$root/"}"
  patched=$((patched + 1))
done

echo "patched $patched videowright file(s)"
