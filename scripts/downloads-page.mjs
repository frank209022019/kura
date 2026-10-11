// Builds Kura's downloads page: every published version, newest first, with its notes and its
// installer. The downloads workflow publishes it on GitHub Pages after each release.
//
//   node scripts/downloads-page.mjs <folder>                     # reads the releases from GitHub
//   node scripts/downloads-page.mjs <folder> --releases <file>   # from a saved list, to preview
//
// See docs/releasing.md.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compareVersions, parseVersion } from "./versioning.mjs";

const REPOSITORY = "frankgrobbelaar/kura";

const LOGO = `<svg viewBox="0 0 24 24" width="32" height="32" aria-hidden="true">
  <rect x="1" y="1" width="22" height="22" rx="7" fill="#f2b33d"/>
  <rect x="6.4" y="6.5" width="2.8" height="11" rx="1.4" fill="#1d1300"/>
  <rect x="10.6" y="8.5" width="2.8" height="9" rx="1.4" fill="#1d1300"/>
  <rect x="14.6" y="6.2" width="2.8" height="11.2" rx="1.4" fill="#1d1300" transform="rotate(14 16 11.8)"/>
</svg>`;

export function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function inline(text) {
  return escapeHtml(text)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2">$2</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/** The little Markdown the changelog uses: headings, lists (with wrapped lines), links, bold, code. */
export function markdown(text) {
  const html = [];
  let list = null;
  let paragraph = [];
  const close = () => {
    if (paragraph.length) html.push(`<p>${inline(paragraph.join(" "))}</p>`);
    if (list) html.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`);
    paragraph = [];
    list = null;
  };
  for (const raw of String(text).replaceAll("\r\n", "\n").split("\n")) {
    const line = raw.trim();
    const heading = /^#{1,6} (.+)$/.exec(line);
    const item = /^[-*] (.+)$/.exec(line);
    if (!line) {
      close();
    } else if (heading) {
      close();
      html.push(`<h3>${inline(heading[1])}</h3>`);
    } else if (item) {
      if (paragraph.length) close();
      list ??= [];
      list.push(item[1]);
    } else if (list && /^\s/.test(raw)) {
      list[list.length - 1] += ` ${line}`;
    } else {
      if (list) close();
      paragraph.push(line);
    }
  }
  close();
  return html.join("\n");
}

/** Splits release notes into what's new and the list of every commit after it. */
function splitNotes(body) {
  const text = String(body ?? "").replaceAll("\r\n", "\n");
  const at = text.search(/^### Every change/m);
  return at === -1 ? [text, ""] : [text.slice(0, at), text.slice(at)];
}

function day(iso) {
  const options = { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" };
  return new Date(iso).toLocaleDateString("en-GB", options);
}

function megabytes(bytes) {
  return `${(bytes / 1e6).toFixed(1)} MB`;
}

/** Published versions, newest first, each with its installer and notices. */
export function versions(releases) {
  return releases
    .filter((release) => !release.draft && !release.prerelease)
    .map((release) => ({ release, version: String(release.tag_name).replace(/^v/, "") }))
    .filter(({ version }) => parseVersion(version))
    .sort((a, b) => compareVersions(b.version, a.version))
    .map(({ release, version }) => ({
      version,
      date: day(release.published_at),
      notes: release.body ?? "",
      page: release.html_url,
      installer: release.assets?.find((asset) => /_x64-setup\.exe$/.test(asset.name)) ?? null,
      notices: release.assets?.find((asset) => asset.name === "THIRD-PARTY-NOTICES.txt") ?? null,
    }));
}

function downloadButton(version) {
  if (!version.installer) return "";
  return `<a class="button primary" href="${escapeHtml(version.installer.browser_download_url)}">Download for Windows</a>`;
}

function fileLine(version) {
  if (!version.installer) return "";
  const { name, size, digest } = version.installer;
  const hash = digest?.startsWith("sha256:")
    ? `<span class="hash">SHA-256 ${escapeHtml(digest.slice(7))}</span>`
    : "";
  return `<p class="file"><span>${escapeHtml(name)} · ${megabytes(size)}</span>${hash}</p>`;
}

function notesBlock(version) {
  const [whatsNew, everyChange] = splitNotes(version.notes);
  const every = everyChange.trim()
    ? `<details><summary>Every change in ${escapeHtml(version.version)}</summary>${markdown(everyChange)}</details>`
    : "";
  return `${markdown(whatsNew)}${every}`;
}

function hero(latest, repository) {
  if (!latest) {
    return `<section class="hero" aria-labelledby="latest">
  <span class="orb" aria-hidden="true"></span>
  <p class="eyebrow">Downloads</p>
  <h1 id="latest">Kura is on its way</h1>
  <p class="lede">No version has been released yet. Each one will appear here, newest first, with
  what changed and a download for Windows.</p>
  <div class="actions"><a class="button primary" href="${repository}">Kura on GitHub</a></div>
</section>`;
  }
  return `<section class="hero" aria-labelledby="latest">
  <span class="orb" aria-hidden="true"></span>
  <p class="eyebrow">Latest version</p>
  <h1 id="latest">Kura ${escapeHtml(latest.version)}</h1>
  <p class="lede">Released ${escapeHtml(latest.date)} · Windows 10 and 11, 64-bit</p>
  <div class="actions">${downloadButton(latest)}
    <a class="button ghost" href="${escapeHtml(latest.page)}">Release on GitHub</a></div>
  ${fileLine(latest)}
</section>`;
}

function previous(older) {
  if (!older.length) return "";
  const rows = older
    .map(
      (version) => `<details class="version">
  <summary><span class="name">Kura ${escapeHtml(version.version)}</span><span class="date">${escapeHtml(version.date)}</span></summary>
  <div class="body">
    <div class="actions">${version.installer ? `<a class="button small" href="${escapeHtml(version.installer.browser_download_url)}">Download ${escapeHtml(version.version)}</a>` : ""}
      <a class="button small ghost" href="${escapeHtml(version.page)}">Release on GitHub</a></div>
    ${fileLine(version)}
    ${notesBlock(version)}
  </div>
</details>`,
    )
    .join("\n");
  return `<section class="panel" aria-labelledby="older"><h2 id="older">Earlier versions</h2>${rows}</section>`;
}

export function renderPage(releases, repository = `https://github.com/${REPOSITORY}`) {
  const all = versions(releases);
  const [latest, ...older] = all;
  const whatsNew = latest
    ? `<section class="panel" aria-labelledby="new"><h2 id="new">What's new in ${escapeHtml(latest.version)}</h2>${notesBlock(latest)}</section>`
    : "";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kura downloads</title>
<meta name="description" content="Download Kura for Windows: the latest version and every earlier one, with what changed.">
<link rel="icon" href="data:image/svg+xml,${encodeURIComponent(LOGO.replace(' width="32" height="32"', ""))}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500&family=Manrope:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    color-scheme: dark;
    --window: #0b0c0f; --glass: rgb(255 255 255 / 0.04); --edge: rgb(255 255 255 / 0.08);
    --fg: #f4f5f7; --fg-soft: #d7dae0; --fg-muted: #a3a8b3; --fg-faint: #7c818c;
    --accent: #f2b33d; --on-accent: #1d1300; --accent-fg: #ffd27a; --accent-fg-hover: #ffe1a6;
    --featured: #13254f; --orb: #f08a24; --sun: #ffcf6b;
    --sans: Manrope, system-ui, sans-serif; --mono: "Geist Mono", ui-monospace, monospace;
    --ease: cubic-bezier(.2, .8, .2, 1);
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--window); color: var(--fg); font: 15px/1.6 var(--sans); }
  a { color: var(--accent-fg); }
  a:hover { color: var(--accent-fg-hover); }
  main, header, footer { width: min(880px, 100% - 32px); margin-inline: auto; }
  header { display: flex; align-items: center; gap: 12px; padding: 28px 0 20px; }
  header .word { font-weight: 800; font-size: 20px; letter-spacing: -0.01em; }
  header nav { margin-left: auto; }
  header nav a { color: var(--fg-muted); text-decoration: none; font-weight: 600; }
  header nav a:hover { color: var(--fg); }
  main { display: grid; gap: 20px; }
  .hero { position: relative; overflow: hidden; background: var(--featured); border-radius: 24px;
    padding: 36px 32px; }
  .orb { position: absolute; right: -90px; top: -110px; width: 300px; height: 300px;
    border-radius: 50%; background: var(--orb); }
  .orb::after { content: ""; position: absolute; left: 70px; bottom: 60px; width: 64px; height: 64px;
    border-radius: 50%; background: var(--sun); }
  .hero > *:not(.orb) { position: relative; }
  .eyebrow { display: inline-block; margin: 0 0 14px; padding: 4px 12px; border-radius: 999px;
    background: rgb(255 255 255 / 0.1); font-size: 13px; font-weight: 700; }
  h1 { margin: 0; font-size: clamp(34px, 7vw, 52px); line-height: 1.05; font-weight: 800;
    letter-spacing: -0.02em; }
  .lede { margin: 10px 0 0; color: var(--fg-soft); max-width: 34em; }
  .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }
  .button { display: inline-flex; align-items: center; justify-content: center; min-height: 44px;
    padding: 0 22px; border-radius: 999px; font-weight: 800; text-decoration: none;
    border: 1px solid var(--edge); color: var(--fg); background: var(--glass);
    transition: transform 120ms var(--ease), background 120ms var(--ease); }
  .button:hover { color: var(--fg); background: rgb(255 255 255 / 0.08); }
  .button:active { transform: scale(0.97); }
  .button.primary { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
  .button.primary:hover { background: var(--accent-fg); color: var(--on-accent); }
  .button.small { min-height: 36px; padding: 0 16px; font-size: 14px; }
  .file { margin: 16px 0 0; display: grid; gap: 2px; font: 12px/1.6 var(--mono); color: var(--fg-muted); }
  .hash { overflow-wrap: anywhere; color: var(--fg-faint); }
  .panel { background: var(--glass); border: 1px solid var(--edge); border-radius: 20px; padding: 24px 28px; }
  h2 { margin: 0 0 6px; font-size: 20px; font-weight: 800; letter-spacing: -0.01em; }
  h3 { margin: 18px 0 4px; font-size: 13px; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--fg-muted); }
  ul { margin: 6px 0 0; padding-left: 20px; }
  li { margin: 4px 0; color: var(--fg-soft); }
  li::marker { color: var(--accent); }
  p { color: var(--fg-soft); }
  code { font: 13px var(--mono); background: rgb(255 255 255 / 0.06); padding: 1px 6px; border-radius: 6px; }
  details { margin-top: 14px; }
  summary { cursor: pointer; font-weight: 700; color: var(--fg); }
  summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 8px; }
  details li { font-size: 14px; }
  .version { border-top: 1px solid var(--edge); padding-top: 14px; }
  .version summary { display: flex; align-items: baseline; gap: 10px; list-style: none; }
  .version summary::-webkit-details-marker { display: none; }
  .version summary::before { content: ""; width: 7px; height: 7px; border: solid var(--fg-muted);
    border-width: 0 2px 2px 0; transform: rotate(-45deg); transition: transform 200ms var(--ease); }
  .version[open] summary::before { transform: rotate(45deg); }
  .version .date { margin-left: auto; }
  .version .date { color: var(--fg-muted); font: 13px/1.8 var(--mono); }
  .version .body { padding: 4px 0 6px; }
  .facts { display: grid; gap: 10px; margin: 8px 0 0; padding: 0; list-style: none; }
  .facts li { color: var(--fg-soft); margin: 0; }
  .facts strong { color: var(--fg); }
  footer { padding: 28px 0 48px; color: var(--fg-faint); font-size: 13px; }
  footer p { color: var(--fg-faint); margin: 4px 0; }
  @media (max-width: 560px) {
    .hero { padding: 28px 22px; }
    .orb { width: 180px; height: 180px; right: -100px; top: -110px; }
    .orb::after { left: 34px; bottom: 34px; width: 40px; height: 40px; }
    .panel { padding: 20px; }
  }
  @media (prefers-reduced-motion: reduce) { .button { transition: none; } }
</style>
</head>
<body>
<header>${LOGO}<span class="word">Kura</span><nav><a href="${repository}">GitHub</a></nav></header>
<main>
${hero(latest, repository)}
${whatsNew}
<section class="panel" aria-labelledby="before">
  <h2 id="before">Before you install</h2>
  <ul class="facts">
    <li><strong>Windows SmartScreen warns once.</strong> Kura isn't code-signed: choose More info, then Run anyway.</li>
    <li><strong>No admin rights needed.</strong> Kura installs for you alone, keeps its data apart, and never touches your anime files.</li>
    <li><strong>It updates itself.</strong> Once installed, Kura offers each new version and shows what changed.</li>
  </ul>
</section>
${previous(older)}
</main>
<footer>
  <p>Kura is free software under the <a href="${repository}/blob/main/LICENSE">MIT licence</a>.
  Each release carries the third-party notices for everything inside it.</p>
  <p>Kura contains no anime or artwork and isn't affiliated with Plex, TMDB, AniList or any show's owners.</p>
</footer>
</body>
</html>
`;
}

async function fetchReleases(repository) {
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "kura-downloads-page" };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const releases = [];
  for (let page = 1; ; page++) {
    const response = await fetch(`https://api.github.com/repos/${repository}/releases?per_page=100&page=${page}`, { headers });
    if (!response.ok) throw new Error(`GitHub answered ${response.status} for ${repository}'s releases.`);
    const batch = await response.json();
    releases.push(...batch);
    if (batch.length < 100) return releases;
  }
}

async function main() {
  const [folder, flag, file] = process.argv.slice(2);
  if (!folder) throw new Error("Usage: node scripts/downloads-page.mjs <folder> [--releases <file>]");
  const repository = process.env.GITHUB_REPOSITORY ?? REPOSITORY;
  const releases = flag === "--releases" ? JSON.parse(readFileSync(file, "utf8")) : await fetchReleases(repository);
  mkdirSync(folder, { recursive: true });
  writeFileSync(join(folder, "index.html"), renderPage(releases, `https://github.com/${repository}`));
  console.log(`Wrote the downloads page with ${versions(releases).length} versions.`);
}

const runDirectly = process.argv[1] && resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase();
if (runDirectly) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
