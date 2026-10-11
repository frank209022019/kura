"""Answers kept for a while, so the same question isn't asked twice."""

from pathlib import Path

from kura.anilist import API, AniList
from kura.cache import DAY, Cache
from tests.fake_web import FakeWeb


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def test_an_answer_comes_back_until_it_is_too_old(tmp_path: Path):
    clock = Clock()
    cache = Cache(tmp_path / "cache", clock)

    cache.put("anilist search 8 trigun", {"data": {"Page": {"media": []}}})

    assert cache.get("anilist search 8 trigun", DAY) == {"data": {"Page": {"media": []}}}
    clock.now += DAY + 1
    assert cache.get("anilist search 8 trigun", DAY) is None


def test_nothing_saved_or_a_damaged_file_is_nothing(tmp_path: Path):
    cache = Cache(tmp_path / "cache")
    assert cache.get("never asked", DAY) is None

    cache.put("asked", {"answer": 1})
    for saved in (tmp_path / "cache").iterdir():
        saved.write_text("not json", encoding="utf-8")
    assert cache.get("asked", DAY) is None


def test_a_search_asked_twice_reaches_anilist_once(tmp_path: Path):
    web = FakeWeb({f"POST {API}": {"data": {"Page": {"media": []}}}})
    anilist = AniList(web, cache=Cache(tmp_path / "cache"))

    anilist.search("Trigun")
    anilist.search("TRIGUN")  # the same question, whatever the case

    assert len(web.asked) == 1
