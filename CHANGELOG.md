# Changelog

Every change to Kura you'd notice, newest first. Versions follow
[semantic versioning](https://semver.org): a new major number means something you have to act on,
a new minor number brings features, a new patch number fixes things. Every version can be
downloaded from the [downloads page](https://frankgrobbelaar.github.io/kura/), and an installed Kura
shows these notes when it offers the update.

## Unreleased

### Added
- A file open in another app (a player playing it) as its conversion finishes no longer fails:
  the queue says so, keeps the converted copy beside it, goes on with the next file, and puts the
  copy in place once the app lets go, trying every 5 minutes or at once with Try now. Skip this
  file throws the copy away. A tidy-up that meets a file open elsewhere says so in Kura's words.
- Poster and background pictures next to each show and film (Settings > Your data, off unless you
  turn it on): `poster.jpg` and `fanart.jpg`, which media servers show. Kura never writes over a
  picture that's there, and turning it off takes away only the ones it wrote, unchanged. Change
  a match, and Kura's pictures of the old title make way for the new one's.
- Import an export (Settings > Your data), from this PC or another: Kura's records become the
  export's as its engine starts again, and what it knew till then is backed up first, so
  Backups can bring it back.
- Move Kura's data to another drive (Settings > Your data): Kura copies it, checks the copy, and
  only then removes the old one, as its engine starts again, however long that takes. A move cut
  short (a power cut) is settled when Kura next starts. A folder on another computer isn't
  taken: the data needs a drive of this PC's own (an external one is fine). If the drive it's on isn't connected,
  Kura says so instead of starting empty, and uninstalling cleans up only Kura's own files
  there.
- Start with Windows (Settings > General): Kura waits in the tray, so the queue, the nightly
  backup and the watching carry on, and closing the window keeps it there. While it's in the
  tray, a Windows notification says when a batch is done ("Trigun, season 1 is done · 26
  episodes · all checked") or when a full drive paused the queue; a click opens Kura. With the
  window open, the same shows as a note at its foot, with View leading to the title (or History,
  or the queue). If Kura can't run there (its data's drive isn't connected yet, say), a
  notification says why, and it tries again by itself.
- Delete a title, a season or one video from its page. Kura asks first, then moves the videos and
  their subtitles to the quarantine on their drive, for as long as you keep copies set aside; the
  page, right after, or History puts them back. A video another app has open stays (the page
  says so), and subtitles another copy of it shares stay with that copy.
- Only the page scrolls: the nav rail and the page's title (or where it sits) stay where they
  are, and so does Settings' list of sections.
- A title's gap analysis reads like a document (headings, lists and tables), under the title Gap
  Analysis.
- Files are named "Clean names" or "Keep my names": Kura's words don't name a media server.
- Backups: every night at 03:00 (or the first chance after), Kura backs up its records, keeping
  the last 7, each checked as it's made and never written over. Settings shows the last one,
  makes one now (kept apart from the nightly ones), and restores one: the backup is checked
  first, Kura's records go back to then, your files stay as they are, and what Kura knew till
  then is backed up first, even when it doesn't check out.
- What waited in quarantine longer than you keep it (30 days unless you choose otherwise) is
  cleared out once a day while Kura is open. A converted file's original goes only once its
  converted copy is in place. Whatever its records say, Kura deletes nothing but what's in its
  quarantine folders, its own unfinished copies and its own pictures.
- Settings: your anime folders, the standard and how files are named (changed at once), the
  TMDB key, where Kura's data lives and how big each part is, the export to a folder you pick,
  whether a gap report goes next to each anime, how long copies set aside are kept, updates, and
  what Kura is made of.
- Convert: choose what to convert (a franchise, a title, or some of its seasons) and how: Best
  quality with the AI model for SD, Fast with Anime4K, or only a re-encode. See it first: a frame
  of one file before and after, at three points, with a handle to drag between them. Before
  queueing, it says what that takes: GPU time, size before and after, and whether each drive has
  room. Queue it to start now, on nights only, or after what's waiting. Every file goes to your
  standard, and none gets more than suits it (the AI model is for SD).
- The queue converts one file at a time while Kura is open, showing the graphics card's load and
  temperature. Pause it (Space), skip a file, move one up, take one out, or run it on nights only
  (23:00 to 07:00). Each result is checked (length, streams, a test play) before it takes its
  original's place; the original waits in quarantine for 30 days and can be put back from
  History, which lists every conversion with what it made. A file whose drive isn't connected
  waits while the others go, a drive without room for the result pauses the queue and says so,
  and a file whose new name is taken (an MKV beside an MP4 of the same name) says so before
  converting. Paused once its result is made, a file is still checked and put in place, and a
  file saved over while it converts keeps what was saved. Kura keeps the PC awake while a file
  converts, and nothing it starts keeps running once it's closed.
- Tidy up: Kura proposes where every identified video goes (`TV\Show (Year)\Season 01`,
  `Movies\Title (Year)`), title by title: moves out of folders holding several anime, renames in
  place, and second copies of an episode set aside in a quarantine folder on the same drive, the
  two compared with a swap if you'd rather keep the other. Leave out any title, then apply.
  Subtitles move with their video (and stay with one that couldn't move), emptied folders
  go, and every video keeps what it was identified as. A film in two files (CD1, CD2) is
  filed as its two parts. With "Keep my names", files move into the same folders under the
  names they have. Applying makes
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
- Offline, Kura says so at the foot of the window: new titles and artwork fill in once the PC is
  back online, and everything else keeps working.
- After Kura closed unexpectedly (a crash, a power cut), Home says what it settled as it started
  again ("One file was restarted from the beginning; the original was never touched and nothing
  was lost."), with the way to History.
- A page for each anime: how much of it is there, its seasons and episode map with every
  episode's state by shape, the missing and broken episodes (a long run of missing ones as one
  range), its specials and OVAs apart, its videos, and the gap analysis written next to it (shown
  in its folder or copied). "Open folder" opens its folder in Explorer (or says why it can't),
  and "Change match" picks another anime for all its files at once: specials stay specials, and a
  file that doesn't fit the new anime waits for you, the title page says how many.
- Scans identify every video: which anime, movie, OVA or special it is and, with a TMDB key,
  which season and episode, numbered as TMDB lists them. Files Kura isn't sure about wait for you
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
