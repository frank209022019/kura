# AniList (which anime a file is)

[AniList](https://anilist.co) knows anime best: every entry's English, romaji and native titles
and its nicknames ("DBZ"), whether it's a TV series, a film, an OVA or a special, its episode count
and dates, what's airing, and how seasons, films and specials connect (sequel, prequel, side
story). Kura searches it to work out which anime a file is; TMDB ([tmdb.md](tmdb.md)) then gives
the episodes in Plex's shape.

It replaced the manami offline database, the first plan, whose repository was archived in 2026:
AniList is always current and needs no download.

## No key, about 30 requests a minute

AniList's API is free for non-commercial use and needs no key or account. Its rate limit is
90 requests a minute, currently lowered to 30 (it says so in `X-RateLimit-Limit`). When a minute's
requests run out (`X-RateLimit-Remaining: 0`), [kura/web.py](../../engine/src/kura/web.py) waits
for `X-RateLimit-Reset` before the next one, and a 429 is retried after its `Retry-After`. The
engine has one AniList client (`create_app` makes it), so scans, the hourly check and the match
screen's search share the minute's requests; the search asks once the owner stops typing. Kura
asks once per anime (a few times for a name that finds nothing, see below), with everything it
needs in that one answer, and keeps the answers, so a library of a hundred anime costs a few
minutes on the first scan and nothing after.

## What Kura asks

One GraphQL endpoint, `POST https://graphql.anilist.co`, from
[kura/anilist.py](../../engine/src/kura/anilist.py):

- a search: `Page(perPage: N) { media(search: $search, type: ANIME) { … } }`;
- one entry: `Media(id: $id, type: ANIME) { … }`.

Both ask for the same fields: `id format episodes duration status startDate endDate
title { romaji english native } synonyms coverImage { large } nextAiringEpisode
relations { edges { relationType node { … } } }`.
[kura/core/catalog.py](../../engine/src/kura/core/catalog.py) reads them into `Anime` and
`Related` values, with Kura's kinds: TV, TV short and web series (ONA) are a series, MOVIE a
movie, OVA an OVA, SPECIAL and MUSIC a special. Relations to manga and novels are dropped. The
relations of every entry the library matched are kept (`anilist_links`), and they tie franchises
together: sequels, prequels, alternative versions, films and side stories do, crossovers
(`CHARACTER`) and loose links (`OTHER`) don't.

Answers are kept a week in the data folder's `cache/`, so a rescan asks nothing again. A show
still airing is the exception: whenever its episode list is due (every hour), a scan or the hourly
check asks AniList afresh, or a new episode would go unnoticed for a week.

## When a name finds nothing

AniList's search finds an entry only when every word asked for is in one of its names, so a
release's own words empty the answer: `Dragon Ball Z - Movie 03 - The Tree of Might` finds
nothing, `Dragon Ball Z: The Tree of Might` (how Kura reads that name) finds the film. While
nothing found is sure, a numbered film is asked for again by its name up to a comma, its own name
alone, and its series (`searches` in [kura/core/identify.py](../../engine/src/kura/core/identify.py)).
When nothing at all is found, the name may be one AniList writes otherwise: what its first word
finds says how ("Dragonball" finds "Dragon Ball"), and `Dragonball GT` is asked for as
`dragon ball gt` (`respelled`). Every answer is kept a week, like any other.

## Without a TMDB key

AniList's count stands in for TMDB's episode list: the episodes aired so far, numbered 1 to N in
one season (`save_anilist_title` in [kura/identify.py](../../engine/src/kura/identify.py)). For a
show still airing that's every episode before `nextAiringEpisode`; when AniList can't say, the list
stays as it was. AniList doesn't date old episodes, so they carry no air date, and all of them
count as aired when Kura looks for gaps.

## Tests

`tests/data/anilist/` holds real AniList answers (Dragon Ball Z, Cowboy Bebop, Attack on Titan
Season 3 Part 2, One Piece, and the searches for The Tree of Might, "Dragonball" and Dragon Ball
GT), saved once, so parsing is tested against what AniList really sends. No test reaches AniList
itself: `tests/fake_web.py` answers instead, with `tests/services.py`'s answers to exact searches
first (as AniList, a search with a word no name has finds nothing) and kinder ones after.
