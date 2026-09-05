from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..audio.waveform import AudioTooLongError, compute_waveform
from ..clips import Clip
from ..items import Item, ItemList
from ..session import default_session_path, load_session, save_session
from ..transcript import normalize_transcript
from . import theme
from .format_time import format_time, format_time_ago
from .icons import icon
from .waveform_view import WaveformView

SUPPORTED_EXTENSIONS = ["wav", "flac", "ogg", "mp3", "aiff"]
AUDIO_FILE_FILTER = (
    "Audio files (" + " ".join(f"*.{ext}" for ext in SUPPORTED_EXTENSIONS) + ");;All files (*)"
)

NOT_YET_IMPLEMENTED = "Not yet implemented — see ROADMAP.md"

# Clip table columns and their fixed widths (Sentence is the one column that
# stretches). Widths are fixed rather than content-driven, per the mockup's
# own column layout (Bootstrapper.dc.html's header row: Range 112px, State
# 96px), so an item flipping between "Drafted"/"Not drafted" doesn't reflow
# the whole table. The Actions column (play + delete) isn't in the mockup
# and is sized to fit both icon buttons.
RANGE_COLUMN = 0
TEXT_COLUMN = 1
STATE_COLUMN = 2
ACTIONS_COLUMN = 3

RANGE_COLUMN_WIDTH = 132
STATE_COLUMN_WIDTH = 118
ACTIONS_COLUMN_WIDTH = 76

# Fixed size of each icon-only button in the Actions column, and the row
# height that comfortably fits them without clipping into the row below.
ROW_ICON_BUTTON_SIZE = 26
ROW_HEIGHT = 40


def _lock_toggle_button_width(button: QPushButton, *texts: str) -> None:
    """Fix a button's width to fit the widest of its possible labels, so a
    button that changes text when clicked (Play/Pause and the like) doesn't
    change size as it toggles."""
    metrics = button.fontMetrics()
    # Comfortably covers the QSS's own horizontal padding/border, plus the
    # icon and its spacing before the text, so text never brushes the edge
    # in either state.
    padding = 32 + (24 if not button.icon().isNull() else 0)
    button.setFixedWidth(max(metrics.horizontalAdvance(t) for t in texts) + padding)


class ItemTextEdit(QPlainTextEdit):
    """QPlainTextEdit that hides its placeholder during IME composition.

    Qt only hides placeholder text once the document actually contains
    text, but an in-progress IME composition (e.g. romaji not yet
    converted/committed to kana/kanji) doesn't touch the document — so
    without this, the placeholder and the uncommitted composition text
    render on top of each other for that first word.
    """

    def __init__(self, placeholder: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._placeholder = placeholder
        self.setPlaceholderText(placeholder)

    def inputMethodEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        super().inputMethodEvent(event)
        self.setPlaceholderText("" if event.preeditString() else self._placeholder)


class ItemTableWidget(QTableWidget):
    """The clip deck: one row per item, columns Range/Sentence/State/Actions.

    Delete/Backspace is bound to discarding the selected item, per
    DESIGN.md §12's keyboard model. Also adds a couple of QListWidget-style
    convenience methods (setCurrentRow) so call sites elsewhere don't need
    to know this is backed by QTableWidget rather than QTableView cells.
    """

    delete_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(0, 4, parent)
        # No header text for the Actions column — it's just a row of icon
        # buttons, a label would only add noise.
        self.setHorizontalHeaderLabels(
            [theme.section_label_text(t) for t in ("Range", "Sentence", "State", "")]
        )
        self.verticalHeader().setVisible(False)
        # Rows default to a height driven by the text font, which is too
        # short to fit the Actions column's icon buttons without clipping
        # into the row below — so every row gets a fixed, taller height.
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)

        # Fixed widths (not ResizeToContents) so a row's column layout can't
        # shift depending on its own content — e.g. "Drafted" vs. "Not
        # drafted" being different widths must not reflow every other row.
        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(RANGE_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TEXT_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(STATE_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(ACTIONS_COLUMN, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(RANGE_COLUMN, RANGE_COLUMN_WIDTH)
        self.setColumnWidth(STATE_COLUMN, STATE_COLUMN_WIDTH)
        self.setColumnWidth(ACTIONS_COLUMN, ACTIONS_COLUMN_WIDTH)

    def setCurrentRow(self, row: int) -> None:
        self.setCurrentCell(row, RANGE_COLUMN)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, session_path: Path | None = None):
        super().__init__()
        self.setWindowTitle("Flashcard Generator")
        self.resize(1280, 760)
        theme.ensure_fonts_loaded()
        self.setStyleSheet(theme.STYLESHEET)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._duration_ms = 0
        self._items = ItemList()
        self._transcript_text = ""
        self._audio_path: str | None = None
        self._session_path = session_path if session_path is not None else default_session_path()
        self._pending_selection: tuple[float, float] | None = None
        self._loop_range: tuple[float, float] | None = None
        self._loop_source: str | None = None  # "item" | "selection" | None
        self._loop_item_index: int | None = None
        self._loading_item_text = False
        self._last_autosave_time: datetime | None = None

        self._build_ui()
        self._build_toolbar()
        self._restore_session()

        self._autosave_label_timer = QTimer(self)
        self._autosave_label_timer.setInterval(15_000)
        self._autosave_label_timer.timeout.connect(self._update_autosave_label)
        self._autosave_label_timer.start()

    # -- layout construction ------------------------------------------------

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(theme.section_label_text(text), self)
        label.setObjectName("sectionLabel")
        return label

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("centralWidget")
        central_layout = QVBoxLayout(central)
        # The mockup runs its panels edge-to-edge, but a real resizable
        # desktop window reads better with breathing room around the
        # content and between panels, so this deliberately departs from it.
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(0)

        main_splitter = QSplitter(Qt.Orientation.Vertical, central)
        main_splitter.setHandleWidth(10)

        top_splitter = QSplitter(Qt.Orientation.Horizontal, main_splitter)
        top_splitter.setHandleWidth(10)
        top_splitter.addWidget(self._build_waveform_panel())
        top_splitter.addWidget(self._build_transcript_panel())
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 1)
        main_splitter.addWidget(top_splitter)

        deck_splitter = QSplitter(Qt.Orientation.Horizontal, main_splitter)
        deck_splitter.setHandleWidth(10)
        deck_splitter.addWidget(self._build_items_panel())
        deck_splitter.addWidget(self._build_editor_panel())
        deck_splitter.setStretchFactor(0, 2)
        deck_splitter.setStretchFactor(1, 1)
        main_splitter.addWidget(deck_splitter)

        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 2)

        central_layout.addWidget(main_splitter)
        self.setCentralWidget(central)

        self._build_status_bar()

    def _build_waveform_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("waveformPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(panel)
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)
        header_layout.addWidget(self._section_label("Waveform"))
        header_layout.addStretch()
        layout.addWidget(header)

        self._waveform = WaveformView(panel)
        self._waveform.seek_requested.connect(self._seek_to_seconds)
        self._waveform.selection_changed.connect(self._on_selection_changed)
        self._waveform.clip_region_edited.connect(self._on_item_region_edited)
        layout.addWidget(self._waveform, 1)

        hint = QLabel(
            "Shift+drag to select a region · drag a region's edge to resize it", panel
        )
        hint.setObjectName("hintLabel")
        hint.setContentsMargins(12, 2, 12, 2)
        layout.addWidget(hint)

        transport = QFrame(panel)
        transport.setObjectName("panelFooter")
        transport_layout = QHBoxLayout(transport)
        transport_layout.setContentsMargins(12, 6, 12, 6)

        self._play_button = QPushButton("Play")
        self._play_button.setIcon(icon("mdi6.play"))
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._toggle_playback)
        _lock_toggle_button_width(self._play_button, "Play", "Pause")
        transport_layout.addWidget(self._play_button)

        self._play_selection_button = QPushButton("Play Selection (Loop)")
        self._play_selection_button.setIcon(icon("mdi6.repeat-variant"))
        self._play_selection_button.setEnabled(False)
        self._play_selection_button.clicked.connect(self._on_play_selection_clicked)
        _lock_toggle_button_width(self._play_selection_button, "Play Selection (Loop)", "Stop")
        transport_layout.addWidget(self._play_selection_button)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setObjectName("clockLabel")
        transport_layout.addWidget(self._time_label)

        transport_layout.addSpacing(8)

        split_at_playhead_button = QPushButton("Split at Playhead")
        split_at_playhead_button.setIcon(icon("mdi6.call-split"))
        split_at_playhead_button.setEnabled(False)
        split_at_playhead_button.setToolTip(NOT_YET_IMPLEMENTED)
        transport_layout.addWidget(split_at_playhead_button)

        self._add_item_button = QPushButton("Clip from Selection")
        self._add_item_button.setIcon(icon("mdi6.content-cut"))
        self._add_item_button.setEnabled(False)
        self._add_item_button.setToolTip("Select a region on the waveform (Shift+drag) first")
        self._add_item_button.clicked.connect(self._on_add_item_clicked)
        transport_layout.addWidget(self._add_item_button)

        transport_layout.addStretch()
        transport_layout.addWidget(self._waveform.zoom_bar)
        layout.addWidget(transport)

        return panel

    def _build_transcript_panel(self) -> QWidget:
        # Hidden until a transcript is imported (§5 of DESIGN.md: an empty
        # pane would read as broken rather than optional), so the no-
        # transcript flow from earlier phases keeps its full waveform width.
        panel = QWidget(self)
        panel.setObjectName("transcriptPanel")
        panel.setVisible(False)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(panel)
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)
        header_layout.addWidget(self._section_label("Transcript"))
        header_layout.addStretch()
        layout.addWidget(header)

        # Read-only, but text-selectable: the raw transcript is shown as-is
        # (no automatic splitting — that only makes sense once forced
        # alignment (Phase 9) exists to do it against known audio timing).
        # The user highlights whatever span they want, like in any text
        # editor, and "Use Selection as Text" below copies it onto the
        # currently selected item.
        self._transcript_text_edit = QPlainTextEdit(panel)
        self._transcript_text_edit.setReadOnly(True)
        self._transcript_text_edit.selectionChanged.connect(self._update_match_button_enabled)
        layout.addWidget(self._transcript_text_edit, 1)

        footer = QFrame(panel)
        footer.setObjectName("panelFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        self._match_transcript_button = QPushButton("Use Selection as Text")
        self._match_transcript_button.setIcon(icon("mdi6.link-variant"))
        self._match_transcript_button.setEnabled(False)
        self._match_transcript_button.clicked.connect(self._on_use_transcript_selection_clicked)
        footer_layout.addWidget(self._match_transcript_button)
        footer_layout.addStretch()
        layout.addWidget(footer)

        self._transcript_panel = panel
        return panel

    def _build_items_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("itemsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(panel)
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)
        header_layout.addWidget(self._section_label("Clips"))
        self._items_count_label = QLabel("0 items")
        self._items_count_label.setObjectName("metaLabel")
        header_layout.addWidget(self._items_count_label)
        header_layout.addStretch()
        key_hint = QLabel("↑↓ select · ⌫ discard")
        key_hint.setObjectName("metaLabel")
        header_layout.addWidget(key_hint)
        layout.addWidget(header)

        self._item_list_widget = ItemTableWidget(panel)
        self._item_list_widget.currentCellChanged.connect(
            lambda row, _col, _prow, _pcol: self._on_current_item_changed(row)
        )
        self._item_list_widget.delete_requested.connect(self._on_remove_item_clicked)
        layout.addWidget(self._item_list_widget, 1)

        footer = QFrame(panel)
        footer.setObjectName("panelFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 4, 12, 4)
        self._items_ready_label = QLabel("")
        self._items_ready_label.setObjectName("metaLabel")
        footer_layout.addWidget(self._items_ready_label)
        footer_layout.addStretch()
        layout.addWidget(footer)

        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("editorPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(panel)
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 8, 6)
        title = QLabel("Item")
        title.setStyleSheet(f"font-weight: 600; color: {theme.TEXT_TITLE};")
        header_layout.addWidget(title)
        self._selected_range_label = QLabel("")
        self._selected_range_label.setObjectName("metaLabel")
        header_layout.addWidget(self._selected_range_label)
        header_layout.addStretch()
        layout.addWidget(header)

        body = QWidget(panel)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 14, 14, 14)
        body_layout.setSpacing(10)

        body_layout.addWidget(self._section_label("Item Text"))
        self._item_text_edit = ItemTextEdit(
            "Type the phrase text for the selected item…", body
        )
        self._item_text_edit.setEnabled(False)
        self._item_text_edit.setFixedHeight(96)
        self._item_text_edit.textChanged.connect(self._on_item_text_changed)
        body_layout.addWidget(self._item_text_edit)

        body_layout.addWidget(self._section_label("Audio"))
        audio_row = QHBoxLayout()
        self._preview_button = QPushButton("Loop Preview")
        self._preview_button.setIcon(icon("mdi6.repeat-variant"))
        self._preview_button.clicked.connect(self._on_preview_clicked)
        _lock_toggle_button_width(self._preview_button, "Loop Preview", "Stop Preview")
        audio_row.addWidget(self._preview_button)
        audio_row.addStretch()
        body_layout.addLayout(audio_row)

        body_layout.addWidget(self._section_label("Reorder"))
        reorder_row = QHBoxLayout()
        self._move_up_button = QPushButton("Move Up")
        self._move_up_button.setIcon(icon("mdi6.chevron-up"))
        self._move_up_button.clicked.connect(self._on_move_item_up)
        reorder_row.addWidget(self._move_up_button)
        self._move_down_button = QPushButton("Move Down")
        self._move_down_button.setIcon(icon("mdi6.chevron-down"))
        self._move_down_button.clicked.connect(self._on_move_item_down)
        reorder_row.addWidget(self._move_down_button)
        body_layout.addLayout(reorder_row)

        body_layout.addStretch(1)
        layout.addWidget(body, 1)

        footer = QFrame(panel)
        footer.setObjectName("panelFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        footer_layout.addStretch()
        self._remove_item_button = QPushButton("Discard Clip")
        self._remove_item_button.setIcon(icon("mdi6.trash-can-outline", color=theme.ACTION_DANGER))
        self._remove_item_button.setObjectName("dangerButton")
        self._remove_item_button.clicked.connect(self._on_remove_item_clicked)
        footer_layout.addWidget(self._remove_item_button)
        layout.addWidget(footer)

        self._update_item_buttons_enabled()
        return panel

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        bar.setObjectName("mainStatusBar")
        self._status_items_label = QLabel("0 items")
        self._status_items_label.setContentsMargins(12, 0, 0, 0)
        bar.addWidget(self._status_items_label)
        self._status_autosave_label = QLabel("")
        self._status_autosave_label.setContentsMargins(0, 0, 12, 0)
        bar.addPermanentWidget(self._status_autosave_label)
        self.setStatusBar(bar)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        import_action = QAction(icon("mdi6.folder-open-outline", color=theme.PAPER_0), "Import Audio", self)
        import_action.setShortcut("Ctrl+O")
        import_action.triggered.connect(self._import_file)
        toolbar.addAction(import_action)
        toolbar.widgetForAction(import_action).setObjectName("primaryToolButton")

        record_action = QAction(icon("mdi6.microphone-outline"), "Record in-app", self)
        record_action.setEnabled(False)
        record_action.setToolTip("Not yet implemented")
        toolbar.addAction(record_action)

        toolbar.addSeparator()

        self._import_transcript_action = QAction(
            icon("mdi6.file-document-outline"), "Import Transcript", self
        )
        self._import_transcript_action.setEnabled(False)
        self._import_transcript_action.setToolTip("Import an audio file first")
        self._import_transcript_action.triggered.connect(self._import_transcript)
        toolbar.addAction(self._import_transcript_action)

        for text, icon_name in (
            ("Suggest Clips", "mdi6.auto-fix"),
            ("Align Transcript", "mdi6.sync"),
        ):
            stub_action = QAction(icon(icon_name), text, self)
            stub_action.setEnabled(False)
            stub_action.setToolTip(NOT_YET_IMPLEMENTED)
            toolbar.addAction(stub_action)

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        for text, icon_name in (
            ("Note Template", "mdi6.card-text-outline"),
            ("Export", "mdi6.export-variant"),
        ):
            stub_action = QAction(icon(icon_name), text, self)
            stub_action.setEnabled(False)
            stub_action.setToolTip(NOT_YET_IMPLEMENTED)
            toolbar.addAction(stub_action)

        toolbar.addSeparator()

        preferences_action = QAction(icon("mdi6.cog-outline"), "Preferences", self)
        preferences_action.setEnabled(False)
        preferences_action.setToolTip(NOT_YET_IMPLEMENTED)
        toolbar.addAction(preferences_action)

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import audio file", "", AUDIO_FILE_FILTER)
        if not path:
            return
        self._load_audio_file(path)

    def _load_audio_file(
        self,
        path: str,
        initial_items: list[Item] | None = None,
        initial_transcript_text: str = "",
    ) -> None:
        if len(self._items) > 0 and not self._confirm_discard_items():
            return

        try:
            waveform_data = compute_waveform(path)
        except AudioTooLongError as exc:
            if not self._confirm_long_audio(exc):
                return
            try:
                waveform_data = compute_waveform(path, allow_long=True)
            except Exception as exc2:  # noqa: BLE001 - surfaced to the user, not crashed on
                self._show_load_error(exc2)
                return
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not crashed on
            self._show_load_error(exc)
            return

        self._player.stop()
        self._stop_loop()
        self._items.clear()
        for item in initial_items or []:
            self._items.add(item)
        self._refresh_item_list_widget()
        self._set_transcript_text(initial_transcript_text)
        self._waveform.set_waveform(waveform_data)
        self._update_item_regions()
        self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self._play_button.setEnabled(True)
        self._import_transcript_action.setEnabled(True)
        self._import_transcript_action.setToolTip("")
        self.setWindowTitle(f"Flashcard Generator — {Path(path).name}")

        self._audio_path = str(Path(path).resolve())
        self._save_session()

    def _restore_session(self) -> None:
        data = load_session(self._session_path)
        if data is None:
            return
        self._load_audio_file(
            data.audio_path, initial_items=data.items, initial_transcript_text=data.transcript_text
        )

    def _save_session(self) -> None:
        if self._audio_path is None:
            return
        save_session(self._session_path, self._audio_path, self._items, self._transcript_text)
        self._last_autosave_time = datetime.now()
        self._update_autosave_label()

    def _import_transcript(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import transcript", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            raw_text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Failed to load transcript", str(exc))
            return
        self._set_transcript_text(normalize_transcript(raw_text))
        self._save_session()

    def _set_transcript_text(self, text: str) -> None:
        self._transcript_text = text
        self._transcript_text_edit.setPlainText(text)
        self._transcript_panel.setVisible(bool(text))

    def _update_autosave_label(self) -> None:
        if self._last_autosave_time is None:
            return
        elapsed = (datetime.now() - self._last_autosave_time).total_seconds()
        self._status_autosave_label.setText(f"Autosaved {format_time_ago(elapsed)}")

    def _confirm_discard_items(self) -> bool:
        count = len(self._items)
        plural = "" if count == 1 else "s"
        choice = QMessageBox.warning(
            self,
            "Discard items?",
            f"Loading a new file will discard the {count} item{plural} you've "
            "created for the current file.\n\nContinue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    def _confirm_long_audio(self, exc: AudioTooLongError) -> bool:
        choice = QMessageBox.warning(
            self,
            "Long audio file",
            f"{exc}\n\nLonger files aren't officially supported yet and the app "
            "may behave unpredictably (slow loading, high memory use, sluggish "
            "waveform interaction).\n\nContinue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    def _show_load_error(self, exc: Exception) -> None:
        supported = ", ".join(ext.upper() for ext in SUPPORTED_EXTENSIONS)
        QMessageBox.critical(
            self,
            "Failed to load audio",
            f"{exc}\n\nSupported file types: {supported}.",
        )

    def _toggle_playback(self) -> None:
        was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self._stop_loop()
        if was_playing:
            self._player.pause()
        else:
            self._player.play()

    def _seek_to_seconds(self, seconds: float) -> None:
        self._stop_loop()
        self._player.setPosition(int(seconds * 1000))

    def _on_position_changed(self, position_ms: int) -> None:
        if self._loop_range is not None and position_ms >= self._loop_range[1] * 1000:
            self._player.setPosition(int(self._loop_range[0] * 1000))
        self._waveform.set_position(position_ms / 1000)
        self._update_time_label(position_ms)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_ms = duration_ms
        self._waveform.set_duration(duration_ms / 1000)
        self._update_time_label(self._player.position())

    def _update_time_label(self, position_ms: int) -> None:
        self._time_label.setText(
            f"{format_time(position_ms / 1000)} / {format_time(self._duration_ms / 1000)}"
        )

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_button.setText("Pause")
            self._play_button.setIcon(icon("mdi6.pause"))
        else:
            self._play_button.setText("Play")
            self._play_button.setIcon(icon("mdi6.play"))

    def _on_player_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            QMessageBox.critical(self, "Playback error", error_string)

    # -- items ------------------------------------------------------------

    def _on_selection_changed(self, selection: tuple[float, float] | None) -> None:
        self._pending_selection = selection
        self._add_item_button.setEnabled(selection is not None)
        self._play_selection_button.setEnabled(selection is not None)
        if self._loop_source == "selection":
            if selection is None:
                self._stop_loop()
            else:
                self._loop_range = selection

    def _on_add_item_clicked(self) -> None:
        if self._pending_selection is None:
            return
        start, end = self._pending_selection
        self._items.add(Item(clip=Clip(start_seconds=start, end_seconds=end)))
        self._waveform.clear_selection()
        self._refresh_item_list_widget(select_index=len(self._items) - 1)
        self._update_item_regions()
        self._save_session()

    def _on_remove_item_clicked(self) -> None:
        index = self._item_list_widget.currentRow()
        if index < 0:
            return
        if self._loop_source == "item":
            self._stop_loop()
        self._items.remove(index)
        self._refresh_item_list_widget()
        self._update_item_regions()
        self._save_session()

    def _on_move_item_up(self) -> None:
        index = self._item_list_widget.currentRow()
        if index <= 0:
            return
        if self._loop_source == "item":
            self._stop_loop()
        self._items.move(index, index - 1)
        self._refresh_item_list_widget(select_index=index - 1)
        self._update_item_regions()
        self._save_session()

    def _on_move_item_down(self) -> None:
        index = self._item_list_widget.currentRow()
        if index < 0 or index >= len(self._items) - 1:
            return
        if self._loop_source == "item":
            self._stop_loop()
        self._items.move(index, index + 1)
        self._refresh_item_list_widget(select_index=index + 1)
        self._update_item_regions()
        self._save_session()

    def _on_item_region_edited(self, index: int, start: float, end: float) -> None:
        old = self._items[index]
        new_clip = Clip(start_seconds=start, end_seconds=end)
        self._items.replace(index, Item(clip=new_clip, text=old.text))
        if self._loop_source == "item" and self._loop_item_index == index:
            self._loop_range = (start, end)
        self._refresh_item_list_widget()
        self._update_item_regions()
        self._save_session()

    def _on_current_item_changed(self, index: int) -> None:
        self._update_item_buttons_enabled()
        self._update_match_button_enabled()
        self._loading_item_text = True
        try:
            self._item_text_edit.setPlainText(self._items[index].text if index >= 0 else "")
        finally:
            self._loading_item_text = False
        self._item_text_edit.setEnabled(index >= 0)
        if index >= 0:
            clip = self._items[index].clip
            self._selected_range_label.setText(
                f"{format_time(clip.start_seconds)}–{format_time(clip.end_seconds)}"
            )
        else:
            self._selected_range_label.setText("")

    def _on_item_text_changed(self) -> None:
        if self._loading_item_text:
            return
        index = self._item_list_widget.currentRow()
        if index < 0:
            return
        old = self._items[index]
        self._items.replace(
            index, Item(clip=old.clip, text=self._item_text_edit.toPlainText())
        )
        # Refresh just this row in place, rather than a full table rebuild,
        # so the text edit's cursor position isn't disturbed mid-keystroke.
        self._populate_row(index, self._items[index])
        self._update_items_meta()
        self._save_session()

    def _on_preview_clicked(self) -> None:
        index = self._item_list_widget.currentRow()
        if index < 0:
            return
        if self._loop_source == "item" and self._loop_item_index == index:
            self._stop_loop()
            return
        item = self._items[index]
        self._loop_item_index = index
        self._start_loop((item.clip.start_seconds, item.clip.end_seconds), source="item")

    def _on_play_selection_clicked(self) -> None:
        if self._loop_source == "selection":
            self._stop_loop()
            return
        selection = self._waveform.selection
        if selection is None:
            return
        self._start_loop(selection, source="selection")

    def _start_loop(self, loop_range: tuple[float, float], source: str) -> None:
        self._loop_range = loop_range
        self._loop_source = source
        self._player.setPosition(int(loop_range[0] * 1000))
        self._player.play()
        self._preview_button.setText("Stop Preview" if source == "item" else "Loop Preview")
        self._preview_button.setIcon(icon("mdi6.stop" if source == "item" else "mdi6.repeat-variant"))
        self._play_selection_button.setText(
            "Stop" if source == "selection" else "Play Selection (Loop)"
        )
        self._play_selection_button.setIcon(
            icon("mdi6.stop" if source == "selection" else "mdi6.repeat-variant")
        )

    def _stop_loop(self) -> None:
        if self._loop_source is None:
            return
        self._loop_range = None
        self._loop_source = None
        self._loop_item_index = None
        self._player.pause()
        self._preview_button.setText("Loop Preview")
        self._preview_button.setIcon(icon("mdi6.repeat-variant"))
        self._play_selection_button.setText("Play Selection (Loop)")
        self._play_selection_button.setIcon(icon("mdi6.repeat-variant"))

    def _refresh_item_list_widget(self, select_index: int | None = None) -> None:
        if select_index is None:
            select_index = self._item_list_widget.currentRow()
        self._item_list_widget.setRowCount(len(self._items))
        for i, item in enumerate(self._items):
            self._populate_row(i, item)
        if 0 <= select_index < len(self._items):
            self._item_list_widget.setCurrentRow(select_index)
        self._update_item_buttons_enabled()
        self._update_items_meta()

    def _populate_row(self, row: int, item: Item) -> None:
        clip = item.clip
        range_text = (
            f"{format_time(clip.start_seconds)}–{format_time(clip.end_seconds)} "
            f"({format_time(clip.duration_seconds)})"
        )
        preview = item.text.strip().splitlines()[0] if item.text.strip() else "(no text)"
        if len(preview) > 60:
            preview = preview[:60] + "…"
        ready = bool(item.text.strip())

        range_item = QTableWidgetItem(range_text)
        range_item.setFlags(range_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._item_list_widget.setItem(row, RANGE_COLUMN, range_item)

        text_item = QTableWidgetItem(preview)
        text_item.setFlags(text_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if not ready:
            text_item.setForeground(QColor(theme.TEXT_DISABLED))
        self._item_list_widget.setItem(row, TEXT_COLUMN, text_item)

        self._item_list_widget.setCellWidget(row, STATE_COLUMN, self._make_state_badge(ready))

        self._item_list_widget.setCellWidget(row, ACTIONS_COLUMN, self._make_row_actions(row))

    def _make_state_badge(self, ready: bool) -> QWidget:
        badge = QLabel("Drafted" if ready else "Not drafted")
        badge.setObjectName("stateBadge")
        badge.setProperty("tone", "good" if ready else "hard")

        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(6, 0, 6, 0)
        container_layout.addWidget(badge)
        container_layout.addStretch()
        return container

    def _make_row_actions(self, row: int) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addStretch()

        play_button = QPushButton()
        play_button.setIcon(icon("mdi6.play", color=theme.ACTION_PRIMARY))
        play_button.setObjectName("rowIconButton")
        play_button.setToolTip("Loop-play this clip")
        play_button.setFixedSize(ROW_ICON_BUTTON_SIZE, ROW_ICON_BUTTON_SIZE)
        play_button.clicked.connect(lambda _checked=False, r=row: self._on_row_play_clicked(r))
        layout.addWidget(play_button)

        delete_button = QPushButton()
        delete_button.setIcon(icon("mdi6.trash-can-outline", color=theme.ACTION_DANGER))
        delete_button.setObjectName("rowIconButton")
        delete_button.setToolTip("Discard this clip")
        delete_button.setFixedSize(ROW_ICON_BUTTON_SIZE, ROW_ICON_BUTTON_SIZE)
        delete_button.clicked.connect(lambda _checked=False, r=row: self._on_row_delete_clicked(r))
        layout.addWidget(delete_button)

        layout.addStretch()
        return container

    def _on_row_play_clicked(self, row: int) -> None:
        self._item_list_widget.setCurrentRow(row)
        self._on_preview_clicked()

    def _on_row_delete_clicked(self, row: int) -> None:
        self._item_list_widget.setCurrentRow(row)
        self._on_remove_item_clicked()

    def _update_item_buttons_enabled(self) -> None:
        index = self._item_list_widget.currentRow()
        has_selection = index >= 0
        self._remove_item_button.setEnabled(has_selection)
        self._preview_button.setEnabled(has_selection)
        self._move_up_button.setEnabled(has_selection and index > 0)
        self._move_down_button.setEnabled(has_selection and index < len(self._items) - 1)

    def _update_items_meta(self) -> None:
        count = len(self._items)
        drafted = sum(1 for item in self._items if item.text.strip())
        not_drafted = count - drafted
        label = "1 item" if count == 1 else f"{count} items"
        self._items_count_label.setText(label)
        self._items_ready_label.setText(
            f"{drafted} drafted · {not_drafted} not drafted" if count else ""
        )
        self._status_items_label.setText(label)

    def _update_item_regions(self) -> None:
        self._waveform.set_clip_regions(self._items.regions())

    # -- transcript (Phase 4) -----------------------------------------------

    def _update_match_button_enabled(self) -> None:
        has_item = self._item_list_widget.currentRow() >= 0
        has_selection = self._transcript_text_edit.textCursor().hasSelection()
        self._match_transcript_button.setEnabled(has_item and has_selection)

    def _on_use_transcript_selection_clicked(self) -> None:
        item_index = self._item_list_widget.currentRow()
        cursor = self._transcript_text_edit.textCursor()
        if item_index < 0 or not cursor.hasSelection():
            return
        # A selection spanning multiple paragraphs comes back with U+2029
        # paragraph separators rather than '\n'.
        selected_text = cursor.selectedText().replace(" ", "\n")
        old = self._items[item_index]
        self._items.replace(item_index, Item(clip=old.clip, text=selected_text))
        self._populate_row(item_index, self._items[item_index])
        self._update_items_meta()
        if self._item_list_widget.currentRow() == item_index:
            self._loading_item_text = True
            try:
                self._item_text_edit.setPlainText(self._items[item_index].text)
            finally:
                self._loading_item_text = False
        self._save_session()
