from __future__ import annotations

import sqlite3
import zipfile

from PySide6.QtWidgets import QFileDialog, QLabel

from flashcard_generator.clips import Clip
from flashcard_generator.export import default_deck_name
from flashcard_generator.items import ClozeSpan, Item, ItemList
from flashcard_generator.template import NoteTemplate
from flashcard_generator.ui.export_dialog import ExportDialog


def _ready_item(start=0.0, end=1.0, text="hello"):
    return Item(clip=Clip(start, end), text=text, cloze_spans=[ClozeSpan(0, len(text))])


def _make_dialog(items, path, deck_name=None, template=None):
    if deck_name is None:
        deck_name = default_deck_name(path)
    return ExportDialog(items, template or NoteTemplate(), path, deck_name, None)


def test_dialog_displays_the_passed_in_deck_name(qtbot, wav_file):
    path = wav_file()
    items = ItemList()
    items.add(_ready_item())

    dialog = _make_dialog(items, path, deck_name="My Existing Deck")
    qtbot.addWidget(dialog)

    labels = [w.text() for w in dialog.findChildren(QLabel)]
    assert "My Existing Deck" in labels


def test_export_uses_the_passed_in_deck_name(qtbot, wav_file, tmp_path, monkeypatch):
    path = wav_file()
    items = ItemList()
    items.add(_ready_item())
    out_path = tmp_path / "out.apkg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out_path), ""))

    dialog = _make_dialog(items, path, deck_name="My Existing Deck")
    qtbot.addWidget(dialog)
    dialog._on_browse_clicked()
    dialog._on_export_clicked()

    with zipfile.ZipFile(out_path) as z:
        z.extract("collection.anki2", tmp_path)
    conn = sqlite3.connect(tmp_path / "collection.anki2")
    try:
        (decks_json,) = conn.execute("select decks from col").fetchone()
    finally:
        conn.close()
    assert "My Existing Deck" in decks_json


def test_export_button_disabled_until_output_path_chosen(qtbot, wav_file):
    path = wav_file()
    items = ItemList()
    items.add(_ready_item())

    dialog = _make_dialog(items, path)
    qtbot.addWidget(dialog)

    assert not dialog._export_button.isEnabled()


def test_browsing_sets_output_path_and_enables_export(qtbot, wav_file, tmp_path, monkeypatch):
    path = wav_file()
    items = ItemList()
    items.add(_ready_item())
    out_path = str(tmp_path / "deck.apkg")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out_path, ""))

    dialog = _make_dialog(items, path)
    qtbot.addWidget(dialog)
    dialog._on_browse_clicked()

    assert dialog._output_path_edit.text() == out_path
    assert dialog._export_button.isEnabled()


def test_no_issues_section_shown_when_all_items_ready(qtbot, wav_file):
    path = wav_file()
    items = ItemList()
    items.add(_ready_item())

    dialog = _make_dialog(items, path)
    qtbot.addWidget(dialog)

    assert dialog._skip_checkbox is None
    assert "1 item" in dialog._summary_label.text()
    assert "1 ready" in dialog._summary_label.text()


def test_incomplete_items_block_export_until_checkbox_checked(
    qtbot, wav_file, tmp_path, monkeypatch
):
    path = wav_file()
    items = ItemList()
    items.add(_ready_item())
    items.add(Item(clip=Clip(1.0, 2.0), text=""))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "deck.apkg"), "")
    )

    dialog = _make_dialog(items, path)
    qtbot.addWidget(dialog)
    dialog._on_browse_clicked()

    assert dialog._skip_checkbox is not None
    assert not dialog._export_button.isEnabled()

    dialog._skip_checkbox.setChecked(True)
    assert dialog._export_button.isEnabled()


def test_successful_export_shows_reveal_and_close(qtbot, wav_file, tmp_path, monkeypatch):
    path = wav_file()
    items = ItemList()
    items.add(_ready_item())
    out_path = tmp_path / "deck.apkg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out_path), ""))

    dialog = _make_dialog(items, path)
    qtbot.addWidget(dialog)
    dialog._on_browse_clicked()
    dialog._on_export_clicked()

    assert out_path.exists()
    labels = [w.text() for w in dialog.findChildren(QLabel)]
    assert any(str(out_path) in text for text in labels)
    buttons = [b.text() for b in dialog.findChildren(type(dialog._export_button))]
    assert "Reveal in File Manager" in buttons
    assert "Close" in buttons
