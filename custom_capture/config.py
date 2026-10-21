from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


APP_NAME = "CustomCapture"
SETTINGS_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
SETTINGS_PATH = SETTINGS_DIR / "settings.json"


def default_downloads_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads"


@dataclass(slots=True)
class Settings:
    hotkey: str = "Win+Shift+S"
    save_dir: str = str(default_downloads_dir())
    copy_to_clipboard: bool = True
    min_selection_size: int = 3


def load_settings() -> Settings:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings()

    if SETTINGS_PATH.exists():
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}

        if isinstance(raw, dict):
            for field_name in asdict(settings):
                if field_name in raw:
                    setattr(settings, field_name, raw[field_name])

    save_settings(settings)
    return settings


def save_settings(settings: Settings) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(settings)
    SETTINGS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
