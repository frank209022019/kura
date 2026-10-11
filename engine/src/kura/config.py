"""Where Kura keeps its data."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    """Kura's data folder: the database, artwork, backups and logs. Anime files never go here."""

    root: Path

    @property
    def database(self) -> Path:
        return self.root / "kura.db"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def tools(self) -> Path:
        """What Kura downloads to work with, such as ffmpeg (see downloads.json)."""
        return self.root / "tools"

    @classmethod
    def default(cls) -> DataPaths:
        r"""%LOCALAPPDATA%\Kura, or the folder in KURA_DATA_DIR when that is set."""
        if override := os.environ.get("KURA_DATA_DIR"):
            return cls(Path(os.path.normpath(override)))
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return cls(base / "Kura")
