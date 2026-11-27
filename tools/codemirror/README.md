# CodeMirror bundle

`codepilot/static/vendor/codemirror.min.js` is CodeMirror 6 built into one classic script, so the app needs no build
step to run or to test. This folder is how it was made. It is not part of the Python package.

- `package.json` and `package-lock.json`: the exact versions (no ranges; `tests/test_repo_hygiene.py` checks).
- `entry.js`: what `codepilot/static/editor.js` uses, assigned to `window.CM`. Only what it names is bundled.
- `licenses.mjs`: writes `LICENSE-codemirror` from the packages esbuild actually bundled (and refuses one that isn't MIT).
- `build.sh`: `npm ci`, esbuild (`--bundle --minify --format=iife`), then the bundle's first line names every version.

## Rebuilding

Rebuild when `editor.js` needs something `entry.js` doesn't export yet, or to update CodeMirror. Updating is by hand,
like the other vendored files (Dependabot doesn't watch this folder):

```bash
cd tools/codemirror
npm install --save-exact @codemirror/view@<version>   # or edit package.json, then: npm install
sh build.sh                                            # writes the bundle and LICENSE-codemirror
```

Then update the CodeMirror row in `THIRD_PARTY_NOTICES.md`, run `make test` and `make e2e`, and commit the bundle,
`LICENSE-codemirror`, `package.json` and `package-lock.json` together. `node_modules/` is not committed.
