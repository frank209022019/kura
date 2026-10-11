# watchdog (noticing changes in the library folders)

[watchdog](https://github.com/gorakhargosh/watchdog) 6.0 (Apache-2.0) tells Kura when a file in a
library folder is added, removed, renamed or written, the moment Windows knows
(`ReadDirectoryChangesW`), without walking the folders on a timer. Walking every few minutes would
keep sleeping disks awake; being told costs nothing.

## How Kura uses it

[kura/watch.py](../../engine/src/kura/watch.py) runs inside `kura serve` (`create_app(...,
watch=True)`; tests leave it off):

- **At start** it catches up: a scan for whatever changed while Kura was closed, once setup is done
  and there are folders, unless a scan is running or the owner paused one.
- **Watching**: one watchdog observer per library folder that's there (`recursive=True`), followed
  as folders are added and forgotten; a folder on an unplugged drive is watched once it's back.
  Only videos (by extension) and folders count. When something changed, a scan starts once the
  folder has been quiet for 10 seconds, so a season still copying waits until it's done. A scan the
  owner paused stays paused.
- **Refreshing**: while no scan runs, episode lists that are due are asked for again (hourly for
  shows still airing, weekly for finished ones), and the gap reports follow. Offline, they wait
  for the next look.

It looks around every 15 seconds. Anything that goes wrong in one look is logged, and the next
look carries on.

## Notes

- Windows takes a moment after an observer starts before it reports changes; the catch-up scan at
  start covers anything that happens in that moment.
- A file write raises "created" and then "modified": both count as the same change, and the quiet
  period runs from the last one.
- PyInstaller bundles watchdog without help; `tests/test_cli.py` (with `KURA_ENGINE_EXE`) starts
  the bundled engine, which imports it.
