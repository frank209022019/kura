"""Posters: downloaded once from TMDB's image server or AniList's, and kept in the data folder's
`artwork` folder. Only those two hosts are ever asked for a picture.
"""

import hashlib
import logging
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from kura.config import DataPaths
from kura.tmdb import IMAGES
from kura.web import Send, Service, WebError

log = logging.getLogger(__name__)

POSTER_SIZE = "w342"  # TMDB's poster width that suits a card
_HOSTS = ("image.tmdb.org", "anilist.co")  # and its subdomains, such as s4.anilist.co
_KINDS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def poster_address(poster: str | None) -> str | None:
    """Where a title's poster is: a TMDB image path becomes its address on the image server;
    an AniList cover is already one. Anything from another host is refused."""
    if not poster:
        return None
    address = f"{IMAGES}/{POSTER_SIZE}{poster}" if poster.startswith("/") else poster
    parts = urlsplit(address)
    host = parts.hostname or ""
    trusted = any(host == known or host.endswith(f".{known}") for known in _HOSTS)
    return address if parts.scheme == "https" and trusted else None


def media_type(path: Path) -> str:
    return _KINDS.get(path.suffix.casefold(), "application/octet-stream")


def poster(paths: DataPaths, source: str | None, transport: Send) -> Path | None:
    """The poster's file, downloaded the first time it's asked for. None when there's none, or
    it can't be fetched now (Kura asks again next time)."""
    address = poster_address(source)
    if address is None:
        return None
    suffix = PurePosixPath(urlsplit(address).path).suffix.casefold()
    if suffix not in _KINDS:
        suffix = ".jpg"
    name = hashlib.sha256(address.encode()).hexdigest()[:24] + suffix
    kept = paths.artwork / name
    if kept.is_file():
        return kept
    try:
        data = Service("Artwork", transport).raw(address)
    except WebError as error:
        log.info("A poster couldn't be fetched (%s): %s", address, error)
        return None
    try:
        paths.artwork.mkdir(parents=True, exist_ok=True)
        partial = kept.with_name(f"{name}.partial")
        partial.write_bytes(data)
        partial.replace(kept)
    except OSError as error:
        log.warning("Kura couldn't keep a poster: %s", error)
        return None
    return kept
