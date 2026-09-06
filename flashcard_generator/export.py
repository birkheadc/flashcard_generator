from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

import genanki
import soundfile as sf

from .items import Item, ItemList
from .template import NoteTemplate, cloze_wrapped_text

# genanki recommends model/deck IDs be random 32-bit-ish integers, chosen to
# stay clear of Anki's own low-valued built-in IDs. Deriving them from a
# stable hash (rather than random.randrange, genanki's own suggestion) means
# re-exporting the same template/deck name reuses the same Anki note
# type/deck instead of spawning a new one on every export.
_ID_RANGE_START = 1 << 30
_ID_RANGE_SIZE = 1 << 30


def _stable_id(*parts: str) -> int:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return _ID_RANGE_START + (int.from_bytes(digest[:4], "big") % _ID_RANGE_SIZE)


@dataclass
class ExportIssue:
    """One item that's missing data required for a real card — DESIGN.md
    §9 requires these be surfaced and block export by default, rather than
    silently producing an incomplete `.apkg`."""

    item_index: int
    reason: str  # "no text" | "no cloze"


class ExportBlockedError(Exception):
    """Raised by `export_apkg` when incomplete items exist and the caller
    didn't pass `skip_incomplete=True` — DESIGN.md §9's "export anyway,
    skipping N incomplete items" override."""

    def __init__(self, issues: list[ExportIssue]):
        self.issues = issues
        super().__init__(f"{len(issues)} item(s) are missing required data")


def find_export_issues(items: ItemList) -> list[ExportIssue]:
    """Items that would produce a broken/empty card: no text at all, or
    text with no cloze marked (a cloze note with no `{{cN::...}}` generates
    zero cards in real Anki)."""
    issues = []
    for i, item in enumerate(items):
        if not item.text.strip():
            issues.append(ExportIssue(i, "no text"))
        elif not item.has_cloze:
            issues.append(ExportIssue(i, "no cloze"))
    return issues


def default_deck_name(audio_path: str) -> str:
    return Path(audio_path).stem


def _audio_field_name(template: NoteTemplate) -> str | None:
    for name in template.fields:
        if name.strip().lower() == "audio":
            return name
    return None


def _field_values_for_export(
    item: Item, template: NoteTemplate, audio_field: str | None, media_filename: str
) -> list[str]:
    values = []
    for i, name in enumerate(template.fields):
        if i == 0:
            values.append(cloze_wrapped_text(item.text, item.valid_cloze_spans()))
        elif name == audio_field:
            values.append(f"[sound:{media_filename}]")
        else:
            values.append(item.extra_fields.get(name, ""))
    return values


def _write_clip_media(audio_path: str, item: Item, dest_path: Path) -> None:
    info = sf.info(audio_path)
    start_frame = max(0, round(item.clip.start_seconds * info.samplerate))
    end_frame = min(info.frames, round(item.clip.end_seconds * info.samplerate))
    data, samplerate = sf.read(
        audio_path, start=start_frame, stop=end_frame, dtype="float32", always_2d=True
    )
    sf.write(str(dest_path), data, samplerate)


def export_apkg(
    items: ItemList,
    template: NoteTemplate,
    audio_path: str,
    deck_name: str,
    output_path: str,
    skip_incomplete: bool = False,
) -> None:
    """Build a single `.apkg` (OUTLINE.md §2.3/ROADMAP.md Phase 6): one
    genanki cloze `Model` from the configured `template`, one `Note` per
    item with its clip audio sliced out and embedded as media.

    Raises `ExportBlockedError` (carrying the offending items) if any item
    is missing text or a cloze span, unless `skip_incomplete` is set —
    DESIGN.md §9's block-by-default/explicit-override behavior.
    """
    issues = find_export_issues(items)
    if issues and not skip_incomplete:
        raise ExportBlockedError(issues)
    skip_indices = {issue.item_index for issue in issues}

    model = genanki.Model(
        _stable_id("model", template.name),
        template.name,
        fields=[{"name": name} for name in template.fields],
        templates=[
            {
                "name": template.name,
                "qfmt": template.front_template,
                "afmt": template.back_template,
            }
        ],
        model_type=genanki.Model.CLOZE,
    )
    deck = genanki.Deck(_stable_id("deck", deck_name), deck_name)
    audio_field = _audio_field_name(template)

    with tempfile.TemporaryDirectory(prefix="flashcard_generator_export_") as media_dir:
        media_files = []
        for i, item in enumerate(items):
            if i in skip_indices:
                continue
            media_filename = f"clip_{i:04d}.wav"
            media_path = Path(media_dir) / media_filename
            _write_clip_media(audio_path, item, media_path)
            media_files.append(str(media_path))

            values = _field_values_for_export(item, template, audio_field, media_filename)
            note = genanki.Note(
                model=model,
                fields=values,
                guid=genanki.guid_for(
                    audio_path, item.clip.start_seconds, item.clip.end_seconds
                ),
            )
            deck.add_note(note)

        genanki.Package(deck, media_files).write_to_file(output_path)
