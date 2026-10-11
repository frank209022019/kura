"""Which titles make one franchise: the ones AniList ties together by story.

Dragon Ball, Dragon Ball Z, GT, Kai, Super and their films are one franchise because AniList says
each is a sequel, prequel, alternative version, side story or film of another. A crossover
(CHARACTER) or a loose OTHER ties nothing, and neither do the manga (ADAPTATION, SOURCE). An entry
the library lacks still ties its neighbours: GT and Kai both name Dragon Ball Z.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# How AniList relates entries of one story.
STORY = frozenset(
    {
        "PREQUEL",
        "SEQUEL",
        "PARENT",
        "SIDE_STORY",
        "ALTERNATIVE",
        "SPIN_OFF",
        "SUMMARY",
        "COMPILATION",
        "CONTAINS",
    }
)


@dataclass(frozen=True)
class Link:
    """What AniList says of one entry: it's the `relation` of entry `related`."""

    anilist_id: int
    related: int
    relation: str


def franchises(titles: Mapping[int, Iterable[int]], links: Iterable[Link]) -> list[list[int]]:
    """The titles grouped by franchise. `titles` maps each title to the AniList entries its files
    matched. Groups come in the order of their first titles, and keep the titles' order."""
    parent: dict[int, int] = {}

    def root(entry: int) -> int:
        parent.setdefault(entry, entry)
        while parent[entry] != entry:
            parent[entry] = parent[parent[entry]]  # halve the path as it goes
            entry = parent[entry]
        return entry

    def join(a: int, b: int) -> None:
        parent[root(a)] = root(b)

    for entries in titles.values():
        known = list(entries)
        for entry in known:
            join(entry, known[0])  # a title's entries are one story
    for link in links:
        if link.relation in STORY:
            join(link.anilist_id, link.related)

    groups: dict[object, list[int]] = {}
    for title_id, entries in titles.items():
        known = list(entries)
        key: object = root(known[0]) if known else ("alone", title_id)
        groups.setdefault(key, []).append(title_id)
    return list(groups.values())
