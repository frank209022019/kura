# Changelog

Every change to Kura you'd notice, newest first. Versions follow
[semantic versioning](https://semver.org): a new major number means something you have to act on,
a new minor number brings features, a new patch number fixes things. Every version can be
downloaded from the [downloads page](https://frankgrobbelaar.github.io/kura/), and an installed Kura
shows these notes when it offers the update.

## Unreleased

### Added
- Home lists every anime and film as poster cards, oldest release first, or by name, newest
  added or most missing. Each says whether it's a TV series, movie, OVA or special, and how much
  of it is there.
- Home's "Needs your attention": files that need a match, episodes missing, files that won't play
  and folders holding mixed anime, each leading to what to do.
- A page for each anime: how much of it is there, its seasons and episode map with every
  episode's state by shape, the missing and broken episodes, its specials and OVAs apart, its
  videos, and the gap analysis written next to it.
- Scans identify every video: which anime, movie, OVA or special it is and, with a TMDB key,
  which season and episode, numbered as Plex shows them. Files Kura isn't sure about wait for you
  instead of being guessed. Offline, the scan still finishes and identifies them next time.
- The scan screen follows every stage: finding, reading, identifying each anime, checking for
  gaps and writing the reports, with the anime found so far (artwork and all, oldest release
  first), the files that need a match, folders with mixed anime and broken files.
- "Which anime is this?": for each file Kura couldn't place surely, its stills, length, picture,
  languages and group tag beside Kura's best guesses (press 1, 2 or 3), a search for another, and
  whether it's an episode, a movie or a special. One choice can cover the other files from the
  same release, and it's remembered, so a rescan never undoes it. "Not anime" leaves a file out
  for good.
- A gap analysis next to each anime that has a folder of its own (`Kura - Gap analysis.md`): the
  episodes TMDB lists as aired that the library doesn't hold, with specials and OVAs listed apart
  and never counted as missing.
- Kura keeps the library current while it's open: it catches up at start on what changed while it
  was closed, notices new, removed and renamed videos in your folders and scans once copying is
  done, and checks for new episodes every hour for shows still airing (weekly for finished ones).
- Setup takes your TMDB key, for episode lists, episode titles and artwork. It's optional: Kura
  checks the key with TMDB, then keeps it on this PC only, encrypted for your Windows account and
  never in an export. Home says whether TMDB is connected.
- First-run setup in four steps: where Kura keeps its data, your anime folders, your standard and
  how files are named, and the tools Kura needs, with a quick check of the graphics card.
- Kura downloads ffmpeg (77 MB) the first time it needs it, and uses it only after checking it
  matches what Kura expects. If a part of it goes missing or it stops working, Kura offers the
  download again.
- The installer's first page lists everything Kura downloads to your PC, with what each is for,
  its size, licence and source.
- Scanning: Kura finds every video in your folders, whatever their layout, and reads each one's
  length and quality. A scan can pause, carries on after a restart, and later scans only read
  what's new or changed, plus any file that couldn't be read last time. Nothing in your folders
  is renamed or moved.
- Home shows your library at a glance: how many videos, how big, and how many are SD, 720p, 1080p
  or larger.
- The export now includes a list of every video in your library.
- A screen that fails to draw, or whose data Kura's engine couldn't give, says so and offers to
  try again, instead of going blank.
- Kura's window in the Cinema design, with its own title bar. Starting Kura a second time brings
  the open window forward.
- The engine that does Kura's work starts and stops with the window, and Kura notices if it stops
  on its own and starts it again.
- Kura updates itself: it checks once a day, downloads a new version in the background, shows
  what's new in it, and asks before restarting.
- Every version and what changed in it are on the downloads page, which the update card and the
  Home page open.
- Export: one zip with Kura's database, settings, every file change and a manifest.
- The installer puts Kura in your user folder without admin rights, offers an export before
  uninstalling, and never touches your anime files.
- A third-party notices file next to Kura lists every open-source part inside it, with its licence.
