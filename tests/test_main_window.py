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
