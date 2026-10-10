// Turns the design canvases' boards (.dc.html) into plain HTML pages in docs/design/,
// so every screen opens in a browser without the canvas.
//
//   node scripts/design-snapshot.mjs <workflows-canvas-folder> <options-canvas-folder>
//
// Each folder is a canvas as Claude's Artifact tool saves it (it holds project/canvas.json).
// See docs/design/README.md.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const CANVASES = {
  workflows: "https://claude.ai/artifact/XgGkfpW6doBUPcnrPqrbxb",
  options: "https://claude.ai/artifact/NWe6abnPRYCn6BGTVK25za",
};
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "docs", "design");
const today = new Date().toISOString().slice(0, 10);

const [workflowsDir, optionsDir] = process.argv.slice(2);
if (!workflowsDir || !optionsDir) {
  console.error("Usage: node scripts/design-snapshot.mjs <workflows-canvas> <options-canvas>");
  process.exit(1);
}

// The workflows canvas: Main becomes index.html, every other board a page in screens/.
const workflows = readCanvas(workflowsDir);
mkdirSync(join(out, "screens"), { recursive: true });
for (const file of workflows.order) {
  const name = file.replace(".dc.html", "");
  const isIndex = name === "Main";
  const page = toPage(workflows, file, {
    canvas: CANVASES.workflows,
    link: (target) => (isIndex ? `screens/${target}.html` : `${target}.html`),
  });
  writeFileSync(join(out, isIndex ? "index.html" : `screens/${name}.html`), page);
}

// The options record: its Main board becomes options.html. It links to boards that
// were folded into the workflows canvas, so those links go to the overview.
const options = readCanvas(optionsDir);
writeFileSync(
  join(out, "options.html"),
  toPage(options, "Main.dc.html", { canvas: CANVASES.options, link: () => "index.html" }),
);

console.log(`Wrote ${workflows.order.length + 1} pages to ${out}`);

function readCanvas(folder) {
  const index = JSON.parse(readFileSync(join(folder, "project", "canvas.json"), "utf8"));
  const source = (file) => readFileSync(join(folder, "project", file), "utf8");
  return { ...index, source };
}

function toPage(canvas, file, { canvas: url, link }) {
  const source = canvas.source(file);
  const title = canvas.boards[file]?.title ?? file;
  const helmet = source.match(/<helmet>([\s\S]*?)<\/helmet>/)?.[1] ?? "";
  const board = source
    .match(/<x-dc>([\s\S]*?)<\/x-dc>/)[1]
    .replace(/<helmet>[\s\S]*?<\/helmet>/, "");
  const body = expand(board, renderValues(source)).replace(
    /href="([\w.-]+)\.dc\.html"/g,
    (_, target) => `href="${link(target)}"`,
  );
  return `<!doctype html>
<!-- Kura design snapshot of "${title}" (${url}), taken ${today}.
     Change the canvas, then re-run scripts/design-snapshot.mjs; don't edit this file. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title} · Kura design</title>
${helmet.trim()}
</head>
<body>
${body.trim()}
</body>
</html>
`;
}

// A board's script builds the data its template repeats over. It only computes
// values, so it runs in an empty sandbox with nothing but the base class it needs.
function renderValues(source) {
  const script = source.match(/<script type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/)?.[1];
  if (!script) return {};
  const sandbox = vm.createContext({
    DCLogic: class {
      props = {};
    },
  });
  return vm.runInContext(`${script}\n;new Component().renderVals()`, sandbox, { timeout: 1000 });
}

// Expands <sc-for>, <sc-if> and {{holes}} the way the canvas renders them.
function expand(html, scope) {
  let result = "";
  let rest = html;
  for (;;) {
    const open = rest.match(/<sc-(for|if)\b([^>]*)>/);
    if (!open) return result + fillHoles(rest, scope);
    const [tag, kind, attributes] = open;
    const close = findClose(rest, kind, open.index + tag.length);
    const inner = rest.slice(open.index + tag.length, close);
    const binding = (name) =>
      attributes.match(new RegExp(`${name}="\\{\\{([^}]+)\\}\\}"`))?.[1].trim();

    result += fillHoles(rest.slice(0, open.index), scope);
    if (kind === "for") {
      const as = attributes.match(/as="([^"]+)"/)[1];
      for (const item of lookup(scope, binding("list")) ?? []) {
        result += expand(inner, { ...scope, [as]: item });
      }
    } else if (lookup(scope, binding("value"))) {
      result += expand(inner, scope);
    }
    rest = rest.slice(close + `</sc-${kind}>`.length);
  }
}

function findClose(html, kind, from) {
  const tags = new RegExp(`<sc-${kind}\\b|</sc-${kind}>`, "g");
  tags.lastIndex = from;
  let depth = 1;
  for (let tag = tags.exec(html); tag; tag = tags.exec(html)) {
    depth += tag[0].startsWith("</") ? -1 : 1;
    if (depth === 0) return tag.index;
  }
  throw new Error(`<sc-${kind}> is never closed`);
}

function fillHoles(html, scope) {
  return html.replace(/\{\{([^}]+)\}\}/g, (_, path) => escapeHtml(lookup(scope, path.trim()) ?? ""));
}

function lookup(scope, path) {
  return path.split(".").reduce((value, key) => value?.[key], scope);
}

function escapeHtml(value) {
  const entities = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
  return String(value).replace(/[&<>"]/g, (character) => entities[character]);
}
