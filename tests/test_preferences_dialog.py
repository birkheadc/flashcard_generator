from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from flashcard_generator.ui.preferences_dialog import PreferencesDialog


def test_reset_all_confirmed_signal_fires_when_confirmed(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.reset_all_confirmed.connect(lambda: fired.append(True))

    dialog._on_reset_all_clicked()

    assert fired == [True]


def test_reset_all_confirmed_signal_does_not_fire_when_declined(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.reset_all_confirmed.connect(lambda: fired.append(True))

    dialog._on_reset_all_clicked()

    assert fired == []
