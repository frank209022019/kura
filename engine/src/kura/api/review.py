"""Files waiting for a match: what they are, Kura's best guesses, searching AniList for another,
and the owner's choice (pinned, so a rescan never undoes it) or "not anime"."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import Field

from kura import review, stills
from kura.anilist import AniList
from kura.api.common import AniListClient, ApiModel, Database, Paths, Toolbox, Web
from kura.config import DataPaths
from kura.core.catalog import TitleKind
from kura.core.identify import Guess as FoundGuess
from kura.core.names import Kind
from kura.identify import Identifier, UnplacedError
from kura.web import Send, WebError

router = APIRouter()


class Guess(ApiModel):
    anilist_id: int
    title: str
    kind: TitleKind | None
    year: int | None
    episodes: int | None
    minutes: int | None
    cover: str | None
    confidence: int  # 0 to 100
    reasons: list[str]


class WaitingFile(ApiModel):
    id: int
    path: str
    size: int
    minutes: float | None
    height: int | None
    codec: str | None
    audio: list[str]
    subtitles: list[str]
    group: str | None  # the release group's tag, such as "subs"
    title: str | None  # the show's name as the file or its folder gives it
    season: int | None
    episode: int | None
    kind: Literal["episode", "special", "movie", "extra", "dvd"]
    guesses: list[Guess]
    alike: list[int]  # other waiting files beside it from the same release


class Choice(ApiModel):
    anilist_id: int
    kind: Literal["episode", "movie", "special"] = "episode"
    # Other files that are the same anime, numbered from their names.
    also: list[int] = Field(default_factory=list[int])
    # The file's number, when its name has none Kura can use.
    episode: int | None = None


class Chosen(ApiModel):
    placed: int


@router.get("/review")
def files_to_review(conn: Database) -> list[WaitingFile]:
    """Every file Kura couldn't place surely, folder by folder."""
    found: list[WaitingFile] = []
    for item in review.waiting(conn):
        guesses = [Guess.model_validate(saved) for saved in item.guesses]
        found.append(
            WaitingFile(
                id=item.id,
                path=item.path,
                size=item.size,
                minutes=item.minutes,
                height=item.height,
                codec=item.codec,
                audio=list(item.audio),
                subtitles=list(item.subtitles),
                group=item.parsed.group,
                title=item.parsed.best_title,
                season=item.parsed.season
                if item.parsed.season is not None
                else item.parsed.folder_season,
                episode=item.parsed.episode,
                kind=item.parsed.kind.value,
                guesses=guesses,
                alike=list(item.alike),
            )
        )
    return found


@router.get("/review/{file_id}/search")
def search_anilist(
    file_id: int, q: str, conn: Database, paths: Paths, web: Web, anilist: AniListClient
) -> list[Guess]:
    """AniList's entries for a name, scored against this file."""
    try:
        found = _identifier(paths, web, anilist).search(conn, file_id, q)
    except WebError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _offline(error)) from None
    return [_guess(guess) for guess in found]


@router.post("/review/{file_id}")
def choose(
    file_id: int, body: Choice, conn: Database, paths: Paths, web: Web, anilist: AniListClient
) -> Chosen:
    """The owner's choice for this file, and for the others that are the same anime. An
    episode Kura can't place is 422: the owner gives its number."""
    try:
        placed = _identifier(paths, web, anilist).choose(
            conn,
            file_id,
            body.anilist_id,
            Kind(body.kind),
            also=body.also,
            episode=body.episode,
        )
    except UnplacedError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except LookupError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "AniList doesn't have that entry any more."
        ) from None
    except WebError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _offline(error)) from None
    if placed == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That file isn't in the library any more.")
    return Chosen(placed=placed)


@router.get(
    "/review/{file_id}/stills/{index}",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def file_still(
    file_id: int, index: int, conn: Database, paths: Paths, toolbox: Toolbox
) -> FileResponse:
    """One of three stills from the file (0, 1 or 2: 15%, 50% and 80% of the way in)."""
    row = conn.execute("SELECT path, duration FROM files WHERE id = ?", (file_id,)).fetchone()
    picture = (
        stills.still(paths, toolbox.path("ffmpeg"), Path(row["path"]), row["duration"], index)
        if row is not None
        else None
    )
    if picture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no still from this file.")
    return FileResponse(picture, media_type="image/jpeg")


@router.post("/review/{file_id}/ignore", status_code=status.HTTP_204_NO_CONTENT)
def ignore(file_id: int, conn: Database, paths: Paths, web: Web, anilist: AniListClient) -> None:
    """Not anime: Kura leaves it out, and no rescan asks about it again."""
    _identifier(paths, web, anilist).ignore(conn, file_id)


def _identifier(paths: DataPaths, web: Send, anilist: AniList) -> Identifier:
    return Identifier(paths, web, now=lambda: datetime.now().astimezone(), anilist=anilist)


def _guess(guess: FoundGuess) -> Guess:
    entry = guess.anime
    return Guess(
        anilist_id=entry.id,
        title=entry.title,
        kind=entry.kind,
        year=entry.year,
        episodes=entry.episodes,
        minutes=entry.minutes,
        cover=entry.cover,
        confidence=guess.confidence,
        reasons=list(guess.reasons),
    )


def _offline(error: WebError) -> str:
    return f"{error} Nothing was changed; try again in a moment."
