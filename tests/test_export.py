from __future__ import annotations

import json
import sqlite3
import zipfile

import pytest
import soundfile as sf

from flashcard_generator.clips import Clip
from flashcard_generator.export import (
    ExportBlockedError,
    ExportIssue,
    default_deck_name,
    export_apkg,
    find_export_issues,
)
from flashcard_generator.items import ClozeSpan, Item, ItemList
from flashcard_generator.template import NoteTemplate


def _read_notes(apkg_path):
    with zipfile.ZipFile(apkg_path) as z:
        media = json.loads(z.read("media"))
        z.extract("collection.anki2", apkg_path.parent)
    conn = sqlite3.connect(apkg_path.parent / "collection.anki2")
    try:
        rows = conn.execute("select flds from notes").fetchall()
    finally:
        conn.close()
    return [row[0].split("\x1f") for row in rows], media


def test_default_deck_name_uses_audio_filename_stem():
    assert default_deck_name("/some/dir/My Recording.wav") == "My Recording"


def test_find_export_issues_flags_missing_text():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text=""))
    issues = find_export_issues(items)
    assert issues == [ExportIssue(0, "no text")]


def test_find_export_issues_flags_missing_cloze():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text="hello world"))
    issues = find_export_issues(items)
    assert issues == [ExportIssue(0, "no cloze")]


def test_find_export_issues_empty_when_all_items_ready():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text="hello", cloze_spans=[ClozeSpan(0, 5)]))
    assert find_export_issues(items) == []


def test_export_apkg_raises_when_incomplete_items_exist(wav_file, tmp_path):
    path = wav_file(duration_seconds=2.0)
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text=""))

    with pytest.raises(ExportBlockedError) as excinfo:
        export_apkg(items, NoteTemplate(), path, "Deck", str(tmp_path / "out.apkg"))
    assert excinfo.value.issues == [ExportIssue(0, "no text")]
    assert not (tmp_path / "out.apkg").exists()


def test_export_apkg_skip_incomplete_exports_only_ready_items(wav_file, tmp_path):
    path = wav_file(duration_seconds=2.0)
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text="hello", cloze_spans=[ClozeSpan(0, 5)]))
    items.add(Item(clip=Clip(1.0, 2.0), text=""))
    out_path = tmp_path / "out.apkg"

    export_apkg(items, NoteTemplate(), path, "Deck", str(out_path), skip_incomplete=True)

    notes, media = _read_notes(out_path)
    assert len(notes) == 1
    assert notes[0][0] == "{{c1::hello}}"
    assert len(media) == 1


def test_export_apkg_embeds_a_sound_reference_in_the_audio_field(wav_file, tmp_path):
    path = wav_file(duration_seconds=2.0)
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text="hello", cloze_spans=[ClozeSpan(0, 5)]))
    out_path = tmp_path / "out.apkg"

    export_apkg(items, NoteTemplate(), path, "Deck", str(out_path))

    notes, media = _read_notes(out_path)
    audio_field = notes[0][1]
    assert audio_field.startswith("[sound:")
    referenced_filename = audio_field[len("[sound:") : -1]
    assert referenced_filename in media.values()


def test_export_apkg_media_file_matches_clip_duration(wav_file, tmp_path):
    path = wav_file(duration_seconds=5.0)
    items = ItemList()
    items.add(Item(clip=Clip(1.0, 2.5), text="hello", cloze_spans=[ClozeSpan(0, 5)]))
    out_path = tmp_path / "out.apkg"

    export_apkg(items, NoteTemplate(), path, "Deck", str(out_path))

    with zipfile.ZipFile(out_path) as z:
        z.extract("0", tmp_path)
    info = sf.info(str(tmp_path / "0"))
    assert info.duration == pytest.approx(1.5, abs=0.05)


def test_export_apkg_extra_fields_are_written_to_note(wav_file, tmp_path):
    path = wav_file(duration_seconds=2.0)
    template = NoteTemplate(fields=["Text", "Audio", "Definition"])
    items = ItemList()
    items.add(
        Item(
            clip=Clip(0.0, 1.0),
            text="hello",
            cloze_spans=[ClozeSpan(0, 5)],
            extra_fields={"Definition": "a greeting"},
        )
    )
    out_path = tmp_path / "out.apkg"

    export_apkg(items, template, path, "Deck", str(out_path))

    notes, _ = _read_notes(out_path)
    assert notes[0][2] == "a greeting"


def test_export_apkg_multi_cloze_item_generates_multiple_cards(wav_file, tmp_path):
    path = wav_file(duration_seconds=2.0)
    items = ItemList()
    items.add(
        Item(
            clip=Clip(0.0, 1.0),
            text="one two three",
            cloze_spans=[ClozeSpan(0, 3), ClozeSpan(8, 13)],
        )
    )
    out_path = tmp_path / "out.apkg"

    export_apkg(items, NoteTemplate(), path, "Deck", str(out_path))

    with zipfile.ZipFile(out_path) as z:
        z.extract("collection.anki2", out_path.parent)
    conn = sqlite3.connect(out_path.parent / "collection.anki2")
    try:
        (count,) = conn.execute("select count(*) from cards").fetchone()
    finally:
        conn.close()
    assert count == 2


def test_export_apkg_reexport_reuses_the_same_model_and_deck_ids(wav_file, tmp_path):
    path = wav_file(duration_seconds=2.0)
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text="hello", cloze_spans=[ClozeSpan(0, 5)]))
    template = NoteTemplate()

    out_path_1 = tmp_path / "out1.apkg"
    out_path_2 = tmp_path / "out2.apkg"
    export_apkg(items, template, path, "Deck", str(out_path_1))
    export_apkg(items, template, path, "Deck", str(out_path_2))

    def _model_and_deck_ids(apkg_path):
        with zipfile.ZipFile(apkg_path) as z:
            z.extract("collection.anki2", apkg_path.parent / apkg_path.stem)
        conn = sqlite3.connect(apkg_path.parent / apkg_path.stem / "collection.anki2")
        try:
            (models_json,) = conn.execute("select models from col").fetchone()
            (decks_json,) = conn.execute("select decks from col").fetchone()
        finally:
            conn.close()
        return set(json.loads(models_json)), set(json.loads(decks_json))

    models_1, decks_1 = _model_and_deck_ids(out_path_1)
    models_2, decks_2 = _model_and_deck_ids(out_path_2)
    assert models_1 == models_2
    assert decks_1 == decks_2
