"""Stands in for ffprobe in tests: python fake_ffprobe.py <ffprobe's arguments> <file>.

Answers with a report for a 720x540 HEVC 10-bit episode, fails like ffprobe for files whose name
holds "broken", and never answers for files whose name holds "stuck".
"""

import json
import sys
import time
from pathlib import Path

REPORT = {
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "hevc",
            "width": 720,
            "height": 540,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "4:3",
            "r_frame_rate": "24000/1001",
            "avg_frame_rate": "24000/1001",
            "pix_fmt": "yuv420p10le",
            "field_order": "progressive",
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "channels": 2,
            "tags": {"language": "jpn"},
        },
    ],
    "format": {"format_name": "matroska,webm", "duration": "1244.202000", "size": "130000000"},
    "chapters": [],
}


def main() -> None:
    file = Path(sys.argv[-1])
    if "stuck" in file.name:
        time.sleep(60)
    if "broken" in file.name:
        print(f"{file}: Invalid data found when processing input", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(REPORT))


if __name__ == "__main__":
    main()
