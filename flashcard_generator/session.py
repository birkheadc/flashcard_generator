from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .clips import Clip
from .items import ClozeSpan, Item, ItemList
from .template import (
    DEFAULT_BACK_TEMPLATE,
    DEFAULT_FIELDS,
    DEFAULT_FRONT_TEMPLATE,
    DEFAULT_TEMPLATE_NAME,
    NoteTemplate,
)


def default_session_path() -> Path:
    return Path.home() / ".flashcard_generator" / "session.json"


def _load_cloze_spans(entry: dict) -> list[ClozeSpan]:
    raw_spans = entry.get("cloze_spans")
    if raw_spans is not None:
        return [ClozeSpan(start=start, end=end) for start, end in raw_spans]
    # Backward compat with the pre-Phase-5.5 single-span format
    # ("cloze_start"/"cloze_end" directly on the item).
    start, end = entry.get("cloze_start"), entry.get("cloze_end")
    if start is not None and end is not None:
        return [ClozeSpan(start=start, end=end)]
    return []


@dataclass
class SessionData:
    audio_path: str
    items: list[Item]
    transcript_text: str
    template: NoteTemplate


def save_session(
    path: Path,
    audio_path: str,
    items: ItemList,
    transcript_text: str = "",
    template: NoteTemplate | None = None,
) -> None:
    """Best-effort autosave: failures are swallowed rather than surfaced,
    since this runs after nearly every edit and shouldn't interrupt work.
    """
    if template is None:
        template = NoteTemplate()
    data = {
        "audio_path": audio_path,
        "items": [
            {
                "start_seconds": item.clip.start_seconds,
                "end_seconds": item.clip.end_seconds,
                "text": item.text,
                "cloze_spans": [[s.start, s.end] for s in item.cloze_spans],
                "extra_fields": item.extra_fields,
            }
            for item in items
        ],
        "transcript_text": transcript_text,
        "template": {
            "name": template.name,
            "fields": template.fields,
            "front_template": template.front_template,
            "back_template": template.back_template,
        },
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
                cloze_spans=_load_cloze_spans(entry),
                extra_fields=entry.get("extra_fields") or {},
            )
            for entry in raw["items"]
        ]
        template_raw = raw.get("template") or {}
        template = NoteTemplate(
            name=template_raw.get("name", DEFAULT_TEMPLATE_NAME),
            fields=template_raw.get("fields") or list(DEFAULT_FIELDS),
            front_template=template_raw.get("front_template", DEFAULT_FRONT_TEMPLATE),
            back_template=template_raw.get("back_template", DEFAULT_BACK_TEMPLATE),
        )
        return SessionData(
            audio_path=raw["audio_path"],
            items=items,
            transcript_text=raw.get("transcript_text", ""),
            template=template,
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
