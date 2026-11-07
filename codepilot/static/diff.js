"use strict";
// Diffs as a code review tool shows them: old and new line numbers in two gutters, a +/− column, file names instead of
// raw `diff --git` / `---` / `+++` headers, and a quiet ⋯ row between hunks (with the function git names, if any). One
// renderer for every diff: the Review tab, a change's own tab, its card in the chat, and the working tree.

const DIFF_SKIP = /^(index |similarity index |dissimilarity index )/;

// Git C-quotes a path with non-ASCII bytes, tabs or quotes ("caf\303\251.py"): turn it back into the name.
function gitUnquote(q) {
  const bytes = [];
  const named = { n: 10, t: 9, r: 13, b: 8, f: 12, a: 7, v: 11, '"': 34, "\\": 92 };
  for (let i = 0; i < q.length; i++) {
    const c = q[i];
    if (c !== "\\") { bytes.push(...new TextEncoder().encode(c)); continue; }
    const oct = q.slice(i + 1, i + 4);
    if (/^[0-7]{3}$/.test(oct)) { bytes.push(parseInt(oct, 8)); i += 3; } else { bytes.push(named[q[i + 1]] ?? q.charCodeAt(i + 1)); i += 1; }
  }
  return new TextDecoder().decode(new Uint8Array(bytes));
}

// The file a `diff --git` / `diff --cc` header names: the destination. Git quotes each side on its own when it has
// unusual characters, but never for spaces, so: a quoted destination is read from the end; after a quoted source, the
// rest is the destination; two plain sides are equal halves ("a/X b/X"), or for a rename, what follows " b/".
const QUOTED = String.raw`"(?:[^"\\]|\\.)*"`;
function fileName(line) {
  const rest = line.replace(/^diff --(git|cc|combined) /, "");
  if (!line.startsWith("diff --git ")) return rest.startsWith('"') ? gitUnquote(rest.slice(1, -1)) : rest;
  let m = rest.match(new RegExp(String.raw` "b\/((?:[^"\\]|\\.)*)"$`));
  if (m) return gitUnquote(m[1]);
  m = rest.match(new RegExp(`^${QUOTED} b\\/(.+)$`));
  if (m) return m[1];
  const sep = (rest.length - 1) / 2; // "a/" + X + " b/" + X: the separator sits at 2 + |X|
  if (Number.isInteger(sep) && rest.startsWith("a/") && rest.slice(sep, sep + 3) === " b/" && rest.slice(2, sep) === rest.slice(sep + 3))
    return rest.slice(sep + 3);
  const renamed = rest.match(/^a\/.+? b\/(.+)$/);
  return renamed ? renamed[1] : rest;
}

function diffHtml(diff) {
  const rows = [];
  let o = 0, n = 0, hunks = 0, header = true; // `---`/`+++` are headers only before a file's first @@
  let oldMode = "", renamedFrom = "", copiedFrom = "", combined = false, sides = 2;
  const gutter = (oldNo, newNo, sign) => `<span class="ln o">${oldNo}</span><span class="ln n">${newNo}</span><span class="sg">${sign}</span>`;
  const row = (cls, oldNo, newNo, sign, text) => `<div class="dl ${cls}">${gutter(oldNo, newNo, sign)}<span class="code">${esc(text) || " "}</span></div>`;
  const meta = (text) => rows.push(`<div class="meta">${esc(text)}</div>`); // what a change is when it has no lines
  for (const l of String(diff || "").split("\n")) {
    let m;
    if (/^diff --(git|cc|combined) /.test(l)) { // a new file, and a fresh start
      combined = !l.startsWith("diff --git ");
      rows.push(`<div class="f">${esc(fileName(l))}</div>`);
      if (combined) meta("merge in progress: both sides' changes, combined");
      header = true; hunks = 0; oldMode = renamedFrom = copiedFrom = "";
      continue;
    }
    if (header) {
      if (l.startsWith("--- ") || l.startsWith("+++ ") || DIFF_SKIP.test(l)) continue;
      if ((m = l.match(/^new file mode (\d+)/))) { meta("new file"); continue; }
      if ((m = l.match(/^deleted file mode (\d+)/))) { meta("deleted"); continue; }
      if ((m = l.match(/^old mode (\d+)/))) { oldMode = m[1]; continue; }
      if ((m = l.match(/^new mode (\d+)/))) { meta(`mode ${oldMode} → ${m[1]}${/755$/.test(m[1]) ? " (now executable)" : /755$/.test(oldMode) ? " (no longer executable)" : ""}`); continue; }
      if ((m = l.match(/^rename from (.+)/))) { renamedFrom = m[1]; continue; }
      if (l.startsWith("rename to ")) { meta(`renamed from ${renamedFrom}`); continue; }
      if ((m = l.match(/^copy from (.+)/))) { copiedFrom = m[1]; continue; }
      if (l.startsWith("copy to ")) { meta(`copied from ${copiedFrom}`); continue; }
      if (l.startsWith("Binary files ")) { meta("binary file changed (not shown)"); continue; }
    }
    if (combined && (m = l.match(/^(@@@+) .*? \1 ?(.*)$/))) { // a merge's hunk: one prefix column per side
      sides = m[1].length - 1; header = false;
      if (hunks++ || m[2]) rows.push(`<div class="hunk">${gutter("", "", "⋯")}<span class="code">${esc(m[2])}</span></div>`);
      continue;
    }
    if ((m = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)$/))) {
      o = +m[1]; n = +m[2]; header = false;
      if (hunks++ || m[3]) rows.push(`<div class="hunk">${gutter("", "", "⋯")}<span class="code">${esc(m[3])}</span></div>`);
      continue;
    }
    if (l === "" || header) continue; // the end of the text; anything else before a hunk is git's bookkeeping
    if (combined) { // no single old/new pair to number: the prefix says which side added or removed it
      const prefix = l.slice(0, sides), cls = prefix.includes("+") ? "a" : prefix.includes("-") ? "d" : "";
      rows.push(row(cls, "", "", cls === "a" ? "+" : cls === "d" ? "−" : "", l.slice(sides)));
      continue;
    }
    if (l.startsWith("\\")) rows.push(`<div class="note">${esc(l.slice(2))}</div>`); // "\ No newline at end of file"
    else if (l.startsWith("+")) rows.push(row("a", "", n++, "+", l.slice(1)));
    else if (l.startsWith("-")) rows.push(row("d", o++, "", "−", l.slice(1)));
    else rows.push(row("", o++, n++, "", l.slice(1)));
  }
  return `<div class="diff">${rows.join("")}</div>`;
}
