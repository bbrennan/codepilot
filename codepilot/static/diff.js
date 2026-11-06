"use strict";
// Diffs as a code review tool shows them: old and new line numbers in two gutters, a +/− column, file names instead of
// raw `diff --git` / `---` / `+++` headers, and a quiet ⋯ row between hunks (with the function git names, if any). One
// renderer for every diff: the Review tab, a change's own tab, its card in the chat, and the working tree.

const DIFF_META = /^(index |new file mode|deleted file mode|old mode|new mode|similarity index|rename from|rename to|copy from|copy to|Binary files)/;

function diffHtml(diff) {
  const rows = [];
  let o = 0, n = 0, hunks = 0, header = true; // `---`/`+++` are headers only before a file's first @@
  const gutter = (oldNo, newNo, sign) => `<span class="ln o">${oldNo}</span><span class="ln n">${newNo}</span><span class="sg">${sign}</span>`;
  const row = (cls, oldNo, newNo, sign, text) => `<div class="dl ${cls}">${gutter(oldNo, newNo, sign)}<span class="code">${esc(text) || " "}</span></div>`;
  for (const l of String(diff || "").split("\n")) {
    let m;
    if ((m = l.match(/^diff --git a\/.+? b\/(.+)$/))) { rows.push(`<div class="f">${esc(m[1])}</div>`); header = true; hunks = 0; continue; }
    if (header && (l.startsWith("--- ") || l.startsWith("+++ ") || DIFF_META.test(l))) continue;
    if ((m = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)$/))) {
      o = +m[1]; n = +m[2]; header = false;
      if (hunks++ || m[3]) rows.push(`<div class="hunk">${gutter("", "", "⋯")}<span class="code">${esc(m[3])}</span></div>`);
      continue;
    }
    if (l === "") continue; // the end of the text (an empty context line is " ")
    if (l.startsWith("\\")) rows.push(`<div class="note">${esc(l.slice(2))}</div>`); // "\ No newline at end of file"
    else if (l.startsWith("+")) rows.push(row("a", "", n++, "+", l.slice(1)));
    else if (l.startsWith("-")) rows.push(row("d", o++, "", "−", l.slice(1)));
    else rows.push(row("", o++, n++, "", l.slice(1)));
  }
  return `<div class="diff">${rows.join("")}</div>`;
}
