# anitopy (reading file names)

[anitopy](https://github.com/igorcmoura/anitopy) 2.1.1 turns an anime file name into its parts:
title, episode number, season, year, release group, resolution. It is a Python port of Anitomy,
the parser behind Taiga, and knows fansub and scene naming. Kura wraps it in
[`kura/core/names.py`](../../engine/src/kura/core/names.py) and adds its own rules.

## Why anitopy

On 2026-10-10 three parsers read the same 33 real-world names (the design boards' examples plus
common fansub and scene patterns):

| | Good at | Wrong on |
| --- | --- | --- |
| **anitopy 2.1.1** (chosen) | Absolute numbers (`Yu Yu Hakusho 112`, `HxH (2011) - 148`, `Dragon Ball - 001`), groups, resolutions | Type words left in titles (`Hellsing Ultimate OVA`, `Cowboy Bebop - Session`), bare `05.mkv` |
| guessit 4.4 | Scene names, stripping type words | Turns absolute numbers into seasons (`112` → S01E12, `001` → season 0, `(2011)` → season 2011): dangerous for anime |
| aniparse 2.0 | Uses folder names | Loses episodes in `Death_Note_07`, scene `S01E131`, and `Kai - 98 - The Final Battle` |

anitopy hasn't had a release since 2022, but it is small, pure Python, and does the hard part best.
Kura's rules cover its gaps, and the tests pin the behaviour, so swapping parsers later is safe.

## What Kura adds

- **Folders.** A `Season 03` or `Specials` folder gives `folder_season`; the show folder above it
  (`Dragon Ball Z (1989)`) gives `folder_title` and the year. General folders (`Downloads`,
  `Extras`, `TV`…) never count as titles.
- **Copies.** `(copy)`, ` - Copy` and ` (2)` are removed before parsing and set `is_copy`.
- **Kinds.** Episode, special (OVA, season 0, a PSA), movie (no episode number), extra (NCOP,
  NCED, PV) or DVD file (`VTS_01_1.VOB`).
- **Clean titles.** Type and release words at the end of the title (`OVA`, `Movie`, `Session`,
  `final`) are removed; a title that is only a number becomes the episode.
- **Numbered films.** A whole series' release numbers its films: `Dragon Ball Z - Movie 03 - The
  Tree of Might`. anitopy reads no number after `Movie`, so that's all title to it; with a letter
  (`Movie 14b`) it takes the number for an episode's and the film's name for the episode's title.
  Either way Kura makes it a film titled `Dragon Ball Z: The Tree of Might`, with `series`
  `Dragon Ball Z`, leaving out what the release adds after the name (`aka Frieza`, a comma). The
  release's number counts its own films, not AniList's.
- **Years in brackets.** `(1990 BluRay - 1080p)` gives the year, which anitopy passes over; a span
  (`1989-2019`) or a checksum doesn't.
- File-name values (`title`, `season`) and folder values (`folder_title`, `folder_season`) stay
  apart, because they can disagree: `Season 07\Naruto Shippuden - 143.mkv` has an absolute episode
  number. Matching decides.

## Things to know

- anitopy keeps its state in module globals, so `parse_name` takes a lock; never call
  `anitopy.parse` directly.
- anitopy ships no types; `engine/typings/anitopy/__init__.pyi` declares the one function Kura uses.
- Add every name that parses wrongly to `engine/tests/core/test_names.py` before fixing it.
