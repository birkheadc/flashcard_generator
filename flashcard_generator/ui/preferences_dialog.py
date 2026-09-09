from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import icon


class PreferencesDialog(QDialog):
    """The toolbar's "Preferences" action (previously a disabled stub) —
    currently just "Reset All", for wiping local app state during
    development/debugging without hunting down
    ~/.flashcard_generator/*.json by hand. More settings land here as real
    ones exist; no reason to build empty sections ahead of that.
    """

    reset_all_confirmed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(380)
        self.setMinimumHeight(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        label = QLabel("Reset All", self)
        label.setObjectName("sectionLabel")
        layout.addWidget(label)

        hint = QLabel(
            "Deletes the saved session and note-template library, then "
            "restarts the app — useful for debugging/development, or to "
            "start over from a clean slate.",
            self,
        )
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        layout.addWidget(hint)

        reset_button = QPushButton("Reset All", self)
        reset_button.setIcon(icon("mdi6.restore", color=theme.ACTION_DANGER))
        reset_button.setObjectName("dangerButton")
        reset_button.clicked.connect(self._on_reset_all_clicked)
        layout.addWidget(reset_button)

        layout.addStretch(1)

        # A fixed top margin on the footer itself (rather than trusting the
        # stretch above to always resolve to some non-zero gap) so Close
        # can't end up visually crowding/overlapping the Reset All button
        # above it regardless of platform/style/DPI quirks in how much
        # space that stretch actually ends up getting.
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 12, 0, 0)
        footer.addStretch()
        close_button = QPushButton("Close", self)
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def _on_reset_all_clicked(self) -> None:
        # A second, explicit confirmation on top of the button's own label —
        # this is permanent and there's no undo, unlike almost everything
        # else in the app (DESIGN.md §1's "nothing is precious" posture
        # assumes reversibility, which deleting these files breaks).
        choice = QMessageBox.warning(
            self,
            "Reset everything?",
            "This permanently deletes the saved session and note-template "
            "library, and restarts the app. This cannot be undone.\n\n"
            "Continue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        self.reset_all_confirmed.emit()
