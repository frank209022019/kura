"""AniList: every anime with all the names it goes by, how its seasons, films and specials connect,
and what's airing. It needs no key, and allows about 30 requests a minute; kura/web.py waits when
it says the minute's requests are spent.
"""

from kura.core import catalog, fields
from kura.core.catalog import Anime
from kura.web import Send, Service, WebError, send

API = "https://graphql.anilist.co"

# Everything Kura reads about an entry (see kura/core/catalog.py), asked for in one go.
_ENTRY = """
    id format episodes duration status
    startDate { year month day }
    endDate { year month day }
    title { romaji english native }
    synonyms
    coverImage { large }
    nextAiringEpisode { episode airingAt }
    relations {
      edges {
        relationType
        node { id type format startDate { year month day } title { romaji english } }
      }
    }
"""
_SEARCH = (
    "query ($search: String, $count: Int) {"
    f" Page(perPage: $count) {{ media(search: $search, type: ANIME) {{ {_ENTRY} }} }} }}"
)
_ONE = f"query ($id: Int) {{ Media(id: $id, type: ANIME) {{ {_ENTRY} }} }}"


class AniList:
    def __init__(self, transport: Send = send, service: Service | None = None) -> None:
        self._service = service or Service("AniList", transport)

    def search(self, text: str, count: int = 8) -> list[Anime]:
        """Entries whose names fit `text`, best first, as AniList ranks them."""
        answer = self._service.json(
            "POST", API, payload={"query": _SEARCH, "variables": {"search": text, "count": count}}
        )
        return catalog.anime_list(answer)

    def entry(self, anime_id: int) -> Anime | None:
        """One entry by its AniList number, or None when AniList has no such entry."""
        payload = {"query": _ONE, "variables": {"id": anime_id}}
        try:
            answer = self._service.json("POST", API, payload=payload)
        except WebError as error:
            if error.status == 404:
                return None
            raise
        media = fields.mapping(fields.mapping(answer, "data"), "Media")
        return catalog.anime(media) if media else None
