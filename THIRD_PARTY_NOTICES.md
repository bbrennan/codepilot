# Third-party notices

codepilot bundles these files in `codepilot/static/vendor/`; each keeps its own licence. CodeMirror is built from
`tools/codemirror/` (pinned versions, one command: see its README).

| Component | File | Version | Licence | Licence text |
|---|---|---|---|---|
| [highlight.js](https://github.com/highlightjs/highlight.js) | `highlight.min.js` | 11.10.0 | BSD-3-Clause | `codepilot/static/vendor/LICENSE-highlightjs` |
| [xterm.js](https://github.com/xtermjs/xterm.js) (`@xterm/xterm`) | `xterm.js`, `xterm.css` | 5.5.0 | MIT | `codepilot/static/vendor/LICENSE-xterm` |
| [@xterm/addon-fit](https://github.com/xtermjs/xterm.js) | `addon-fit.js` | 0.10.0 | MIT | `codepilot/static/vendor/LICENSE-xterm` |
| [marked](https://github.com/markedjs/marked) | `marked.umd.js` | 18.0.13 | MIT | `codepilot/static/vendor/LICENSE-marked` |
| [DOMPurify](https://github.com/cure53/DOMPurify) | `purify.min.js` | 3.4.15 | Apache-2.0 or MPL-2.0 (used under Apache-2.0) | `codepilot/static/vendor/LICENSE-dompurify` |
| [Mermaid](https://github.com/mermaid-js/mermaid) | `mermaid.min.js` | 11.17.2 | MIT | `codepilot/static/vendor/LICENSE-mermaid` |
| [CodeMirror 6](https://codemirror.net) and its Lezer parsers | `codemirror.min.js` | `@codemirror/view` 6.44.2, `@codemirror/state` 6.7.6; every package and version is in the file's first line | MIT | `codepilot/static/vendor/LICENSE-codemirror` |

The UI icons are drawn in the style of [Lucide](https://lucide.dev) (ISC licence).

The built-in skills' workflows are adapted from ideas in [mattpocock/skills](https://github.com/mattpocock/skills)
(MIT) and [obra/superpowers](https://github.com/obra/superpowers), and rewritten for codepilot; no text is
copied verbatim.

Python dependencies are installed from PyPI under their own licences and are not redistributed here.
