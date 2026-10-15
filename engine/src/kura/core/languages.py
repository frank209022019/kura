"""The languages a video can be heard and read in: its sound tracks', its subtitle tracks', and
those of subtitle files beside it ("Episode 1.en.srt"), and whether English is among them."""

from collections.abc import Iterable, Sequence
from pathlib import PurePath

_ENGLISH = frozenset({"eng", "en", "english"})
# Words a subtitle file's name carries besides its language: "Episode 1.en.forced.srt", and
# "Episode 1.kura.en.srt", Kura's own when another file has the first name.
_FLAGS = frozenset({"forced", "sdh", "cc", "hi", "default", "full", "signs", "kura"})


def is_english(language: str) -> bool:
    """English, however a file names it: "eng", "en", "English", "en-US"."""
    code = language.casefold()
    return code in _ENGLISH or code.startswith(("en-", "en_"))


def track_languages(languages: Iterable[str | None]) -> list[str]:
    """Each track's language as Kura keeps it: "jpn", or "" for one that doesn't say."""
    return [(language or "").casefold() for language in languages]


def beside_language(subtitle: PurePath, video: PurePath) -> str:
    """The language a subtitle file beside `video` names: "en" for "Episode 1.en.srt", "english"
    for "Episode 1.English.forced.ass", and "" for "Episode 1.srt"."""
    parts = subtitle.name[len(video.stem) :].split(".")[1:-1]
    return next((part.casefold() for part in parts if part and part.casefold() not in _FLAGS), "")


def listed(languages: Sequence[str]) -> list[str]:
    """Each language once, in the order first met."""
    return list(dict.fromkeys(languages))
