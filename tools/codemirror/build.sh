#!/bin/sh
# Rebuilds codepilot/static/vendor/codemirror.min.js and LICENSE-codemirror from the versions pinned in
# package-lock.json. Run from anywhere: sh tools/codemirror/build.sh (needs Node 22 and the npm registry, once).
set -eu
cd "$(dirname "$0")"
VENDOR=../../codepilot/static/vendor
npm ci --no-audit --no-fund
npx esbuild entry.js --bundle --minify --format=iife --target=es2020 --legal-comments=none \
  --metafile=meta.json --outfile=bundle.tmp.js
node licenses.mjs meta.json "$VENDOR/LICENSE-codemirror" > versions.tmp
# The first line says what's inside, so the committed file names its own versions.
{ printf '/* CodeMirror 6 for codepilot (tools/codemirror): %s */\n' "$(cat versions.tmp)"; cat bundle.tmp.js; } \
  > "$VENDOR/codemirror.min.js"
rm -f bundle.tmp.js versions.tmp meta.json
ls -l "$VENDOR/codemirror.min.js"
