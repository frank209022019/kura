# Docs: guide for coding agents

Kura's docs are short pages, one subject each, written for the owner and for agents. Start with
[../AGENTS.md](../AGENTS.md).

## Rules

- **Lean.** Say it once, in the right place, in plain short sentences. Use tables for lookups and
  code blocks for commands. No filler, no marketing, no history of how a page came to be.
- **Same commit as the code.** A change that alters how something works updates its doc too.
- **Every tool has a page** in `stack/`: what Kura uses it for, the files, the patterns, the
  commands, gotchas and upgrading. New tool, new page (or a section in the closest page), plus a
  row with its version in the table in [README.md](README.md).
- **Decisions live in [CLAUDE.md](../CLAUDE.md)**, the owner's preferences included. Docs explain
  how things work; CLAUDE.md records what was decided.
- **Links are relative** and must resolve; anchors too.
- **`design/` is generated.** `scripts/design-snapshot.mjs` writes it from the design canvases;
  never edit those pages by hand. When the canvas changes, refresh them (see
  [design/README.md](design/README.md)) and keep `design/preview.png` in step.

## Where things go

| Subject | Page |
| --- | --- |
| How the parts fit and talk | `architecture.md` |
| Setting up, running, checking, updating dependencies | `development.md` |
| How code is written | `conventions.md` |
| How Kura looks and behaves | `design.md` |
| Versions, installer, updates, the signing key | `releasing.md` |
| One tool, in depth | `stack/<tool>.md` |
