"""Reading ffprobe's report. Fixtures mirror real `ffprobe -show_format -show_streams` output."""

from fractions import Fraction

from kura.core.media import media_from_ffprobe

DVD_RIP_MKV: dict[str, object] = {
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_type": "video",
            "width": 720,
            "height": 480,
            "sample_aspect_ratio": "8:9",
            "display_aspect_ratio": "4:3",
            "pix_fmt": "yuv420p",
            "field_order": "progressive",
            "avg_frame_rate": "24000/1001",
            "r_frame_rate": "24000/1001",
            "disposition": {"default": 1, "attached_pic": 0},
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_type": "audio",
            "channels": 2,
            "tags": {"language": "jpn"},
        },
        {
            "index": 2,
            "codec_name": "ass",
            "codec_type": "subtitle",
            "tags": {"language": "eng", "title": "Full Subtitles"},
            "disposition": {"default": 1, "forced": 0},
        },
        {
            "index": 3,
            "codec_name": "ttf",
            "codec_type": "attachment",
            "tags": {"filename": "arial.ttf", "mimetype": "application/x-truetype-font"},
        },
        {
            "index": 4,
            "codec_name": "otf",
            "codec_type": "attachment",
            "tags": {"filename": "title.otf", "mimetype": "font/otf"},
        },
    ],
    "chapters": [{"id": 0}, {"id": 1}, {"id": 2}],
    "format": {
        "format_name": "matroska,webm",
        "duration": "1440.064000",
        "size": "244318208",
        "tags": {"ENCODER": "libebml v1.4.2"},
    },
}

BLURAY_HEVC_FLAC: dict[str, object] = {
    "streams": [
        {
            "codec_name": "hevc",
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "16:9",
            "pix_fmt": "yuv420p10le",
            "avg_frame_rate": "24000/1001",
        },
        {"codec_name": "flac", "codec_type": "audio", "channels": 2, "tags": {"language": "jpn"}},
        {"codec_name": "aac", "codec_type": "audio", "channels": 2, "tags": {"language": "eng"}},
        {
            "codec_name": "hdmv_pgs_subtitle",
            "codec_type": "subtitle",
            "tags": {"language": "eng"},
            "disposition": {"forced": 1},
        },
    ],
    "format": {"format_name": "matroska,webm", "duration": "1420.5", "size": "1181116006"},
}

XVID_AVI: dict[str, object] = {
    "streams": [
        {
            "codec_name": "mpeg4",
            "codec_type": "video",
            "width": 640,
            "height": 480,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "2997/125",
        },
        {"codec_name": "mp3", "codec_type": "audio", "channels": 2},
    ],
    "format": {"format_name": "avi", "duration": "1380.2", "size": "183500800"},
}

INTERLACED_VOB: dict[str, object] = {
    "streams": [
        {
            "codec_name": "mpeg2video",
            "codec_type": "video",
            "width": 720,
            "height": 576,
            "sample_aspect_ratio": "16:15",
            "display_aspect_ratio": "4:3",
            "pix_fmt": "yuv420p",
            "field_order": "tt",
            "avg_frame_rate": "25/1",
        },
        {"codec_name": "ac3", "codec_type": "audio", "channels": 6},
        {"codec_name": "pcm_s16be", "codec_type": "audio", "channels": 2},
        {"codec_name": "dvd_subtitle", "codec_type": "subtitle"},
    ],
    "format": {"format_name": "mpeg", "duration": "5520.0", "size": "1073741824"},
}

MP4_WITH_COVER: dict[str, object] = {
    "streams": [
        {
            "codec_name": "mjpeg",
            "codec_type": "video",
            "width": 600,
            "height": 900,
            "disposition": {"attached_pic": 1},
        },
        {
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1280,
            "height": 720,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "0/0",
            "r_frame_rate": "24000/1001",
        },
        {"codec_name": "aac", "codec_type": "audio", "channels": 2, "tags": {"language": "und"}},
    ],
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "1420.0", "size": "419430400"},
}


def test_a_dvd_rip_in_mkv():
    media = media_from_ffprobe(DVD_RIP_MKV)

    assert media.container == "mkv"
    assert media.duration == 1440.064
    assert media.size == 244_318_208
    assert media.video is not None
    assert (media.video.codec, media.video.width, media.video.height) == ("h264", 720, 480)
    assert media.video.display_aspect == Fraction(4, 3)
    assert media.video.frame_rate == Fraction(24000, 1001)
    assert (media.video.bit_depth, media.video.interlaced) == (8, False)
    assert [(audio.codec, audio.language, audio.lossless) for audio in media.audio] == [
        ("aac", "jpn", False)
    ]
    assert [(sub.codec, sub.language, sub.text) for sub in media.subtitles] == [
        ("ass", "eng", True)
    ]
    assert (media.fonts, media.chapters) == (2, 3)


def test_a_bluray_rip_with_lossless_audio_and_picture_subtitles():
    media = media_from_ffprobe(BLURAY_HEVC_FLAC)

    assert media.video is not None
    assert (media.video.codec, media.video.bit_depth) == ("hevc", 10)
    assert media.video.display_aspect == Fraction(16, 9)
    assert media.video.interlaced is None  # ffprobe didn't say; checked later
    assert [audio.lossless for audio in media.audio] == [True, False]
    assert [(sub.text, sub.forced) for sub in media.subtitles] == [(False, True)]


def test_an_old_xvid_avi():
    media = media_from_ffprobe(XVID_AVI)

    assert media.container == "avi"
    assert media.video is not None
    assert media.video.codec == "mpeg4"
    assert media.video.display_aspect == Fraction(4, 3)  # no aspect given: square pixels
    assert media.video.frame_rate == Fraction(2997, 125)
    assert media.audio[0].language is None
    assert media.subtitles == ()


def test_an_interlaced_dvd_vob():
    media = media_from_ffprobe(INTERLACED_VOB)

    assert media.container == "mpeg"
    assert media.video is not None
    assert (media.video.height, media.video.interlaced) == (576, True)
    assert media.video.display_aspect == Fraction(4, 3)
    assert [(audio.codec, audio.channels, audio.lossless) for audio in media.audio] == [
        ("ac3", 6, False),
        ("pcm_s16be", 2, True),
    ]
    assert [sub.text for sub in media.subtitles] == [False]


def test_cover_art_is_not_the_video_and_a_missing_average_rate_falls_back():
    media = media_from_ffprobe(MP4_WITH_COVER)

    assert media.container == "mp4"
    assert media.video is not None
    assert (media.video.codec, media.video.height) == ("h264", 720)
    assert media.video.frame_rate == Fraction(24000, 1001)
    assert media.audio[0].language is None  # "und" means unknown


def test_a_file_ffprobe_can_barely_read():
    media = media_from_ffprobe({"format": {"format_name": "matroska,webm"}})

    assert (media.video, media.duration, media.size) == (None, None, None)
    assert media.audio == ()


def test_kuras_own_tag_is_found_whatever_its_case():
    report: dict[str, object] = {
        "format": {"format_name": "matroska,webm", "tags": {"kura": "Cinema 1080p; 2026-10-10"}}
    }

    assert media_from_ffprobe(report).kura_tag == "Cinema 1080p; 2026-10-10"
    assert media_from_ffprobe(DVD_RIP_MKV).kura_tag is None
