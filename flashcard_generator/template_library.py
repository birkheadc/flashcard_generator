from __future__ import annotations

import json
import os
from pathlib import Path

from .template import DEFAULT_BACK_TEMPLATE, DEFAULT_FIELDS, DEFAULT_FRONT_TEMPLATE, NoteTemplate


def default_template_library_path() -> Path:
    return Path.home() / ".flashcard_generator" / "templates.json"


def load_template_library(path: Path) -> list[NoteTemplate]:
    """Load the user's saved note-type presets (ROADMAP.md Phase 5.5) —
    distinct from a session's currently active template (session.py),
    which need not be saved here at all. Best-effort: a missing or
    corrupted file just means an empty library, not a crash."""
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [
            NoteTemplate(
                name=entry["name"],
                fields=entry.get("fields") or list(DEFAULT_FIELDS),
                front_template=entry.get("front_template", DEFAULT_FRONT_TEMPLATE),
                back_template=entry.get("back_template", DEFAULT_BACK_TEMPLATE),
            )
            for entry in raw.get("templates", [])
        ]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return []


def save_template_library(path: Path, templates: list[NoteTemplate]) -> None:
    data = {
        "templates": [
            {
                "name": t.name,
                "fields": t.fields,
                "front_template": t.front_template,
                "back_template": t.back_template,
            }
            for t in templates
        ]
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)  # atomic on POSIX and Windows
    except OSError:
        pass
