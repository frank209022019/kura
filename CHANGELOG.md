# Changelog

Every change to Kura you'd notice, newest first. Versions follow
[semantic versioning](https://semver.org): a new major number means something you have to act on,
a new minor number brings features, a new patch number fixes things. Every version can be
downloaded from the [downloads page](https://frankgrobbelaar.github.io/kura/), and an installed Kura
shows these notes when it offers the update.

## Unreleased

### Added
- Tidy up: Kura proposes where every identified video goes for Plex (`TV\Show (Year)\Season 01`,
  `Movies\Title (Year)`), title by title: moves out of folders holding several anime, renames in
  place, and second copies of an episode set aside in a quarantine folder on the same drive, the
  two compared with a swap if you'd rather keep the other. Leave out any title, then apply.
  Subtitles move with their video, emptied folders go, and every video keeps what it was
  identified as. A film in two files (CD1, CD2) is filed as its two parts. Applying makes
  exactly what you reviewed, or asks you to look again if a scan changed it, and waits while a
  scan runs.
- History: every tidy-up and scan by day, newest first. Any tidy-up can be undone there (or right
  after applying it), putting every file back; a file that couldn't go back can be tried again.
- Home lists every franchise and series as poster cards, oldest release first, or by name,
  newest added or most missing. A franchise (Dragon Ball's series, films, OVAs and specials) is
  one card with a page of its own that lists them the same ways. Each says whether it's a TV
  series, movie, OVA or special, and how much of it is there.
- Home's "Needs your attention": files that need a match, episodes missing, files that won't play
  and folders holding mixed anime, each leading to what to do.
- A page for each anime: how much of it is there, its seasons and episode map with every
  episode's state by shape, the missing and broken episodes (a long run of missing ones as one
  range), its specials and OVAs apart, its videos, and the gap analysis written next to it (shown
  in its folder or copied). "Open folder" opens its folder in Explorer, and "Change match" picks
  another anime for all its files at once: specials stay specials, and a file that doesn't fit
  the new anime waits for you, the title page says how many.
- Scans identify every video: which anime, movie, OVA or special it is and, with a TMDB key,
  which season and episode, numbered as Plex shows them. Files Kura isn't sure about wait for you
  instead of being guessed. Offline, the scan still finishes and identifies them next time.
- The scan screen follows every stage: finding, reading, identifying each anime, checking for
  gaps and writing the reports, with the anime found so far (artwork and all, oldest release
  first), the files that need a match, folders with mixed anime and broken files.
- "Which anime is this?": for each file Kura couldn't place surely, its stills, length, picture,
  languages and group tag beside Kura's best guesses (press 1, 2 or 3), a search for another,
  whether it's an episode, a movie or a special, and which episode when its name doesn't say. One
  choice can cover the other files from the same release, and it's remembered, so a rescan never
  undoes it. "Not anime" leaves a file out for good.
- A gap analysis next to each anime that has a folder of its own (`Kura - Gap analysis.md`): the
  episodes TMDB lists as aired that the library doesn't hold (without a TMDB key, AniList's count
  of the episodes aired so far), a run of them as one range, with specials and OVAs listed apart
  and never counted as missing.
- Kura keeps the library current while it's open: it catches up at start on what changed while it
  was closed, notices videos and folders added, removed or renamed in your library (and a drive
  plugged back in) and scans once copying is done, and checks for new episodes every hour for
  shows still airing (weekly for finished ones).
- Setup takes your TMDB key, for episode lists, episode titles and artwork. It's optional: Kura
  checks the key with TMDB, then keeps it on this PC only, encrypted for your Windows account and
  never in an export. Home says whether TMDB is connected, and a key added later sorts what's
  already matched into TMDB's seasons.
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
