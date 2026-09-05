from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .clips import Clip
from .items import Item, ItemList


def default_session_path() -> Path:
    return Path.home() / ".flashcard_generator" / "session.json"


@dataclass
class SessionData:
    audio_path: str
    items: list[Item]
    transcript_text: str


def save_session(
    path: Path,
    audio_path: str,
    items: ItemList,
    transcript_text: str = "",
) -> None:
    """Best-effort autosave: failures are swallowed rather than surfaced,
    since this runs after nearly every edit and shouldn't interrupt work.
    """
    data = {
        "audio_path": audio_path,
        "items": [
            {
                "start_seconds": item.clip.start_seconds,
                "end_seconds": item.clip.end_seconds,
                "text": item.text,
            }
            for item in items
        ],
        "transcript_text": transcript_text,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)  # atomic on POSIX and Windows
    except OSError:
        pass


def load_session(path: Path) -> SessionData | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = [
            Item(
                clip=Clip(
                    start_seconds=entry["start_seconds"], end_seconds=entry["end_seconds"]
                ),
                text=entry.get("text", ""),
            )
            for entry in raw["items"]
        ]
        return SessionData(
            audio_path=raw["audio_path"],
            items=items,
            transcript_text=raw.get("transcript_text", ""),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
