// Sets Kura's version in both places it lives (app/package.json and engine/pyproject.toml),
// then refreshes the engine's lockfile and API snapshot, which carry the version too.
//
//   node scripts/set-version.mjs 1.2.3
//
// See docs/releasing.md.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const version = process.argv[2] ?? "";
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  console.error("Usage: node scripts/set-version.mjs 1.2.3");
  process.exit(1);
}

const path = (relative) => fileURLToPath(new URL(`../${relative}`, import.meta.url));

function replaceIn(file, pattern, replacement) {
  const before = readFileSync(path(file), "utf8");
  const after = before.replace(pattern, replacement);
  if (after === before) throw new Error(`No version found in ${file}`);
  writeFileSync(path(file), after);
}

replaceIn("app/package.json", /"version": "[^"]+"/, `"version": "${version}"`);
replaceIn("engine/pyproject.toml", /^version = "[^"]+"/m, `version = "${version}"`);

const engine = { cwd: path("engine"), stdio: "inherit" };
execFileSync("uv", ["lock"], engine);
execFileSync("uv", ["run", "kura", "openapi", "openapi.json"], engine);

console.log(`\nKura is now ${version}. Commit it, then release with:`);
console.log(`  git tag v${version} && git push origin main v${version}`);
