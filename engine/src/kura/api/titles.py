"""The library's titles: every anime and film with its kind, release date, files and gaps, and one
title in full with its seasons, the episodes it's missing, and its videos."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from kura import artwork, titles
from kura.api.common import ApiModel, Database, Paths, Web
from kura.core.catalog import Episode, TitleKind
from kura.titles import Order, Title

router = APIRouter()


class SeasonCount(ApiModel):
    season: int
    present: int
    aired: int
    total: int  # with the episodes still to air


class EpisodeRef(ApiModel):
    season: int
    number: int
    name: str | None
    aired: str | None


class TitleSummary(ApiModel):
    id: int
    kind: TitleKind
    name: str
    year: int | None
    released: str | None  # the first episode, or the film's release (lists sort by it)
    airing: bool
    has_poster: bool
    files: int  # videos in the library
    added: str | None  # when the first of them was found
    aired: int  # numbered episodes out so far; 0 for a film
    present: int  # of those, the ones the library holds
    missing: int
    specials_missing: int  # specials and OVAs, listed apart: never counted as missing
    upcoming: int  # episodes still to air


class TitleFile(ApiModel):
    id: int
    path: str
    season: int | None
    episode: int | None
    episode_end: int | None
    problem: str | None  # why it couldn't be read
    height: int | None
    codec: str | None
    duration: float | None


class TitleDetail(TitleSummary):
    seasons: list[SeasonCount]
    missing_episodes: list[EpisodeRef]
    missing_specials: list[EpisodeRef]
    upcoming_episodes: list[EpisodeRef]
    videos: list[TitleFile]


Sort = Annotated[Order, Query(description="released (the default), name, added or missing")]


@router.get("/titles")
def list_titles(conn: Database, sort: Sort = "released") -> list[TitleSummary]:
    """Every anime and film in the library, oldest release first unless asked otherwise."""
    return [_summary(found) for found in titles.titles(conn, _today(), sort)]


@router.get("/titles/{title_id}")
def one_title(title_id: int, conn: Database) -> TitleDetail:
    found = titles.title(conn, title_id, _today())
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kura has no such title.")
    gaps = found.gaps
    videos = conn.execute(
        """SELECT id, path, season, episode, episode_end, problem, height, codec, duration
           FROM files WHERE title_id = ? AND gone_at IS NULL
           ORDER BY season, episode, path""",
        (title_id,),
    )
    return TitleDetail(
        **_summary(found).model_dump(by_alias=False),
        seasons=[
            SeasonCount(season=s.season, present=s.present, aired=s.aired, total=s.total)
            for s in (gaps.seasons if gaps else ())
        ],
        missing_episodes=[_episode(e) for e in (gaps.missing if gaps else ())],
        missing_specials=[_episode(e) for e in (gaps.specials_missing if gaps else ())],
        upcoming_episodes=[_episode(e) for e in (gaps.upcoming if gaps else ())],
        videos=[TitleFile.model_validate(dict(row)) for row in videos],
    )


@router.get(
    "/titles/{title_id}/poster",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}},
)
def title_poster(title_id: int, conn: Database, paths: Paths, web: Web) -> FileResponse:
    """The title's poster, fetched once from TMDB or AniList and then kept."""
    row = conn.execute("SELECT poster FROM titles WHERE id = ?", (title_id,)).fetchone()
    kept = artwork.poster(paths, row["poster"], web) if row is not None else None
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This title has no poster yet.")
    return FileResponse(kept, media_type=artwork.media_type(kept))


@router.get(
    "/artwork",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}},
)
def artwork_at(address: str, paths: Paths, web: Web) -> FileResponse:
    """A picture from TMDB's or AniList's image server, such as a guess's cover, fetched once and
    kept. Any other address is refused."""
    kept = artwork.poster(paths, address, web)
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kura has no picture at that address.")
    return FileResponse(kept, media_type=artwork.media_type(kept))


def _summary(found: Title) -> TitleSummary:
    gaps = found.gaps
    return TitleSummary(
        id=found.id,
        kind=found.kind,
        name=found.name,
        year=found.year,
        released=found.released.isoformat() if found.released else None,
        airing=found.airing,
        has_poster=artwork.poster_address(found.poster) is not None,
        files=found.files,
        added=found.added,
        aired=gaps.aired if gaps else 0,
        present=gaps.present if gaps else 0,
        missing=len(gaps.missing) if gaps else 0,
        specials_missing=len(gaps.specials_missing) if gaps else 0,
        upcoming=len(gaps.upcoming) if gaps else 0,
    )


def _episode(episode: Episode) -> EpisodeRef:
    return EpisodeRef(
        season=episode.season,
        number=episode.number,
        name=episode.title,
        aired=episode.aired.isoformat() if episode.aired else None,
    )


def _today() -> date:
    return datetime.now().astimezone().date()
