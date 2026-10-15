# Kura's screens

Snapshots of the design canvases, as plain pages: open [index.html](index.html) in a browser and
click through. The canvases themselves are the source of truth (they are the owner's, and
private; these snapshots are the shared copy):

- [Kura Workflows](https://claude.ai/artifact/XgGkfpW6doBUPcnrPqrbxb): every screen in Cinema.
- [Design Language Options](https://claude.ai/artifact/NWe6abnPRYCn6BGTVK25za): the three
  directions explored, Cinema chosen, and the eight rules they all share ([options.html](options.html)).
- [Kura Light Mode Options](https://claude.ai/artifact/7Bdz7CoKjBbV8JrSLXfu4y): three lights for
  Cinema, Paper chosen ([light-options.html](light-options.html)), and Home and the queue in
  Paper ([light.html](light.html)) and in Cinema's dark beside it ([dark.html](dark.html)). Every
  other screen in light follows from the tokens.
- [Kura Player](https://claude.ai/artifact/3MK2zSwv9fS1jzt2rP7Qw3): the small player inside Kura,
  over the page and moved anywhere, full screen, in light, for a quick check, and its small
  things ([player.html](player.html) and the pages after it). On the canvas the small player
  drags; in the snapshot it sits where it starts.
- [Kura README Options](https://claude.ai/artifact/SJXeVqCrbCZPHk5Y17p7jk): three drafts of the
  repo's README, B (a tour) chosen ([readme.html](readme.html)). Its pictures are the README's
  own, in [../readme/](../readme/).

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
| Light mode: Paper, Home and the queue | [light.html](light.html) |
| The same in Cinema's dark, to set beside it | [dark.html](dark.html) |
| Light mode: the three options | [light-options.html](light-options.html) |
| The small player, over a title's page | [player.html](player.html) |
| The player full screen, sound and subtitles open | [player-full.html](player-full.html) |
| The small player in light | [player-light.html](player-light.html) |
| A quick check on "Which anime is this?" | [player-check.html](player-check.html) |
| The player's small things | [player-states.html](player-states.html) |
| The README: three drafts, the tour chosen | [readme.html](readme.html) |

The sample library is made up: its titles, episodes and files are invented (Starfall Academy and
the like, as in the README's pictures), and file states, timings and sizes are estimates for a
GTX 1660 Super. The boards name no media server app either. Fonts load from Google Fonts (and the
README options' Markdown reader from cdnjs), so pages need the internet to look exactly right.

## Building from these

The markup is plain HTML with inline styles, so every size, colour and spacing can be read off
directly. Map the values to the tokens in `app/src/styles/tokens.css` (they match one for one),
reuse the components in `app/src/components/`, and keep each screen's states.

## Refreshing the snapshot

The pages are generated; don't edit them. When a canvas changes, ask Claude to read it (its
`project/` files) into a folder, then run the script with the canvases read, one or more (the
README options are a plain page: give the file a read of it saves):

```powershell
node scripts/design-snapshot.mjs --workflows <folder> --options <folder> --light <folder> --player <folder> --readme <page>
```

The script expands each board's repeated parts with the board's own sample data and rewrites the
links between boards.

## The README's pictures

[../readme/](../readme/) holds them, at 1280 × 800: Kura's own screens rendered from its tests,
with the tests' titles swapped for made-up ones. No real series, artwork or video is in any of
them: posters are Kura's placeholders and the player's picture is a stand-in. Every picture of
Kura that goes public keeps to that. To refresh them, ask Claude. `download.svg` is the README's
download button, Cinema's amber pill with its words in Manrope ExtraBold drawn as outlines, so it
looks the same wherever the README is read.
