"""The library's titles: every anime and film with its kind, release date, files and gaps, one
title in full with its seasons, the episodes it's missing, and its videos, and the franchises they
make (a franchise's series, films, OVAs and specials together, and the ones it lacks)."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from kura import artwork, franchises, titles
from kura.api.common import ApiModel, Database, Paths, Web
from kura.core.catalog import Episode, TitleKind
from kura.core.franchise import Entry
from kura.core.report import GAP_ANALYSIS_FILE
from kura.preferences import library_standard
from kura.reports import own_folder
from kura.titles import Order, State, Title

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
    size: int  # bytes
    season: int | None
    episode: int | None
    episode_end: int | None
    problem: str | None  # why it couldn't be read
    height: int | None
    codec: str | None
    duration: float | None


class EpisodeState(ApiModel):
    """One episode and how it stands, for the episode map: status by shape."""

    season: int  # 0 for the specials
    number: int
    name: str | None
    aired: str | None
    state: State
    file_id: int | None


class FranchiseRef(ApiModel):
    id: int
    name: str


class KindCounts(ApiModel):
    series: int
    movie: int
    ova: int
    special: int


class FranchiseSummary(ApiModel):
    """Titles AniList ties together by story. A title on its own is a franchise of one."""

    id: int  # its lead title's: the first series to air, or else the first title
    name: str
    released: str | None  # its first release
    kinds: KindCounts
    has_poster: bool  # its lead's
    airing: bool  # any of it
    files: int
    added: str | None  # when its newest title's first video was found
    aired: int
    present: int
    missing: int
    specials_missing: int
    upcoming: int
    titles: list[TitleSummary]  # in the order asked for


class MissingTitle(ApiModel):
    """A series, film, OVA or special of a franchise that the library has no part of, as AniList
    knows it."""

    anilist_id: int
    kind: TitleKind
    name: str
    year: int | None
    released: str | None  # its first episode, or the film's release
    episodes: int | None  # None while AniList doesn't know how many
    coming: bool  # not out yet
    airing: bool  # out, with more of it still to come
    cover: str | None  # AniList's cover address (shown through /artwork)


class FranchiseMissing(ApiModel):
    titles: list[MissingTitle]  # oldest release first
    looking: bool  # some of the franchise is still to be looked up on AniList


class TitleDetail(TitleSummary):
    franchise: FranchiseRef | None  # when the title is one of several
    source: Literal["tmdb", "anilist"]  # where its episode list comes from
    folder: str | None  # its own folder, when its videos have one
    seasons: list[SeasonCount]
    missing_episodes: list[EpisodeRef]
    missing_specials: list[EpisodeRef]
    upcoming_episodes: list[EpisodeRef]
    episodes: list[EpisodeState]  # every episode with its state, specials included
    videos: list[TitleFile]


Sort = Annotated[Order, Query(description="released (the default), name, added or missing")]


@router.get("/titles")
def list_titles(conn: Database, sort: Sort = "released") -> list[TitleSummary]:
    """Every anime and film in the library, oldest release first unless asked otherwise."""
    return [_summary(found) for found in titles.titles(conn, _today(), sort)]


@router.get("/franchises")
def list_franchises(conn: Database, sort: Sort = "released") -> list[FranchiseSummary]:
    """Every franchise with its titles, oldest release first unless asked otherwise: Home's
    shelf. A title on its own is a franchise of one."""
    return [_franchise(found) for found in titles.franchises(conn, _today(), sort)]


@router.get("/franchises/{title_id}")
def one_franchise(title_id: int, conn: Database, sort: Sort = "released") -> FranchiseSummary:
    """The franchise a title belongs to, found by any of its titles."""
    found = titles.franchise_of(conn, title_id, _today(), sort)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kura has no such franchise.")
    return _franchise(found)


@router.get("/franchises/{title_id}/missing")
def franchise_missing(title_id: int, conn: Database) -> FranchiseMissing:
    """The series, films, OVAs and specials AniList ties to the franchise that the library has no
    part of. Kura looks the franchise up in the background, a few entries at a time."""
    found = titles.franchise_of(conn, title_id, _today())
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kura has no such franchise.")
    rest = franchises.rest(conn, found)
    return FranchiseMissing(
        titles=[_missing(entry, kind) for entry in rest.titles if (kind := entry.kind)],
        looking=rest.looking,
    )


@router.get("/titles/{title_id}")
def one_title(title_id: int, conn: Database) -> TitleDetail:
    found = titles.title(conn, title_id, _today())
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kura has no such title.")
    group = titles.franchise_of(conn, title_id, _today())
    gaps = found.gaps
    videos = conn.execute(
        """SELECT id, path, size, season, episode, episode_end, problem, height, codec, duration
           FROM files WHERE title_id = ? AND gone_at IS NULL
           ORDER BY season, episode, path""",
        (title_id,),
    )
    show = titles.show_of(conn, title_id)
    statuses = (
        titles.episode_statuses(conn, title_id, show, library_standard(conn), _today())
        if show
        else []
    )
    roots = [Path(row["path"]) for row in conn.execute("SELECT path FROM folders")]
    own = own_folder(conn, title_id, roots)
    return TitleDetail(
        **_summary(found).model_dump(by_alias=False),
        franchise=FranchiseRef(id=group.id, name=group.name)
        if group and len(group.titles) > 1
        else None,
        source="tmdb" if found.tmdb else "anilist",
        folder=str(own) if own else None,
        episodes=[
            EpisodeState(
                season=s.episode.season,
                number=s.episode.number,
                name=s.episode.title,
                aired=s.episode.aired.isoformat() if s.episode.aired else None,
                state=s.state,
                file_id=s.file_id,
            )
            for s in statuses
        ],
        seasons=[
            SeasonCount(season=s.season, present=s.present, aired=s.aired, total=s.total)
            for s in (gaps.seasons if gaps else ())
        ],
        missing_episodes=[_episode(e) for e in (gaps.missing if gaps else ())],
        missing_specials=[_episode(e) for e in (gaps.specials_missing if gaps else ())],
        upcoming_episodes=[_episode(e) for e in (gaps.upcoming if gaps else ())],
        videos=[TitleFile.model_validate(dict(row)) for row in videos],
    )


class Report(ApiModel):
    path: str
    text: str


@router.get("/titles/{title_id}/report")
def title_report(title_id: int, conn: Database) -> Report:
    """The gap analysis Kura wrote next to the title, as it is on disk."""
    roots = [Path(row["path"]) for row in conn.execute("SELECT path FROM folders")]
    folder = own_folder(conn, title_id, roots)
    report = folder / GAP_ANALYSIS_FILE if folder else None
    try:
        text = report.read_text(encoding="utf-8") if report else None
    except OSError:
        text = None
    if report is None or text is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "There's no gap analysis for this title yet: it gets one once its videos have a "
            "folder of their own.",
        )
    return Report(path=str(report), text=text)


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


def _franchise(found: titles.Franchise) -> FranchiseSummary:
    members = [_summary(title) for title in found.titles]
    lead = next(member for member in members if member.id == found.id)
    kinds = {kind: sum(1 for m in members if m.kind is kind) for kind in TitleKind}
    return FranchiseSummary(
        id=found.id,
        name=found.name,
        released=found.released.isoformat() if found.released else None,
        kinds=KindCounts(**{kind.value: count for kind, count in kinds.items()}),
        has_poster=lead.has_poster,
        airing=any(m.airing for m in members),
        files=sum(m.files for m in members),
        added=max((m.added for m in members if m.added), default=None),
        aired=sum(m.aired for m in members),
        present=sum(m.present for m in members),
        missing=sum(m.missing for m in members),
        specials_missing=sum(m.specials_missing for m in members),
        upcoming=sum(m.upcoming for m in members),
        titles=members,
    )


def _missing(entry: Entry, kind: TitleKind) -> MissingTitle:
    return MissingTitle(
        anilist_id=entry.id,
        kind=kind,
        name=entry.name,
        year=entry.start.year if entry.start else None,
        released=entry.start.isoformat() if entry.start else None,
        episodes=entry.episodes,
        coming=entry.coming,
        airing=entry.airing,
        cover=entry.cover if artwork.poster_address(entry.cover) else None,
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
