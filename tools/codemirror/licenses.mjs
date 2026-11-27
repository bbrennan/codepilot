// From esbuild's metafile: every package in the bundle. Writes each distinct licence text once, naming the packages
// it covers, to the file given; prints the bundled versions ("@codemirror/view 6.44.2, ...") for the banner.
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const [meta, out] = process.argv.slice(2);
const names = new Set();
for (const input of Object.keys(JSON.parse(readFileSync(meta, "utf8")).inputs)) {
  const m = input.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
  if (m) names.add(m[1]);
}
const texts = new Map(); // licence text -> packages
const versions = [];
for (const name of [...names].sort()) {
  const dir = join("node_modules", name);
  const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  if (pkg.license !== "MIT") throw new Error(`${name} is ${pkg.license}, not MIT: check it before bundling`);
  const file = readdirSync(dir).find((f) => /^licen[cs]e/i.test(f));
  if (!file) throw new Error(`${name} has no licence file`);
  const text = readFileSync(join(dir, file), "utf8").trim();
  texts.set(text, [...(texts.get(text) || []), `${name} ${pkg.version}`]);
  versions.push(`${name} ${pkg.version}`);
}
const parts = [...texts].map(([text, pkgs]) => `${pkgs.join("\n")}\n\n${text}`);
writeFileSync(out, `codemirror.min.js bundles these packages, all under the MIT licence.\n\n${parts.join("\n\n" + "-".repeat(72) + "\n\n")}\n`);
process.stdout.write(versions.join(", "));
