"""Asking AniList: searches by any name, and single entries."""

import json
from pathlib import Path

from kura.anilist import API, AniList
from kura.core.catalog import TitleKind
from tests.fake_web import Asked, FakeWeb, reply

ANSWERS = Path(__file__).parent / "data" / "anilist"


def saved(name: str) -> object:
    return json.loads((ANSWERS / f"{name}.json").read_text(encoding="utf-8"))


def test_a_search_asks_for_anime_by_name_and_reads_the_answer():
    web = FakeWeb({f"POST {API}": saved("cowboy-bebop")})

    found = AniList(web).search("Cowboy Bebop", 5)

    assert [(entry.id, entry.kind) for entry in found[:2]] == [
        (1, TitleKind.SERIES),
        (5, TitleKind.MOVIE),
    ]
    variables = web.asked[0].payload["variables"]
    assert variables == {"search": "Cowboy Bebop", "count": 5}
    assert "type: ANIME" in str(web.asked[0].payload["query"])


def test_one_entry_by_its_number():
    bebop = json.loads(json.dumps(saved("cowboy-bebop")))["data"]["Page"]["media"][0]

    def answer(asked: Asked) -> object:
        variables = asked.payload["variables"]
        return {"data": {"Media": bebop}} if variables == {"id": 1} else None

    web = FakeWeb({f"POST {API}": answer})

    entry = AniList(web).entry(1)

    assert entry is not None
    assert entry.title == "Cowboy Bebop"


def test_an_entry_anilist_doesnt_have_is_none():
    web = FakeWeb(
        {f"POST {API}": reply({"errors": [{"message": "Not Found.", "status": 404}]}, 404)}
    )

    assert AniList(web).entry(999_999_999) is None
