"""Files waiting for a match: what they are, Kura's best guesses, searching AniList for another,
and the owner's choice (pinned, so a rescan never undoes it) or "not anime"."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import Field

from kura import review
from kura.api.common import ApiModel, Database, Paths, Web
from kura.config import DataPaths
from kura.core.catalog import TitleKind
from kura.core.identify import Guess as FoundGuess
from kura.core.names import Kind
from kura.identify import Identifier
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
def search_anilist(file_id: int, q: str, conn: Database, paths: Paths, web: Web) -> list[Guess]:
    """AniList's entries for a name, scored against this file."""
    try:
        found = _identifier(paths, web).search(conn, file_id, q)
    except WebError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _offline(error)) from None
    return [_guess(guess) for guess in found]


@router.post("/review/{file_id}")
def choose(file_id: int, body: Choice, conn: Database, paths: Paths, web: Web) -> Chosen:
    """The owner's choice for this file, and for the others that are the same anime."""
    files = [file_id, *[other for other in body.also if other != file_id]]
    try:
        placed = _identifier(paths, web).choose(conn, files, body.anilist_id, Kind(body.kind))
    except LookupError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "AniList doesn't have that entry any more."
        ) from None
    except WebError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _offline(error)) from None
    if placed == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That file isn't in the library any more.")
    return Chosen(placed=placed)


@router.post("/review/{file_id}/ignore", status_code=status.HTTP_204_NO_CONTENT)
def ignore(file_id: int, conn: Database, paths: Paths, web: Web) -> None:
    """Not anime: Kura leaves it out, and no rescan asks about it again."""
    _identifier(paths, web).ignore(conn, file_id)


def _identifier(paths: DataPaths, web: Send) -> Identifier:
    return Identifier(paths, web, now=lambda: datetime.now().astimezone())


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
