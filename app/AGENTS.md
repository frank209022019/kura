# App UI: guide for coding agents

The UI lives in `app/src`: React 19, TypeScript 7, Tailwind 4, built by Vite. The Rust shell in
`app/src-tauri` has [its own guide](src-tauri/AGENTS.md). Start with [../AGENTS.md](../AGENTS.md)
and [../CLAUDE.md](../CLAUDE.md).

## Build to the design

- Every screen has a board in `docs/design/screens/`. Match it: layout, spacing, copy, states.
  Its inline values map one to one to the tokens in `src/styles/tokens.css`.
- Use only Cinema tokens. Tailwind's own palette and scales are switched off on purpose; if a
  value isn't a token, ask the owner before adding one.
- One primary (amber) action per view; the rest are secondary or ghost buttons.
- Every screen designs its loading, empty and error states, following the "small things" board:
  name the problem, say what Kura did, offer the next step.
- Motion: `ease-cinema`, 120 / 200 / 320 ms, `animate-fade-up` for entrances. Reduced motion is
  handled globally; don't work around it.
- Accessible as built: real `<button>` and `<a>`, labels on icon-only buttons, visible focus, a
  keyboard path for everything, `role="alert"` or `role="status"` for messages that appear.
- Only the page scrolls. A page starts with its top, its header or a breadcrumb, carrying
  `page-top`, so it stays put while the rest scrolls under it.
- Say what a thing does, never which media server reads it: no "Plex" anywhere in the UI.
- Markdown (Kura's reports) shows through `components/markdown.tsx`, as a reader sees it.
- Deleting asks first, beside what goes (`components/delete.tsx`, on a title's page and on "Which
  anime is this?"), says where it goes and for how long, and offers it back right after. Nothing is ever deleted outright; emptying a drive's
  quarantine early to make room (`features/convert/no-room.tsx`) asks once more and says it can't
  come back.
- While Kura's records are damaged, the way back (`features/records/`) stands in for every page
  (`components/shell/app-shell.tsx`): the engine answers nothing else.

## Where things go

| What | Where |
| --- | --- |
| A screen and its parts | `src/features/<area>/` (`home/`, then `tidy/`, `convert/`, …) |
| Shared primitives (buttons, switches, dialogs…) | `src/components/ui/` |
| The window frame (title bar, nav rail, update card, the notes at its foot) | `src/components/shell/` |
| Talking to the engine and the shell | `src/lib/engine.tsx`, `src/lib/updates.ts` |
| Tokens and global styles | `src/styles/` |
| Routes | `src/app.tsx`; nav items, and the one a new page lights (`sectionOf`), in `src/components/shell/sections.ts` |

## Data

- Engine data comes only through `src/lib/engine.tsx`: add a typed hook per endpoint
  (`export const useLibrary = () => useEngineQuery<Library>("/library")`), with its type mirroring
  `engine/openapi.json`. Changes use `useMutation` and invalidate the queries they affect.
- No `fetch` or `invoke` outside `src/lib/`.
- Local state stays in components. Add a global store only when two distant screens truly share
  client-side state.

## Components

- Reuse what exists (`Button`, `EmptyState`, and `EngineProblem` for a screen whose data didn't
  come) before adding anything.
- New primitives start from shadcn/ui (`pnpm dlx shadcn@latest add <name>`) and are restyled to
  Cinema with the mapping in [docs/stack/tailwind.md](../docs/stack/tailwind.md). They live in
  `src/components/ui/` and open with a comment naming shadcn/ui and `LICENSE-shadcn.txt`.
- A new npm package needs a licence on the allowed list in
  `engine/tools/third_party_notices.py`; `pnpm build:installer` stops otherwise.
- Merge classes with `cn()`. New font sizes or radii also go in `fontSizes` and `radii` in
  `src/lib/utils.ts` (a test checks).
- Icons from `lucide-react`; decorative ones get `aria-hidden="true"`.

## Commands

```powershell
pnpm tauri dev      # run Kura (UI with hot reload, shell, engine)
pnpm check          # Biome, TypeScript, Vitest
pnpm fix            # format and apply safe lint fixes
pnpm test:watch     # tests while you work
```

## Done means

`pnpm check` and `pnpm build` are green; the screen matches its board and works in the running app
with its loading, empty and error states; tests cover what a person sees and does. Guides:
[react.md](../docs/stack/react.md), [tailwind.md](../docs/stack/tailwind.md),
[design.md](../docs/design.md), [testing.md](../docs/stack/testing.md).
