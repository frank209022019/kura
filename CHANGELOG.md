# Changelog

Every change to Kura you'd notice, newest first. Versions follow
[semantic versioning](https://semver.org): a new major number means something you have to act on,
a new minor number brings features, a new patch number fixes things. Every version can be
downloaded from the [downloads page](https://frankgrobbelaar.github.io/kura/), and an installed Kura
shows these notes when it offers the update.

## Unreleased

### Added
- First-run setup in four steps: where Kura keeps its data, your anime folders, your standard and
  how files are named, and the tools Kura needs, with a quick check of the graphics card.
- Kura downloads ffmpeg (77 MB) the first time it needs it, and uses it only after checking it
  matches what Kura expects.
- Scanning: Kura finds every video in your folders, whatever their layout, and reads each one's
  length and quality. A scan can pause, carries on after a restart, and later scans only read
  what's new or changed. Nothing in your folders is renamed or moved.
- Home shows your library at a glance: how many videos, how big, and how many are SD, 720p, 1080p
  or larger.
- The export now includes a list of every video in your library.
- A screen that fails to draw says so and offers to reload, instead of going blank.
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
