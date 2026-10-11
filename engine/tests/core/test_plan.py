"""Tidy-up plans. The expected moves are the rows on the design's tidy board."""

from datetime import date
from fractions import Fraction
from pathlib import PureWindowsPath

from kura.core.copies import Copy
from kura.core.media import Audio, MediaInfo, Subtitle, Video
from kura.core.plan import (
    DELETED,
    Change,
    ChangeKind,
    EpisodeOf,
    MovieOf,
    PlacedFile,
    plan_set_aside,
    plan_tidy,
    quarantine_place,
    sidecars_of,
)

LIBRARY = PureWindowsPath(r"D:\Anime")
DAY = date(2026, 10, 10)


def media(height: int, *, audio: int = 1, subtitles: bool = False) -> MediaInfo:
    video = Video("h264", round(height * 4 / 3), height, Fraction(4, 3), None, 8, False)
    tracks = tuple(Audio("aac", 2, "jpn", False) for _ in range(audio))
    subs = (Subtitle("ass", "eng", True, False),) if subtitles else ()
    return MediaInfo("mkv", 1400.0, height * 500_000, video, tracks, subs)


def placed(
    path: str, identity: EpisodeOf | MovieOf, media_info: MediaInfo | None = None
) -> PlacedFile:
    return PlacedFile(Copy(LIBRARY / path, media_info or media(480)), identity)


BEBOP_1 = EpisodeOf("Cowboy Bebop", 1998, season=1, episode=1, title="Asteroid Blues")
BEBOP_2 = EpisodeOf("Cowboy Bebop", 1998, season=1, episode=2, title="Stray Dog Strut")
DEATH_NOTE_1 = EpisodeOf("Death Note", 2006, season=1, episode=1, title="Rebirth")
DEATH_NOTE_7 = EpisodeOf("Death Note", 2006, season=1, episode=7, title="Overcast")
TRIGUN_3 = EpisodeOf("Trigun", 1998, season=1, episode=3, title="Peace Maker")
BEBOP_MOVIE = MovieOf("Cowboy Bebop: The Movie", 2001)


def test_the_tidy_boards_downloads_folder():
    files = [
        placed(r"Downloads\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv", BEBOP_1),
        placed(r"Downloads\[Hi10] Cowboy_Bebop_-_02_(BD_720p).mkv", BEBOP_2),
        placed(r"Downloads\Death Note 01.avi", DEATH_NOTE_1),
        placed(
            r"Downloads\[DB] Death_Note_07 (720p).mkv",
            DEATH_NOTE_7,
            media(720, audio=2, subtitles=True),
        ),
        placed(r"Downloads\Death Note 07.avi", DEATH_NOTE_7, media(480)),
        placed(r"Downloads\trigun_03.mp4", TRIGUN_3),
        placed(r"Downloads\Cowboy Bebop Movie.mkv", BEBOP_MOVIE),
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    assert [(c.kind, str(c.source.name), str(c.target)) for c in changes] == [
        (
            ChangeKind.QUARANTINE,
            "Death Note 07.avi",
            r"D:\Kura quarantine\2026-10-10\Death Note 07.avi",
        ),
        (
            ChangeKind.MOVE,
            "Cowboy Bebop Movie.mkv",
            r"D:\Anime\Movies\Cowboy Bebop - The Movie (2001)\Cowboy Bebop - The Movie (2001).mkv",
        ),
        (
            ChangeKind.MOVE,
            "[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv",
            r"D:\Anime\TV\Cowboy Bebop (1998)\Season 01"
            r"\Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv",
        ),
        (
            ChangeKind.MOVE,
            "[Hi10] Cowboy_Bebop_-_02_(BD_720p).mkv",
            r"D:\Anime\TV\Cowboy Bebop (1998)\Season 01"
            r"\Cowboy Bebop (1998) - S01E02 - Stray Dog Strut.mkv",
        ),
        (
            ChangeKind.MOVE,
            "Death Note 01.avi",
            r"D:\Anime\TV\Death Note (2006)\Season 01\Death Note (2006) - S01E01 - Rebirth.avi",
        ),
        (
            ChangeKind.MOVE,
            "[DB] Death_Note_07 (720p).mkv",
            r"D:\Anime\TV\Death Note (2006)\Season 01\Death Note (2006) - S01E07 - Overcast.mkv",
        ),
        (
            ChangeKind.MOVE,
            "trigun_03.mp4",
            r"D:\Anime\TV\Trigun (1998)\Season 01\Trigun (1998) - S01E03 - Peace Maker.mp4",
        ),
    ]


def test_a_duplicate_says_which_copy_was_kept_and_why():
    files = [
        placed(r"Downloads\[DB] Death_Note_07 (720p).mkv", DEATH_NOTE_7, media(720, audio=2)),
        placed(r"Downloads\Death Note 07.avi", DEATH_NOTE_7, media(480)),
    ]

    quarantine = plan_tidy(files, LIBRARY, day=DAY).changes[0]

    assert quarantine.label == "Death Note · S01E07 · duplicate"
    assert quarantine.reason == (
        "Kept [DB] Death_Note_07 (720p).mkv instead: higher resolution and an extra audio track"
    )


def test_labels_name_the_episode_or_movie():
    changes = plan_tidy(
        [placed(r"x\a.mkv", BEBOP_1), placed(r"x\b.mkv", BEBOP_MOVIE)], LIBRARY, day=DAY
    ).changes

    assert {c.label for c in changes} == {"Cowboy Bebop · S01E01", "Cowboy Bebop: The Movie"}


def test_a_file_already_in_place_needs_nothing():
    path = r"TV\Trigun (1998)\Season 01\Trigun (1998) - S01E03 - Peace Maker.mp4"

    assert plan_tidy([placed(path, TRIGUN_3)], LIBRARY, day=DAY).changes == ()


def test_a_name_differing_only_in_case_is_renamed():
    path = r"TV\Trigun (1998)\Season 01\trigun (1998) - s01e03 - peace maker.mp4"

    changes = plan_tidy([placed(path, TRIGUN_3)], LIBRARY, day=DAY).changes

    assert [c.target.name for c in changes] == ["Trigun (1998) - S01E03 - Peace Maker.mp4"]


def test_a_name_another_file_already_has_gets_2():
    existing = r"D:\Anime\TV\Trigun (1998)\Season 01\Trigun (1998) - S01E03 - Peace Maker.mp4"

    changes = plan_tidy(
        [placed(r"Downloads\trigun_03.mp4", TRIGUN_3)], LIBRARY, day=DAY, taken={existing}
    ).changes

    assert changes[0].target.name == "Trigun (1998) - S01E03 - Peace Maker (2).mp4"
    assert (
        changes[0].reason
        == "Named and filed. A file with this name is already there; both are kept"
    )


def test_quarantine_never_overwrites_either():
    already = r"D:\Kura quarantine\2026-10-10\Death Note 07.avi"
    files = [
        placed(r"Downloads\[DB] Death_Note_07 (720p).mkv", DEATH_NOTE_7, media(720)),
        placed(r"Downloads\Death Note 07.avi", DEATH_NOTE_7, media(480)),
    ]

    quarantine = plan_tidy(files, LIBRARY, day=DAY, taken={already}).changes[0]

    assert str(quarantine.target) == r"D:\Kura quarantine\2026-10-10\Death Note 07 (2).avi"


def test_three_copies_keep_one():
    files = [
        placed(rf"x\{n}.mkv", BEBOP_1, media(h)) for n, h in (("a", 480), ("b", 720), ("c", 576))
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    kinds = sorted((c.kind, c.source.name) for c in changes)
    assert kinds == [
        (ChangeKind.MOVE, "b.mkv"),
        (ChangeKind.QUARANTINE, "a.mkv"),
        (ChangeKind.QUARANTINE, "c.mkv"),
    ]


def test_a_file_whose_place_can_never_fit_is_left_alone_with_a_reason():
    deep = PureWindowsPath("D:\\" + "\\".join(["Folder"] * 40))
    file = PlacedFile(Copy(deep.parent / "x.mkv", media(480)), BEBOP_1)

    plan = plan_tidy([file], deep, day=DAY)

    assert plan.changes == ()
    assert plan.skipped == ((file.copy.path, "The new name would be too long for Windows"),)


def test_a_change_is_a_plain_value():
    change = Change(ChangeKind.MOVE, LIBRARY / "a", LIBRARY / "b", "label", "reason")

    assert change == Change(ChangeKind.MOVE, LIBRARY / "a", LIBRARY / "b", "label", "reason")


def test_subtitles_beside_a_video_move_and_rename_with_it():
    video = LIBRARY / "Downloads" / "Death Note 01.avi"
    subtitles = (video.with_name("Death Note 01.en.srt"), video.with_name("Death Note 01.ja.ass"))
    files = [PlacedFile(Copy(video, media(480)), DEATH_NOTE_1, sidecars=subtitles)]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    season = r"D:\Anime\TV\Death Note (2006)\Season 01"
    assert [(c.source.name, str(c.target), c.label, c.reason) for c in changes] == [
        (
            "Death Note 01.avi",
            season + r"\Death Note (2006) - S01E01 - Rebirth.avi",
            "Death Note · S01E01",
            "Named and filed",
        ),
        (
            "Death Note 01.en.srt",
            season + r"\Death Note (2006) - S01E01 - Rebirth.en.srt",
            "Death Note · S01E01 · subtitles",
            "Follows its video",
        ),
        (
            "Death Note 01.ja.ass",
            season + r"\Death Note (2006) - S01E01 - Rebirth.ja.ass",
            "Death Note · S01E01 · subtitles",
            "Follows its video",
        ),
    ]


def test_a_quarantined_copys_subtitles_go_with_it():
    better = placed(r"Downloads\[DB] Death_Note_07 (720p).mkv", DEATH_NOTE_7, media(720))
    worse = LIBRARY / "Downloads" / "Death Note 07.avi"
    files = [
        better,
        PlacedFile(Copy(worse, media(480)), DEATH_NOTE_7, (worse.with_suffix(".srt"),)),
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    quarantined = [str(c.target) for c in changes if c.kind is ChangeKind.QUARANTINE]
    assert quarantined == [
        r"D:\Kura quarantine\2026-10-10\Death Note 07.avi",
        r"D:\Kura quarantine\2026-10-10\Death Note 07.srt",
    ]


def test_only_subtitles_named_after_the_video_belong_to_it():
    video = LIBRARY / "Show" / "Episode 1.mkv"
    names = [
        "Episode 1.mkv",
        "Episode 1.srt",
        "Episode 1.en.forced.ass",
        "EPISODE 1.EN.SRT",
        "Episode 10.en.srt",  # another episode's
        "Episode 1.nfo",  # not subtitles
        "Episode 1 extra.srt",  # not named after it
    ]

    assert [path.name for path in sidecars_of(video, names)] == [
        "Episode 1.en.forced.ass",
        "EPISODE 1.EN.SRT",
        "Episode 1.srt",
    ]


def test_subtitles_go_to_the_video_whose_name_fits_them_best():
    folder = LIBRARY / "Show"
    names = ["Show - 12.mkv", "Show - 12.5.mkv", "Show - 12.en.srt", "Show - 12.5.en.srt"]

    assert [p.name for p in sidecars_of(folder / "Show - 12.mkv", names)] == ["Show - 12.en.srt"]
    assert [p.name for p in sidecars_of(folder / "Show - 12.5.mkv", names)] == [
        "Show - 12.5.en.srt"
    ]


def test_a_change_of_case_alone_renames_the_subtitles_too():
    season = LIBRARY / "TV" / "Dragon Ball Z (1989)" / "Season 01"
    video = season / "dragon ball z (1989) - s01e01 - the new threat.mkv"
    subtitles = video.with_name("dragon ball z (1989) - s01e01 - the new threat.en.srt")
    identity = EpisodeOf("Dragon Ball Z", 1989, season=1, episode=1, title="The New Threat")
    files = [PlacedFile(Copy(video, media(480)), identity, (subtitles,))]

    changes = plan_tidy(files, LIBRARY, day=DAY, taken=[str(video), str(subtitles)]).changes

    assert {c.target.name for c in changes} == {
        "Dragon Ball Z (1989) - S01E01 - The New Threat.mkv",
        "Dragon Ball Z (1989) - S01E01 - The New Threat.en.srt",  # not "… (2).en.srt"
    }


def test_the_owner_can_keep_the_other_copy():
    better = placed(r"Downloads\[DB] Death_Note_07 (720p).mkv", DEATH_NOTE_7, media(720))
    chosen = placed(r"Downloads\Death Note 07.avi", DEATH_NOTE_7, media(480))

    changes = plan_tidy([better, chosen], LIBRARY, day=DAY, keep={chosen.copy.path}).changes

    assert [(c.kind, c.source.name) for c in changes] == [
        (ChangeKind.QUARANTINE, "[DB] Death_Note_07 (720p).mkv"),
        (ChangeKind.MOVE, "Death Note 07.avi"),
    ]
    assert changes[0].reason == "Kept Death Note 07.avi instead: you chose it"


def test_each_file_goes_under_its_own_library_folder():
    other = PureWindowsPath("F:/More anime")
    files = [
        placed(r"Downloads\trigun_03.mp4", TRIGUN_3),
        PlacedFile(Copy(other / "Bebop" / "01.mkv", media(480)), BEBOP_1, root=other),
    ]

    targets = sorted(str(c.target) for c in plan_tidy(files, LIBRARY, day=DAY).changes)

    assert targets == [
        r"D:\Anime\TV\Trigun (1998)\Season 01\Trigun (1998) - S01E03 - Peace Maker.mp4",
        r"F:\More anime\TV\Cowboy Bebop (1998)\Season 01"
        r"\Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv",
    ]


def test_a_file_holding_more_episodes_isnt_a_copy_of_one_holding_fewer():
    both = EpisodeOf("Cowboy Bebop", 1998, season=1, episode=1, last_episode=2)
    files = [
        placed(r"x\Cowboy Bebop - 01-02.mkv", both, media(480)),
        placed(r"x\Cowboy Bebop - 01.mkv", BEBOP_1, media(720)),
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    assert {c.kind for c in changes} == {ChangeKind.MOVE}
    assert len(changes) == 2


def test_the_parts_of_a_film_are_filed_together_not_set_aside():
    files = [
        placed(r"x\Akira (1988) CD1.avi", MovieOf("Akira", 1988, part=1)),
        placed(r"x\Akira (1988) CD2.avi", MovieOf("Akira", 1988, part=2)),
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    assert [(c.kind, str(c.target)) for c in changes] == [
        (ChangeKind.MOVE, r"D:\Anime\Movies\Akira (1988)\Akira (1988) - pt1.avi"),
        (ChangeKind.MOVE, r"D:\Anime\Movies\Akira (1988)\Akira (1988) - pt2.avi"),
    ]
    assert [c.label for c in changes] == ["Akira · part 1", "Akira · part 2"]


def test_two_titles_of_one_name_and_year_are_never_copies_of_each_other():
    one = EpisodeOf("Hellsing", 2001, season=1, episode=1, title_id=1)
    other = EpisodeOf("Hellsing", 2001, season=1, episode=1, title_id=2)

    changes = plan_tidy(
        [placed(r"x\a.mkv", one), placed(r"y\b.mkv", other)], LIBRARY, day=DAY
    ).changes

    assert {c.kind for c in changes} == {ChangeKind.MOVE}


def test_two_copies_sharing_one_subtitle_file_leave_it_with_the_one_kept():
    kept, copy = LIBRARY / "Downloads" / "Ep.mkv", LIBRARY / "Downloads" / "Ep.mp4"
    subtitles = (kept.with_suffix(".srt"),)
    files = [
        PlacedFile(Copy(kept, media(720)), BEBOP_1, subtitles),
        PlacedFile(Copy(copy, media(480)), BEBOP_1, subtitles),
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    assert [(c.kind, c.source.name) for c in changes] == [
        (ChangeKind.QUARANTINE, "Ep.mp4"),
        (ChangeKind.MOVE, "Ep.mkv"),
        (ChangeKind.MOVE, "Ep.srt"),
    ]


def test_a_subtitle_two_videos_names_fit_goes_with_one_of_them_only():
    first, second = LIBRARY / "x" / "Ep.mkv", LIBRARY / "x" / "Ep.mp4"
    subtitles = (first.with_suffix(".srt"),)
    files = [
        PlacedFile(Copy(first, media(720)), BEBOP_1, subtitles),
        PlacedFile(Copy(second, media(720)), EpisodeOf("Cowboy Bebop", 1998, 1, 2), subtitles),
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY).changes

    assert sorted(c.source.name for c in changes) == ["Ep.mkv", "Ep.mp4", "Ep.srt"]


def test_a_subtitle_whose_new_name_is_too_long_keeps_its_video_where_it_is():
    deep = PureWindowsPath("D:\\" + "\\".join(["Folder"] * 26))
    video = deep / "x.mkv"
    subtitle = video.with_name("x." + "a" * 40 + ".en.srt")
    file = PlacedFile(Copy(video, media(480)), BEBOP_1, (subtitle,))

    plan = plan_tidy([file], deep, day=DAY)

    assert plan.changes == ()
    assert plan.skipped == ((video, "The new name would be too long for Windows"),)


def test_a_folder_scans_never_look_into_is_never_a_place_to_file():
    hidden = EpisodeOf("System Volume Information", None, season=1, episode=1)

    plan = plan_tidy([placed(r"x\a.mkv", hidden)], LIBRARY, day=DAY)

    assert plan.changes == ()
    assert plan.skipped == ((LIBRARY / "x" / "a.mkv", "Scans never look in a folder named so"),)


def test_kept_names_go_into_the_shows_folders_as_they_are():
    files = [
        placed(r"Downloads\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv", BEBOP_1),
        placed(r"Movies\cowboy bebop movie.mkv", BEBOP_MOVIE),
    ]

    changes = plan_tidy(files, LIBRARY, day=DAY, keep_names=True).changes

    assert [str(c.target) for c in changes] == [
        r"D:\Anime\Movies\Cowboy Bebop - The Movie (2001)\cowboy bebop movie.mkv",
        r"D:\Anime\TV\Cowboy Bebop (1998)\Season 01\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv",
    ]


def test_deleting_sets_a_video_aside_with_its_subtitles_under_names_still_free():
    video = LIBRARY / "TV" / "Trigun (1998)" / "Season 01" / "Trigun (1998) - S01E03.mkv"
    subtitles = (video.with_name("Trigun (1998) - S01E03.en.srt"),)
    earlier = quarantine_place(video, DAY)  # one set aside earlier today has its name

    plan = plan_set_aside([(video, "Trigun · S01E03", subtitles)], day=DAY, taken={str(earlier)})

    assert [(c.kind, c.source.name, str(c.target), c.label, c.reason) for c in plan.changes] == [
        (
            ChangeKind.QUARANTINE,
            "Trigun (1998) - S01E03.mkv",
            r"D:\Kura quarantine\2026-10-10\Trigun (1998) - S01E03 (2).mkv",
            "Trigun · S01E03",
            DELETED,
        ),
        (
            ChangeKind.QUARANTINE,
            "Trigun (1998) - S01E03.en.srt",
            r"D:\Kura quarantine\2026-10-10\Trigun (1998) - S01E03 (2).en.srt",
            "Trigun · S01E03 · subtitles",
            DELETED,
        ),
    ]
