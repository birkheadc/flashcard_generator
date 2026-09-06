from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..export import ExportBlockedError, export_apkg, find_export_issues
from ..items import ItemList
from ..template import NoteTemplate
from . import theme
from .format_time import format_time
from .icons import icon


class ExportDialog(QDialog):
    """Export flow per DESIGN.md §9: deck name, output path, a summary of
    any items missing required data (blocking export by default, per
    `export.export_apkg`'s `ExportBlockedError`), and a confirm step that
    produces the `.apkg` and offers to reveal it in the file manager.

    A single dialog, since export is a terminal action with no ongoing
    state — closing it after a successful export leaves nothing to undo or
    resume. The deck name itself is *not* owned by this dialog — it's a
    persistent, in-app setting (`MainWindow._deck_name_edit`, autosaved in
    `session.py`) edited from the main toolbar, since this dialog is modal
    and would otherwise block editing it right when the user needs to
    check/change it before exporting. This dialog only displays the
    current value for confirmation.
    """

    def __init__(
        self,
        items: ItemList,
        template: NoteTemplate,
        audio_path: str,
        deck_name: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export to Anki")
        self.setMinimumWidth(480)
        self._items = items
        self._template = template
        self._audio_path = audio_path
        self._deck_name = deck_name
        self._issues = find_export_issues(items)
        self._output_path: str | None = None

        self._layout = QVBoxLayout(self)
        self._build_form()

    # -- form state ---------------------------------------------------------

    def _build_form(self) -> None:
        name_label = QLabel("Anki Deck", self)
        name_label.setObjectName("sectionLabel")
        self._layout.addWidget(name_label)
        deck_name_value = QLabel(self._deck_name or "(none set)", self)
        self._layout.addWidget(deck_name_value)
        deck_name_hint = QLabel(
            "Set from the toolbar's \"Anki Deck Name\" field — must exactly "
            "match an existing Anki deck's name to import into it, "
            "otherwise Anki creates a new deck with this name.",
            self,
        )
        deck_name_hint.setObjectName("hintLabel")
        deck_name_hint.setWordWrap(True)
        self._layout.addWidget(deck_name_hint)

        path_label = QLabel("Output File")
        path_label.setObjectName("sectionLabel")
        self._layout.addWidget(path_label)
        path_row = QHBoxLayout()
        self._output_path_edit = QLineEdit(self)
        self._output_path_edit.setReadOnly(True)
        self._output_path_edit.setPlaceholderText("Choose where to save the .apkg…")
        path_row.addWidget(self._output_path_edit, 1)
        browse_button = QPushButton("Browse…", self)
        browse_button.clicked.connect(self._on_browse_clicked)
        path_row.addWidget(browse_button)
        self._layout.addLayout(path_row)

        summary_label = QLabel("Summary")
        summary_label.setObjectName("sectionLabel")
        self._layout.addWidget(summary_label)
        count = len(self._items)
        plural = "" if count == 1 else "s"
        ready = count - len(self._issues)
        self._summary_label = QLabel(
            f"{count} item{plural} — {ready} ready to export.", self
        )
        self._summary_label.setWordWrap(True)
        self._layout.addWidget(self._summary_label)

        self._skip_checkbox: QCheckBox | None = None
        if self._issues:
            issues_text = "\n".join(
                f"• {format_time(self._items[issue.item_index].clip.start_seconds)}"
                f"–{format_time(self._items[issue.item_index].clip.end_seconds)}: {issue.reason}"
                for issue in self._issues
            )
            issues_label = QLabel(issues_text, self)
            issues_label.setObjectName("hintLabel")
            issues_label.setWordWrap(True)
            self._layout.addWidget(issues_label)

            self._skip_checkbox = QCheckBox(
                f"Export anyway, skipping {len(self._issues)} incomplete item"
                f"{'' if len(self._issues) == 1 else 's'}",
                self,
            )
            self._skip_checkbox.toggled.connect(self._update_export_button_enabled)
            self._layout.addWidget(self._skip_checkbox)

        footer = QHBoxLayout()
        footer.addStretch()
        cancel_button = QPushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        self._export_button = QPushButton("Export", self)
        self._export_button.setObjectName("primaryButton")
        self._export_button.setIcon(icon("mdi6.export-variant", color=theme.PAPER_0))
        self._export_button.clicked.connect(self._on_export_clicked)
        footer.addWidget(self._export_button)
        self._layout.addLayout(footer)

        self._update_export_button_enabled()

    def _skip_incomplete(self) -> bool:
        return self._skip_checkbox is not None and self._skip_checkbox.isChecked()

    def _update_export_button_enabled(self) -> None:
        can_export = (
            bool(self._deck_name.strip())
            and self._output_path is not None
            and (not self._issues or self._skip_incomplete())
        )
        self._export_button.setEnabled(can_export)

    def _on_browse_clicked(self) -> None:
        deck_name = self._deck_name.strip() or "deck"
        default_dir = Path.home() / "Downloads"
        if not default_dir.is_dir():
            default_dir = Path.home()
        suggested = str(default_dir / f"{deck_name}.apkg")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to .apkg", suggested, "Anki Deck (*.apkg)"
        )
        if not path:
            return
        if not path.lower().endswith(".apkg"):
            path += ".apkg"
        self._output_path = path
        self._output_path_edit.setText(path)
        self._update_export_button_enabled()

    # -- export ---------------------------------------------------------

    def _on_export_clicked(self) -> None:
        if self._output_path is None:
            return
        try:
            export_apkg(
                self._items,
                self._template,
                self._audio_path,
                self._deck_name.strip(),
                self._output_path,
                skip_incomplete=self._skip_incomplete(),
            )
        except ExportBlockedError as exc:
            QMessageBox.warning(
                self,
                "Cannot export",
                f"{len(exc.issues)} item(s) are missing text or a cloze — "
                "check \"export anyway\" to skip them, or fix them first.",
            )
            return
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return

        self._show_success()

    def _show_success(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            layout = item.layout()
            if layout is not None:
                _clear_layout(layout)

        self._layout.addWidget(QLabel(f"Exported to:\n{self._output_path}", self))

        footer = QHBoxLayout()
        footer.addStretch()
        reveal_button = QPushButton("Reveal in File Manager", self)
        reveal_button.clicked.connect(self._on_reveal_clicked)
        footer.addWidget(reveal_button)
        close_button = QPushButton("Close", self)
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        self._layout.addLayout(footer)

    def _on_reveal_clicked(self) -> None:
        if self._output_path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._output_path).parent)))


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        child_layout = item.layout()
        if child_layout is not None:
            _clear_layout(child_layout)
