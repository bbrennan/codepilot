// What codepilot/static/editor.js uses from CodeMirror 6, as one object on window.CM. Only what is named here ends up
// in the bundle, so a function editor.js starts using is added here and the bundle rebuilt (README.md).

import { EditorState, EditorSelection, Compartment, Prec } from "@codemirror/state";
import {
  EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, dropCursor,
  highlightSpecialChars, rectangularSelection, crosshairCursor,
} from "@codemirror/view";
import { defaultKeymap, historyKeymap, history, indentWithTab, undo, redo } from "@codemirror/commands";
import { indentUnit, indentOnInput, bracketMatching, syntaxHighlighting, HighlightStyle, StreamLanguage } from "@codemirror/language";
import { search, searchKeymap, gotoLine, openSearchPanel, closeSearchPanel, getSearchQuery, setSearchQuery, SearchQuery } from "@codemirror/search";
import { tags } from "@lezer/highlight";

import { python } from "@codemirror/lang-python";
import { javascriptLanguage, typescriptLanguage, jsxLanguage, tsxLanguage } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { html } from "@codemirror/lang-html";
import { xml } from "@codemirror/lang-xml";
import { css } from "@codemirror/lang-css";
import { yaml } from "@codemirror/lang-yaml";
import { rust } from "@codemirror/lang-rust";
import { go } from "@codemirror/lang-go";
import { java } from "@codemirror/lang-java";
import { cpp } from "@codemirror/lang-cpp";
import { sql } from "@codemirror/lang-sql";
import { php } from "@codemirror/lang-php";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import { toml } from "@codemirror/legacy-modes/mode/toml";
import { properties } from "@codemirror/legacy-modes/mode/properties";
import { ruby } from "@codemirror/legacy-modes/mode/ruby";
import { kotlin, csharp } from "@codemirror/legacy-modes/mode/clike";
import { swift } from "@codemirror/legacy-modes/mode/swift";
import { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";
import { sCSS } from "@codemirror/legacy-modes/mode/css";

const stream = (mode) => () => StreamLanguage.define(mode);

// Each a function, so a language's extension is only made when a file of it is edited. No tag closing, no link on
// paste: the editor types what you type (no completion, no close-brackets).
const languages = {
  python: () => python(),
  javascript: () => javascriptLanguage,
  typescript: () => typescriptLanguage,
  jsx: () => jsxLanguage,
  tsx: () => tsxLanguage,
  json: () => json(),
  markdown: () => markdown({ pasteURLAsLink: false }),
  html: () => html({ autoCloseTags: false }),
  xml: () => xml({ autoCloseTags: false }),
  css: () => css(),
  scss: stream(sCSS),
  yaml: () => yaml(),
  rust: () => rust(),
  go: () => go(),
  java: () => java(),
  cpp: () => cpp(),
  sql: () => sql(),
  php: () => php(),
  shell: stream(shell),
  toml: stream(toml),
  properties: stream(properties),
  ruby: stream(ruby),
  kotlin: stream(kotlin),
  csharp: stream(csharp),
  swift: stream(swift),
  dockerfile: stream(dockerFile),
};

window.CM = {
  EditorState, EditorSelection, Compartment, Prec,
  EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, dropCursor,
  highlightSpecialChars, rectangularSelection, crosshairCursor,
  defaultKeymap, historyKeymap, history, indentWithTab, undo, redo,
  indentUnit, indentOnInput, bracketMatching, syntaxHighlighting, HighlightStyle,
  search, searchKeymap, gotoLine, openSearchPanel, closeSearchPanel, getSearchQuery, setSearchQuery, SearchQuery,
  tags, languages,
};
