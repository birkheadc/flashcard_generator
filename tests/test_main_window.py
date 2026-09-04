from __future__ import annotations

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox

from flashcard_generator.ui.main_window import MainWindow


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


def test_selection_enables_add_clip_button(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    assert not window._add_clip_button.isEnabled()

    window._waveform._waveform.set_selection(1.0, 3.0)
    assert window._add_clip_button.isEnabled()

    window._waveform.clear_selection()
    assert not window._add_clip_button.isEnabled()


def test_add_clip_appends_to_list_and_clears_selection(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 3.0)
    window._on_add_clip_clicked()

    assert len(window._clips) == 1
    assert window._clips[0].start_seconds == pytest.approx(1.0)
    assert window._clips[0].end_seconds == pytest.approx(3.0)
    assert window._clip_list_widget.count() == 1
    assert window._waveform.selection is None
    assert not window._add_clip_button.isEnabled()


def test_remove_clip_deletes_selected_row(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 3.0)
    window._on_add_clip_clicked()
    window._waveform._waveform.set_selection(4.0, 6.0)
    window._on_add_clip_clicked()

    window._clip_list_widget.setCurrentRow(0)
    window._on_remove_clip_clicked()

    assert len(window._clips) == 1
    assert window._clips[0].start_seconds == pytest.approx(4.0)


def test_move_clip_up_and_down_reorders(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_clip_clicked()
    window._waveform._waveform.set_selection(3.0, 4.0)
    window._on_add_clip_clicked()

    window._clip_list_widget.setCurrentRow(1)
    window._on_move_clip_up()

    assert [c.start_seconds for c in window._clips] == [3.0, 1.0]
    assert window._clip_list_widget.currentRow() == 0

    window._on_move_clip_down()

    assert [c.start_seconds for c in window._clips] == [1.0, 3.0]
    assert window._clip_list_widget.currentRow() == 1


def test_loop_preview_seeks_back_to_clip_start_past_end(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_clip_clicked()
    window._clip_list_widget.setCurrentRow(0)

    window._on_preview_clicked()
    assert window._preview_button.text() == "Stop Preview"
    qtbot.waitUntil(lambda: window._player.position() > 0, timeout=3000)

    window._on_position_changed(2500)  # past the clip's 2.0s end

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


def test_dragging_clip_edge_on_waveform_updates_the_clip(qtbot, wav_file):
    path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 3.0)
    window._on_add_clip_clicked()

    window._on_clip_region_edited(0, 1.0, 5.0)

    assert window._clips[0].start_seconds == pytest.approx(1.0)
    assert window._clips[0].end_seconds == pytest.approx(5.0)
    assert window._clip_list_widget.item(0).text().startswith("1. 0:01–0:05")


def test_loading_new_file_clears_clips_if_confirmed(qtbot, wav_file, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    first_path = wav_file(duration_seconds=10.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window._load_audio_file(first_path)
    qtbot.waitUntil(lambda: window._duration_ms > 0, timeout=3000)

    window._waveform._waveform.set_selection(1.0, 2.0)
    window._on_add_clip_clicked()
    assert len(window._clips) == 1

    second_path = wav_file(duration_seconds=5.0)
    window._load_audio_file(second_path)

    assert len(window._clips) == 0
    assert window._clip_list_widget.count() == 0


def test_loading_new_file_with_clips_warns_and_aborts_if_declined(qtbot, wav_file, monkeypatch):
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
    window._on_add_clip_clicked()
    original_title = window.windowTitle()

    second_path = wav_file(duration_seconds=5.0)
    window._load_audio_file(second_path)

    assert len(warnings) == 1
    assert "discard" in warnings[0][1].lower()
    assert len(window._clips) == 1
    assert window.windowTitle() == original_title


def test_loading_new_file_without_clips_does_not_warn(qtbot, wav_file, monkeypatch):
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
