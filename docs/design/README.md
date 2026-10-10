# Kura's screens

Snapshots of the design canvases, as plain pages: open [index.html](index.html) in a browser and
click through. The canvases themselves are the source of truth:

- [Kura Workflows](https://claude.ai/artifact/XgGkfpW6doBUPcnrPqrbxb): every screen in Cinema.
- [Design Language Options](https://claude.ai/artifact/NWe6abnPRYCn6BGTVK25za): the three
  directions explored, Cinema chosen, and the eight rules they all share ([options.html](options.html)).

| Board | Page |
| --- | --- |
| Overview: every workflow and the Cinema language | [index.html](index.html) |
| 1.1 Set up in four steps | [screens/01-setup.html](screens/01-setup.html) |
| 1.2 First scan | [screens/02-scan.html](screens/02-scan.html) |
| 2.1 Library home | [screens/03-home.html](screens/03-home.html) |
| 2.2 A title: gaps, report and history | [screens/04-title.html](screens/04-title.html) |
| 3.1 Tidy up: review changes | [screens/05-tidy.html](screens/05-tidy.html) |
| 3.2 Fix a match | [screens/06-match.html](screens/06-match.html) |
| 4.1 Convert: choose and preview | [screens/07-convert.html](screens/07-convert.html) |
| 4.2 Queue | [screens/08-queue.html](screens/08-queue.html) |
| 4.3 History and reports | [screens/09-history.html](screens/09-history.html) |
| 5.1 Settings: your data | [screens/10-settings.html](screens/10-settings.html) |
| 5.2 Update and uninstall | [screens/11-uninstall.html](screens/11-uninstall.html) |
| 5.3 The small things | [screens/12-states.html](screens/12-states.html) |

The sample library is illustrative: episode counts are real, while file states, timings and sizes
are estimates for a GTX 1660 Super. Fonts load from Google Fonts, so pages need the internet to
look exactly right.

## Building from these

The markup is plain HTML with inline styles, so every size, colour and spacing can be read off
directly. Map the values to the tokens in `app/src/styles/tokens.css` (they match one for one),
reuse the components in `app/src/components/`, and keep each screen's states.

## Refreshing the snapshot

The pages are generated; don't edit them. When a canvas changes, ask Claude to read both canvases
(their `project/` files) into a folder each, then run:

```powershell
node scripts/design-snapshot.mjs <workflows-folder> <options-folder>
```

The script expands each board's repeated parts with the board's own sample data and rewrites the
links between boards.
