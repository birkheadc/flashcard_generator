from __future__ import annotations

import pytest
from PySide6.QtGui import QAction, QInputMethodEvent, QTextCursor
from PySide6.QtWidgets import QFileDialog, QLabel, QLineEdit, QMessageBox

from flashcard_generator.clips import Clip
from flashcard_generator.items import Item, ItemList
from flashcard_generator.session import load_session, save_session
from flashcard_generator.template import NoteTemplate
from flashcard_generator.ui.main_window import (
    RANGE_COLUMN,
    STATE_COLUMN,
    TEXT_COLUMN,
    ItemTextEdit,
    MainWindow,
)


def _select_substring(text_edit, substring: str) -> None:
    """Test helper: select the given substring within a QPlainTextEdit,
    mimicking a user highlighting a span of the transcript by hand."""
    text = text_edit.toPlainText()
    start = text.index(substring)
    cursor = text_edit.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + len(substring), QTextCursor.MoveMode.KeepAnchor)
    text_edit.setTextCursor(cursor)


def _sample_data_input(dialog, field_name: str) -> QLineEdit:
    """Test helper: find the editable sample-data QLineEdit for a given
    field in the Note Template dialog's Live Preview panel."""
    for i in range(dialog._sample_data_layout.count()):
        row = dialog._sample_data_layout.itemAt(i).widget()
        label = row.findChild(QLabel)
        if label is not None and label.text() == field_name:
            return row.findChild(QLineEdit)
    raise AssertionError(f"no sample-data input for field {field_name!r}")


def test_import_loads_audio_and_enables_playback(qtbot, wav_file):
    path = wav_file(duration_seconds=1.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)

    assert window._play_button.isEnabled()
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)
    assert window._duration_ms == pytest.approx(1000, abs=50)


def test_play_pause_toggles_button_label(qtbot, wav_file):
    path = wav_file(duration_seconds=1.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._toggle_playback()
    qtbot.waitUntil(lambda: window._play_button.text() == "Pause", timeout=3000)

    window._toggle_playback()
    qtbot.waitUntil(lambda: window._play_button.text() == "Play", timeout=3000)


def test_seek_moves_player_position(qtbot, wav_file):
    path = wav_file(duration_seconds=2.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._seek_to_seconds(1.0)

    qtbot.waitUntil(lambda: window._player.position() > 0, timeout=3000)
    assert window._player.position() == pytest.approx(1000, abs=100)


def test_record_action_is_disabled_stub(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    record_actions = [a for a in window.findChildren(QAction) if a.text() == "Record in-app"]

    assert len(record_actions) == 1
    assert not record_actions[0].isEnabled()
    assert record_actions[0].toolTip() == "Not yet implemented"


def test_import_long_audio_warns_and_aborts_if_declined(qtbot, wav_file, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: (warnings.append(args), QMessageBox.StandardButton.No)[1],
    )
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: critical_calls.append(args)
    )

    path = wav_file(duration_seconds=31 * 60, sample_rate=800)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)

    assert len(warnings) == 1
    assert "long" in warnings[0][1].lower()
    assert critical_calls == []
    assert not window._play_button.isEnabled()


def test_import_long_audio_proceeds_if_confirmed(qtbot, wav_file, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )

    path = wav_file(duration_seconds=31 * 60, sample_rate=800)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)

    assert window._play_button.isEnabled()
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)
    assert window._duration_ms == pytest.approx(31 * 60 * 1000, abs=100)


def test_selection_enables_add_item_button(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    assert not window._add_item_button.isEnabled()

    window._waveform._waveform.set_selection(1.0, 3.0)
    assert window._add_item_button.isEnabled()

    window._waveform.clear_selection()
    assert not window._add_item_button.isEnabled()


def test_add_item_appends_to_list_and_clears_selection(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 3.0)
    window._on_add_item_clicked()

    assert len(window._items) == 1
    assert window._items[0].clip.start_seconds == pytest.approx(1.0)
    assert window._items[0].clip.end_seconds == pytest.approx(3.0)
    assert window._items[0].text == ""
    assert window._item_list_widget.rowCount() == 1
    assert window._waveform.selection is None
    assert not window._add_item_button.isEnabled()


def test_remove_item_deletes_selected_row(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 3.0)
    window._on_add_item_clicked()
    window._waveform._waveform.set_selection(4.0, 6.0)
    window._on_add_item_clicked()

    window._item_list_widget.setCurrentRow(0)
    window._on_remove_item_clicked()

    assert len(window._items) == 1
    assert window._items[0].clip.start_seconds == pytest.approx(4.0)


def test_move_item_up_and_down_reorders(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._waveform._waveform.set_selection(3.0, 4.0)
    window._on_add_item_clicked()

    window._item_list_widget.setCurrentRow(1)
    window._on_move_item_up()

    assert [i.clip.start_seconds for i in window._items] == [3.0, 1.0]
    assert window._item_list_widget.currentRow() == 0

    window._on_move_item_down()

    assert [i.clip.start_seconds for i in window._items] == [1.0, 3.0]
    assert window._item_list_widget.currentRow() == 1


def test_loop_preview_seeks_back_to_item_start_past_end(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)

    window._on_preview_clicked()
    assert window._preview_button.text() == "Stop Preview"
    qtbot.waitUntil(lambda: window._player.position() > 0, timeout=3000)

    window._on_position_changed(2500)  # past the item's 2.0s end

    assert window._player.position() == pytest.approx(1000, abs=50)

    window._on_preview_clicked()
    assert window._preview_button.text() == "Loop Preview"
    assert window._loop_range is None
    assert window._loop_source is None


def test_play_selection_loop_seeks_back_to_selection_start_past_end(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    assert not window._play_selection_button.isEnabled()

    window._waveform._waveform.set_selection(1.0, 2.0)
    assert window._play_selection_button.isEnabled()

    window._on_play_selection_clicked()
    assert window._play_selection_button.text() == "Stop"
    qtbot.waitUntil(lambda: window._player.position() > 0, timeout=3000)

    window._on_position_changed(2500)  # past the selection's 2.0s end

    assert window._player.position() == pytest.approx(1000, abs=50)

    window._on_play_selection_clicked()
    assert window._play_selection_button.text() == "Play Selection (Loop)"
    assert window._loop_range is None
    assert window._loop_source is None


def test_clearing_selection_stops_selection_loop(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_play_selection_clicked()
    qtbot.waitUntil(lambda: window._player.position() > 0, timeout=3000)

    window._waveform.clear_selection()

    assert window._loop_source is None
    assert window._play_selection_button.text() == "Play Selection (Loop)"


def test_manual_seek_stops_active_loop(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_play_selection_clicked()
    qtbot.waitUntil(lambda: window._player.position() > 0, timeout=3000)

    window._seek_to_seconds(5.0)

    assert window._loop_source is None
    assert window._play_selection_button.text() == "Play Selection (Loop)"


def test_dragging_item_edge_on_waveform_updates_the_item(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 3.0)
    window._on_add_item_clicked()

    window._on_item_region_edited(0, 1.0, 5.0)

    assert window._items[0].clip.start_seconds == pytest.approx(1.0)
    assert window._items[0].clip.end_seconds == pytest.approx(5.0)
    assert window._item_list_widget.item(0, RANGE_COLUMN).text().startswith("0:01–0:05")


def test_editing_item_region_preserves_its_text(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 3.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    window._item_text_edit.setPlainText("hello world")

    window._on_item_region_edited(0, 1.0, 5.0)

    assert window._items[0].text == "hello world"


def test_loading_new_file_clears_items_if_confirmed(qtbot, wav_file, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    first_path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(first_path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    assert len(window._items) == 1

    second_path = wav_file(duration_seconds=5.0)
    window._load_audio_file(second_path)

    assert len(window._items) == 0
    assert window._item_list_widget.rowCount() == 0


def test_loading_new_file_with_items_warns_and_aborts_if_declined(qtbot, wav_file, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: (warnings.append(args), QMessageBox.StandardButton.No)[1],
    )
    first_path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(first_path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    original_title = window.windowTitle()

    second_path = wav_file(duration_seconds=5.0)
    window._load_audio_file(second_path)

    assert len(warnings) == 1
    assert "discard" in warnings[0][1].lower()
    assert len(window._items) == 1
    assert window.windowTitle() == original_title


def test_loading_new_file_without_items_does_not_warn(qtbot, wav_file, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args)
    )
    first_path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(first_path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    second_path = wav_file(duration_seconds=5.0)
    window._load_audio_file(second_path)

    assert warnings == []


def test_failed_import_shows_supported_formats_and_keeps_playback_disabled(
    qtbot, tmp_path, monkeypatch
):
    shown_messages = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: shown_messages.append(args)
    )

    window = MainWindow()
    qtbot.addWidget(window)

    bad_file = tmp_path / "not_audio.txt"
    bad_file.write_text("hello")

    window._load_audio_file(str(bad_file))

    assert not window._play_button.isEnabled()
    assert len(shown_messages) == 1
    message_text = shown_messages[0][2]
    assert "Supported file types" in message_text


# -- item text field (Phase 3) -------------------------------------------


def test_text_edit_disabled_until_an_item_is_selected(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    assert not window._item_text_edit.isEnabled()

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()

    assert window._item_text_edit.isEnabled()
    assert window._item_text_edit.toPlainText() == ""


def test_ime_composition_hides_placeholder_text(qtbot):
    edit = ItemTextEdit("Type the phrase text for the selected item…")
    qtbot.addWidget(edit)

    assert edit.placeholderText() != ""

    edit.inputMethodEvent(QInputMethodEvent("は", []))
    assert edit.placeholderText() == ""

    edit.inputMethodEvent(QInputMethodEvent("", []))
    assert edit.placeholderText() != ""


def test_typing_in_text_edit_saves_to_the_selected_item(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()

    window._item_text_edit.setPlainText("こんにちは")

    assert window._items[0].text == "こんにちは"
    assert "こんにちは" in window._item_list_widget.item(0, TEXT_COLUMN).text()


def test_selecting_a_different_item_loads_its_own_text(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("first item")

    window._waveform._waveform.set_selection(3.0, 4.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("second item")

    window._item_list_widget.setCurrentRow(0)
    assert window._item_text_edit.toPlainText() == "first item"

    window._item_list_widget.setCurrentRow(1)
    assert window._item_text_edit.toPlainText() == "second item"

    assert window._items[0].text == "first item"
    assert window._items[1].text == "second item"


def test_removing_item_deletes_it_regardless_of_text(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("has text")

    window._waveform._waveform.set_selection(3.0, 4.0)
    window._on_add_item_clicked()  # no text typed for this one

    assert len(window._items) == 2

    window._item_list_widget.setCurrentRow(0)
    window._on_remove_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    window._on_remove_item_clicked()

    assert len(window._items) == 0


# -- session persistence ---------------------------------------------------


def test_loading_audio_with_no_prior_session_starts_empty(qtbot, session_path):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._audio_path is None
    assert not session_path.exists()


def test_adding_item_autosaves_session(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()

    data = load_session(session_path)
    assert data is not None
    assert data.audio_path == window._audio_path
    assert len(data.items) == 1
    assert data.items[0].clip.start_seconds == pytest.approx(1.0)


def test_editing_text_autosaves_session(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("saved text")

    data = load_session(session_path)
    assert data.items[0].text == "saved text"


def test_removing_last_item_autosaves_empty_session(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    window._on_remove_item_clicked()

    data = load_session(session_path)
    assert data is not None
    assert data.items == []


def test_restoring_session_on_launch_reloads_audio_and_items(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)
    items = ItemList()
    items.add(Item(clip=Clip(1.0, 2.0), text="restored item"))
    save_session(session_path, path, items)

    window = MainWindow()
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    assert len(window._items) == 1
    assert window._items[0].text == "restored item"
    assert window._item_list_widget.rowCount() == 1
    assert window._play_button.isEnabled()


def test_restoring_session_with_missing_audio_shows_error_and_starts_empty(
    qtbot, tmp_path, session_path, monkeypatch
):
    shown_messages = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: shown_messages.append(args)
    )
    items = ItemList()
    items.add(Item(clip=Clip(1.0, 2.0), text="orphaned item"))
    save_session(session_path, str(tmp_path / "gone.wav"), items)

    window = MainWindow()
    qtbot.addWidget(window)

    assert len(shown_messages) == 1
    assert len(window._items) == 0
    assert not window._play_button.isEnabled()


def test_restoring_session_with_corrupted_file_starts_empty(qtbot, session_path):
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("not valid json", encoding="utf-8")

    window = MainWindow()
    qtbot.addWidget(window)

    assert len(window._items) == 0
    assert window._audio_path is None


# -- transcript import & matching (Phase 4) --------------------------------


def test_import_transcript_disabled_until_audio_is_loaded(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window._import_transcript_action.isEnabled()


def test_loading_audio_enables_import_transcript(qtbot, wav_file):
    path = wav_file(duration_seconds=5.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)

    assert window._import_transcript_action.isEnabled()


def test_import_transcript_populates_pane_and_reveals_it(qtbot, wav_file, tmp_path, monkeypatch):
    path = wav_file(duration_seconds=5.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window._load_audio_file(path)

    assert not window._transcript_panel.isVisible()

    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text("First section.\n\nSecond section.", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(transcript_path), "")
    )

    window._import_transcript()

    assert window._transcript_panel.isVisible()
    # The raw transcript is shown as-is, not split into pre-cut sections —
    # automatic splitting only makes sense once forced alignment (Phase 9)
    # exists to do it against known audio timing.
    assert window._transcript_text_edit.toPlainText() == "First section.\n\nSecond section."
    assert window._transcript_text == "First section.\n\nSecond section."


def test_using_a_transcript_selection_sets_the_selected_items_text(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()

    window._set_transcript_text("First section.\n\nSecond section.")

    window._item_list_widget.setCurrentRow(0)
    _select_substring(window._transcript_text_edit, "Second section.")
    assert window._match_transcript_button.isEnabled()

    window._on_use_transcript_selection_clicked()

    assert window._items[0].text == "Second section."
    assert window._item_text_edit.toPlainText() == "Second section."


def test_use_selection_button_disabled_without_item_or_text_selection(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._set_transcript_text("First section.\n\nSecond section.")

    assert not window._match_transcript_button.isEnabled()

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)

    assert not window._match_transcript_button.isEnabled()

    _select_substring(window._transcript_text_edit, "First section.")
    assert window._match_transcript_button.isEnabled()


# -- cloze selection & card template (Phase 5, multi-cloze/library in 5.5) --


def test_mark_cloze_button_disabled_without_text_selection(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("저는 학생 입니다")

    assert not window._mark_cloze_button.isEnabled()

    _select_substring(window._item_text_edit, "학생")

    assert window._mark_cloze_button.isEnabled()


def test_marking_a_selection_sets_cloze_span_korean(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("저는 학생 입니다")
    _select_substring(window._item_text_edit, "학생")

    window._on_mark_cloze_clicked()

    item = window._items[0]
    assert item.has_cloze
    span = item.valid_cloze_spans()[0]
    assert item.text[span.start : span.end] == "학생"


def test_marking_a_selection_sets_cloze_span_japanese(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("これはサンプルです")
    _select_substring(window._item_text_edit, "サンプル")

    window._on_mark_cloze_clicked()

    item = window._items[0]
    assert item.has_cloze
    span = item.valid_cloze_spans()[0]
    assert item.text[span.start : span.end] == "サンプル"


def test_marking_a_second_selection_adds_a_second_cloze(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("one two three")
    _select_substring(window._item_text_edit, "one")
    window._on_mark_cloze_clicked()
    _select_substring(window._item_text_edit, "three")
    window._on_mark_cloze_clicked()

    item = window._items[0]
    spans = item.valid_cloze_spans()
    assert len(spans) == 2
    assert item.text[spans[0].start : spans[0].end] == "one"
    assert item.text[spans[1].start : spans[1].end] == "three"


def test_mark_cloze_disabled_for_a_selection_overlapping_an_existing_cloze(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("hello world")
    _select_substring(window._item_text_edit, "hello world")
    window._on_mark_cloze_clicked()

    _select_substring(window._item_text_edit, "world")
    assert not window._mark_cloze_button.isEnabled()


def test_removing_one_cloze_span_keeps_the_others(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("one two three")
    _select_substring(window._item_text_edit, "one")
    window._on_mark_cloze_clicked()
    _select_substring(window._item_text_edit, "three")
    window._on_mark_cloze_clicked()

    first_span = window._items[0].valid_cloze_spans()[0]
    window._on_remove_cloze_span(0, first_span)

    remaining = window._items[0].valid_cloze_spans()
    assert len(remaining) == 1
    assert window._items[0].text[remaining[0].start : remaining[0].end] == "three"


def test_editing_text_after_marking_cloze_clears_it(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("hello world")
    _select_substring(window._item_text_edit, "world")
    window._on_mark_cloze_clicked()
    assert window._items[0].has_cloze

    window._item_text_edit.setPlainText("hello world, edited")

    assert not window._items[0].has_cloze


def test_selecting_different_item_loads_its_own_cloze_state(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("hello world")
    _select_substring(window._item_text_edit, "world")
    window._on_mark_cloze_clicked()

    window._waveform._waveform.set_selection(3.0, 4.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("second item")

    assert window._cloze_list_layout.count() == 0

    window._item_list_widget.setCurrentRow(0)

    assert window._cloze_list_layout.count() == 1


def test_state_badge_reflects_text_and_cloze_progress(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()

    def badge_text() -> str:
        return window._item_list_widget.cellWidget(0, STATE_COLUMN).findChild(QLabel).text()

    assert badge_text() == "Not drafted"

    window._item_text_edit.setPlainText("hello world")
    assert badge_text() == "No cloze"

    _select_substring(window._item_text_edit, "world")
    window._on_mark_cloze_clicked()
    assert badge_text() == "Ready"


def test_row_text_preview_shows_original_text_not_blanked(qtbot, wav_file):
    # The deck row shows the item's text as typed/matched, not a
    # cloze-blanked rendering — the Cloze status badge already conveys
    # cloze progress (see test_state_badge_reflects_text_and_cloze_progress).
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("저는 학생 입니다")
    _select_substring(window._item_text_edit, "학생")
    window._on_mark_cloze_clicked()

    assert window._item_list_widget.item(0, TEXT_COLUMN).text() == "저는 학생 입니다"


def test_card_preview_reflects_selected_item_and_cloze(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("これはサンプルです")
    _select_substring(window._item_text_edit, "サンプル")
    window._on_mark_cloze_clicked()

    assert window._preview_front_label.text() == "これは[...]です"
    assert "サンプル" in window._preview_back_label.text()
    assert not window._multi_cloze_hint_label.isVisible()


def test_card_preview_shows_only_the_first_cloze_with_multiple_marked(qtbot, wav_file):
    # Real Anki generates a separate card per distinct cloze number, not
    # one card with every blank filled in — the preview should reflect
    # only card 1 (c1), with the other cloze(s) shown revealed, not
    # blanked, since they belong to other cards.
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("one two three")
    _select_substring(window._item_text_edit, "one")
    window._on_mark_cloze_clicked()
    _select_substring(window._item_text_edit, "three")
    window._on_mark_cloze_clicked()

    assert window._preview_front_label.text() == "[...] two three"
    assert window._preview_back_label.text().startswith("one two three")
    assert window._multi_cloze_hint_label.isVisible()
    assert "2 cards" in window._multi_cloze_hint_label.text()
    assert "card 1" in window._multi_cloze_hint_label.text()


def test_card_preview_clears_when_no_item_selected(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("hello")

    window._item_list_widget.setCurrentRow(-1)

    assert window._preview_front_label.text() == ""
    assert window._preview_back_label.text() == ""
    assert not window._multi_cloze_hint_label.isVisible()


def test_card_preview_lives_in_its_own_panel_separate_from_the_editor(qtbot, wav_file):
    # The preview used to be a section inside the item editor's own body;
    # it now lives in a dedicated panel to its own right so editing and
    # reading-the-result-back aren't competing for the same scrollable
    # column.
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    editor_panel = window._item_text_edit
    while editor_panel is not None and editor_panel.objectName() != "editorPanel":
        editor_panel = editor_panel.parentWidget()
    preview_panel = window._preview_front_label
    while preview_panel is not None and preview_panel.objectName() != "previewPanel":
        preview_panel = preview_panel.parentWidget()

    assert editor_panel is not None
    assert preview_panel is not None
    assert editor_panel is not preview_panel
    assert not window._preview_front_label.isAncestorOf(window._item_text_edit)
    assert not window._item_text_edit.isAncestorOf(window._preview_front_label)


def test_note_template_dialog_updates_window_template_live(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("hello world")
    _select_substring(window._item_text_edit, "world")
    window._on_mark_cloze_clicked()

    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    dialog = NoteTemplateDialog(
        window._template,
        window._field_values_for_item(window._items[0]),
        window._template_library_path,
        window,
    )
    qtbot.addWidget(dialog)
    dialog.template_changed.connect(window._on_template_changed)

    dialog._back_edit.setPlainText("{{cloze:Text}} :: extra")

    assert window._template.back_template == "{{cloze:Text}} :: extra"
    assert "extra" in window._preview_back_label.text()


def test_template_dialog_library_list_does_not_overlap_its_button_row(qtbot, tmp_path):
    # Regression: the dialog used to be resized before its layout existed,
    # leaving the splitter's left panel undersized once the layout
    # actually activated — the "Saved Templates" list and the New/Load/
    # Save/Delete row ended up occupying overlapping vertical space.
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    dialog = NoteTemplateDialog(NoteTemplate(), {"Text": "hi"}, tmp_path / "templates.json")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    list_bottom = dialog._library_list.geometry().bottom()
    buttons_top = dialog._load_button.geometry().top()
    assert list_bottom < buttons_top


def test_note_template_dialog_add_and_rename_field(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    template = NoteTemplate()
    dialog = NoteTemplateDialog(
        template, {"Text": "hi", "Audio": "[a]"}, tmp_path / "templates.json"
    )
    qtbot.addWidget(dialog)

    captured = []
    dialog.template_changed.connect(captured.append)

    dialog._on_add_field()

    assert captured[-1].fields == ["Text", "Audio", "Field"]

    item = dialog._field_list.item(2)
    item.setText("Notes")

    assert captured[-1].fields == ["Text", "Audio", "Notes"]


def test_new_field_gets_an_editable_sample_data_input(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    dialog = NoteTemplateDialog(
        NoteTemplate(), {"Text": "hi", "Audio": "[a]"}, tmp_path / "templates.json"
    )
    qtbot.addWidget(dialog)

    dialog._on_add_field()
    dialog._field_list.item(2).setText("Definition")

    field_input = _sample_data_input(dialog, "Definition")
    assert field_input.text() == ""
    assert "definition" in field_input.placeholderText().lower()


def test_typing_sample_data_updates_the_live_preview(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    dialog = NoteTemplateDialog(
        NoteTemplate(), {"Text": "hi", "Audio": "[a]"}, tmp_path / "templates.json"
    )
    qtbot.addWidget(dialog)
    dialog._on_add_field()
    dialog._field_list.item(2).setText("Definition")
    dialog._back_edit.setPlainText("{{cloze:Text}}<br>{{Definition}}")

    dialog._on_sample_value_edited("Definition", "a formal way of saying hello")

    assert "a formal way of saying hello" in dialog._preview_back.text()


def test_sample_data_input_prefills_from_passed_in_preview_values(qtbot, tmp_path):
    # When an item is selected in the main window, its real Text/Audio
    # values flow in as preview_field_values — the sample-data inputs
    # should start seeded with those, not blank.
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    dialog = NoteTemplateDialog(
        NoteTemplate(), {"Text": "저는 학생 입니다", "Audio": "🔊 0:01–0:02"}, tmp_path / "templates.json"
    )
    qtbot.addWidget(dialog)

    assert _sample_data_input(dialog, "Text").text() == "저는 학생 입니다"
    assert _sample_data_input(dialog, "Audio").text() == "🔊 0:01–0:02"


def test_sample_data_values_persist_across_unrelated_field_changes(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    dialog = NoteTemplateDialog(
        NoteTemplate(), {"Text": "hi", "Audio": "[a]"}, tmp_path / "templates.json"
    )
    qtbot.addWidget(dialog)
    dialog._on_add_field()
    dialog._field_list.item(2).setText("Definition")
    dialog._on_sample_value_edited("Definition", "a formal way of saying hello")

    # Adding another field rebuilds every sample-data row — the existing
    # one's typed value must survive that rebuild.
    dialog._on_add_field()

    assert _sample_data_input(dialog, "Definition").text() == "a formal way of saying hello"


def test_removing_a_field_removes_its_sample_data_input(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    dialog = NoteTemplateDialog(
        NoteTemplate(), {"Text": "hi", "Audio": "[a]"}, tmp_path / "templates.json"
    )
    qtbot.addWidget(dialog)
    dialog._on_add_field()
    dialog._field_list.item(2).setText("Definition")

    dialog._field_list.setCurrentRow(2)
    dialog._on_remove_field()

    with pytest.raises(AssertionError):
        _sample_data_input(dialog, "Definition")


# -- per-item data for custom fields -----------------------------------------


def _add_custom_field(qtbot, window, field_name: str) -> None:
    """Test helper: add a field to the active template the same way a user
    would — through the modal Note Template dialog — since the item
    editor's "Additional Fields" section only appears once a field has
    actually gone through that flow (this also exercises the same
    dialog-then-close timing the app hits in real use)."""
    from PySide6.QtCore import QTimer

    def add_and_close():
        from flashcard_generator.ui.template_dialog import NoteTemplateDialog

        dialog = next(iter(window.findChildren(NoteTemplateDialog)), None)
        assert dialog is not None
        dialog._on_add_field()
        dialog._field_list.item(dialog._field_list.count() - 1).setText(field_name)
        dialog.accept()

    QTimer.singleShot(0, add_and_close)
    window._open_template_dialog()
    qtbot.wait(50)


def test_new_field_shows_as_editable_box_in_item_editor(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)

    assert not window._extra_fields_section.isVisible()

    _add_custom_field(qtbot, window, "Definition")

    assert window._extra_fields_section.isVisible()
    assert "Definition" in window._extra_field_edits


def test_typing_in_extra_field_saves_to_the_item(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    _add_custom_field(qtbot, window, "Definition")

    window._extra_field_edits["Definition"].setPlainText("a formal way of saying hello")

    assert window._items[0].extra_fields == {"Definition": "a formal way of saying hello"}


def test_extra_field_content_flows_into_card_preview(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    window._item_text_edit.setPlainText("hello")
    _add_custom_field(qtbot, window, "Definition")
    window._template.back_template = "{{cloze:Text}}<br>{{Definition}}"

    window._extra_field_edits["Definition"].setPlainText("a formal way of saying hello")

    assert "a formal way of saying hello" in window._preview_back_label.text()


def test_selecting_different_item_loads_its_own_extra_field_values(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    _add_custom_field(qtbot, window, "Definition")
    window._extra_field_edits["Definition"].setPlainText("first item's definition")

    window._waveform._waveform.set_selection(3.0, 4.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(1)

    assert window._extra_field_edits["Definition"].toPlainText() == ""

    window._extra_field_edits["Definition"].setPlainText("second item's definition")
    window._item_list_widget.setCurrentRow(0)

    assert window._extra_field_edits["Definition"].toPlainText() == "first item's definition"
    assert window._items[0].extra_fields == {"Definition": "first item's definition"}
    assert window._items[1].extra_fields == {"Definition": "second item's definition"}


def test_removing_the_field_hides_the_additional_fields_section(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    _add_custom_field(qtbot, window, "Definition")
    assert window._extra_fields_section.isVisible()

    window._template.fields = ["Text", "Audio"]
    window._rebuild_extra_field_inputs()

    assert not window._extra_fields_section.isVisible()
    assert window._extra_field_edits == {}


def test_editing_item_text_preserves_extra_fields(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    _add_custom_field(qtbot, window, "Definition")
    window._extra_field_edits["Definition"].setPlainText("a formal way of saying hello")

    window._item_text_edit.setPlainText("edited text")

    assert window._items[0].extra_fields == {"Definition": "a formal way of saying hello"}


def test_marking_cloze_preserves_extra_fields(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    window._item_text_edit.setPlainText("hello world")
    _add_custom_field(qtbot, window, "Definition")
    window._extra_field_edits["Definition"].setPlainText("a formal way of saying hello")

    _select_substring(window._item_text_edit, "world")
    window._on_mark_cloze_clicked()

    assert window._items[0].extra_fields == {"Definition": "a formal way of saying hello"}


def test_extra_fields_survive_session_restore(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    _add_custom_field(qtbot, window, "Definition")
    window._extra_field_edits["Definition"].setPlainText("a formal way of saying hello")

    restored = MainWindow()
    qtbot.addWidget(restored)
    qtbot.waitUntil(lambda: restored._duration_ms > 0, timeout=3000)

    assert restored._items[0].extra_fields == {"Definition": "a formal way of saying hello"}


def test_additional_fields_section_geometry_settles_after_dialog_closes(qtbot, wav_file):
    # A field added while the Note Template dialog is open takes a few
    # layout passes to reach its full size (more than usual — modifying
    # a hidden-then-shown widget's layout from inside a modal dialog's
    # event loop needs extra recompute passes than the same change made
    # outside one) — settles within milliseconds under real event
    # processing, per qtbot.wait below, but confirm it actually does.
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    window.resize(1280, 950)
    qtbot.addWidget(window)
    window.show()
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_list_widget.setCurrentRow(0)
    _add_custom_field(qtbot, window, "Definition")
    qtbot.wait(100)

    height = window._extra_field_edits["Definition"].parentWidget().geometry().height()
    assert height >= 70


# -- saved-template library (Phase 5.5) --------------------------------------


def test_saving_a_template_persists_it_to_the_library(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog
    from flashcard_generator.template_library import load_template_library

    library_path = tmp_path / "templates.json"
    template = NoteTemplate(name="My Preset", fields=["Text", "Audio"])
    dialog = NoteTemplateDialog(template, {"Text": "hi"}, library_path)
    qtbot.addWidget(dialog)

    dialog._on_save_template_clicked()

    saved = load_template_library(library_path)
    assert [t.name for t in saved] == ["My Preset"]


def test_load_and_delete_enabled_immediately_after_saving_first_template(qtbot, tmp_path):
    # Regression: _reload_library_list() rebuilds the list with signals
    # blocked (so its own setCurrentRow doesn't recurse), which meant
    # Load/Delete's enabled state — normally kept in sync by
    # currentRowChanged — went stale: the newly saved entry showed
    # selected (highlighted) but Load/Delete stayed disabled.
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog

    library_path = tmp_path / "templates.json"
    dialog = NoteTemplateDialog(NoteTemplate(name="Default"), {"Text": "hi"}, library_path)
    qtbot.addWidget(dialog)

    dialog._on_save_template_clicked()

    assert dialog._library_list.currentRow() == 0
    assert dialog._load_button.isEnabled()
    assert dialog._delete_button.isEnabled()


def test_saving_again_with_same_name_overwrites_the_entry(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog
    from flashcard_generator.template_library import load_template_library

    library_path = tmp_path / "templates.json"
    template = NoteTemplate(name="My Preset", fields=["Text", "Audio"])
    dialog = NoteTemplateDialog(template, {"Text": "hi"}, library_path)
    qtbot.addWidget(dialog)
    dialog._on_save_template_clicked()

    dialog._back_edit.setPlainText("{{cloze:Text}} updated")
    dialog._on_save_template_clicked()

    saved = load_template_library(library_path)
    assert len(saved) == 1
    assert saved[0].back_template == "{{cloze:Text}} updated"


def test_loading_a_saved_template_replaces_the_editor_contents(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog
    from flashcard_generator.template_library import save_template_library

    library_path = tmp_path / "templates.json"
    save_template_library(
        library_path,
        [NoteTemplate(name="Saved One", fields=["Text", "Audio", "Notes"])],
    )

    dialog = NoteTemplateDialog(NoteTemplate(), {"Text": "hi"}, library_path)
    qtbot.addWidget(dialog)
    dialog._library_list.setCurrentRow(0)

    dialog._on_load_template_clicked()

    assert dialog._template.name == "Saved One"
    assert dialog._template.fields == ["Text", "Audio", "Notes"]
    assert dialog._name_edit.text() == "Saved One"
    assert [dialog._field_list.item(i).text() for i in range(dialog._field_list.count())] == [
        "Text",
        "Audio",
        "Notes",
    ]


def test_deleting_a_saved_template_removes_it_from_the_library(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog
    from flashcard_generator.template_library import load_template_library, save_template_library

    library_path = tmp_path / "templates.json"
    save_template_library(library_path, [NoteTemplate(name="Saved One")])

    dialog = NoteTemplateDialog(NoteTemplate(), {"Text": "hi"}, library_path)
    qtbot.addWidget(dialog)
    dialog._library_list.setCurrentRow(0)

    dialog._on_delete_template_clicked()

    assert load_template_library(library_path) == []
    assert dialog._library_list.count() == 0


def test_new_template_resets_editor_without_touching_the_library(qtbot, tmp_path):
    from flashcard_generator.ui.template_dialog import NoteTemplateDialog
    from flashcard_generator.template_library import save_template_library

    library_path = tmp_path / "templates.json"
    save_template_library(library_path, [NoteTemplate(name="Saved One")])

    dialog = NoteTemplateDialog(
        NoteTemplate(name="Saved One"), {"Text": "hi"}, library_path
    )
    qtbot.addWidget(dialog)

    dialog._on_new_template_clicked()

    assert dialog._template.name == "New Template"
    assert dialog._template.fields == NoteTemplate().fields
    assert dialog._library_list.count() == 1  # library itself untouched


def test_note_template_survives_session_restore(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._template = NoteTemplate(
        fields=["Text", "Audio", "Notes"],
        front_template="{{cloze:Text}}",
        back_template="{{cloze:Text}}<br>{{Notes}}",
    )
    window._save_session()

    restored = MainWindow()
    qtbot.addWidget(restored)
    qtbot.waitUntil(lambda: restored._duration_ms > 0, timeout=3000)

    assert restored._template.fields == ["Text", "Audio", "Notes"]
    assert restored._template.back_template == "{{cloze:Text}}<br>{{Notes}}"


def test_cloze_span_survives_session_restore(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._item_text_edit.setPlainText("hello world")
    _select_substring(window._item_text_edit, "world")
    window._on_mark_cloze_clicked()

    restored = MainWindow()
    qtbot.addWidget(restored)
    qtbot.waitUntil(lambda: restored._duration_ms > 0, timeout=3000)

    assert restored._items[0].has_cloze
    span = restored._items[0].valid_cloze_spans()[0]
    assert restored._items[0].text[span.start : span.end] == "world"


def test_transcript_text_survives_session_restore(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._set_transcript_text("Only section.")
    window._save_session()

    restored = MainWindow()
    qtbot.addWidget(restored)
    restored.show()
    qtbot.waitUntil(lambda: restored._duration_ms > 0, timeout=3000)

    assert restored._transcript_text == "Only section."
    assert restored._transcript_text_edit.toPlainText() == "Only section."
    assert restored._transcript_panel.isVisible()


# -- export (Phase 6) ---------------------------------------------------------


def test_deck_name_field_disabled_with_no_audio_loaded(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window._deck_name_edit.isEnabled()


def test_deck_name_defaults_to_audio_filename_stem_on_import(qtbot, wav_file):
    from pathlib import Path

    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    assert window._deck_name == Path(path).stem
    assert window._deck_name_edit.text() == Path(path).stem
    assert window._deck_name_edit.isEnabled()


def test_editing_toolbar_deck_name_persists_and_survives_restore(qtbot, wav_file, session_path):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._on_deck_name_edited("My Existing Deck")
    assert window._deck_name == "My Existing Deck"

    restored = MainWindow()
    qtbot.addWidget(restored)
    qtbot.waitUntil(lambda: restored._duration_ms > 0, timeout=3000)

    assert restored._deck_name == "My Existing Deck"
    assert restored._deck_name_edit.text() == "My Existing Deck"


def test_export_action_disabled_with_no_items(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    assert not window._export_action.isEnabled()


def test_export_action_enables_once_an_item_exists(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()

    assert window._export_action.isEnabled()


def test_export_action_disables_again_once_last_item_removed(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()
    window._on_remove_item_clicked()

    assert not window._export_action.isEnabled()


def test_open_export_dialog_passes_current_items_template_and_audio(qtbot, wav_file, monkeypatch):
    from flashcard_generator.ui import main_window as main_window_module

    path = wav_file(duration_seconds=10.0)
    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_item_clicked()

    captured = {}

    class FakeDialog:
        def __init__(self, items, template, audio_path, deck_name, parent):
            captured["items"] = items
            captured["template"] = template
            captured["audio_path"] = audio_path
            captured["deck_name"] = deck_name

        def exec(self):
            captured["exec_called"] = True

    monkeypatch.setattr(main_window_module, "ExportDialog", FakeDialog)

    window._open_export_dialog()

    assert captured["items"] is window._items
    assert captured["template"] is window._template
    assert captured["audio_path"] == window._audio_path
    assert captured["deck_name"] == window._deck_name
    assert captured["exec_called"] is True
