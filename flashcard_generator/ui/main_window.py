from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..audio.playback_engine import PlaybackEngine
from ..audio.waveform import AudioTooLongError, compute_waveform
from ..clips import Clip
from ..export import ExportBlockedError, default_deck_name, export_apkg
from ..items import PROVENANCE_MANUAL, PROVENANCE_VAD, ClozeSpan, Item, ItemList
from ..session import default_session_path, load_session, save_session
from ..template import NoteTemplate, cloze_index_count, cloze_wrapped_text, render_card
from ..template_library import default_template_library_path
from ..transcript import normalize_transcript
from . import theme
from .format_time import format_time, format_time_ago
from .export_dialog import ExportDialog
from .icons import icon
from .preferences_dialog import PreferencesDialog
from .template_dialog import NoteTemplateDialog
from .waveform_view import WaveformView

SUPPORTED_EXTENSIONS = ["wav", "flac", "ogg", "mp3", "aiff"]
AUDIO_FILE_FILTER = (
    "Audio files (" + " ".join(f"*.{ext}" for ext in SUPPORTED_EXTENSIONS) + ");;All files (*)"
)

NOT_YET_IMPLEMENTED = "Not yet implemented — see ROADMAP.md"

# Shown in the window title so "which build is this" is answerable at a
# glance after an upgrade, without opening an About dialog that doesn't
# exist yet — __version__ is this app's one source of truth, also read by
# packaging/build_windows.ps1 when stamping the installer's own version.
APP_TITLE = f"Flashcard Generator v{__version__}"

# Clip table columns and their fixed widths (Sentence is the one column that
# stretches). Widths are fixed rather than content-driven, per the mockup's
# own column layout (Bootstrapper.dc.html's header row: Range 112px, State
# 96px), so an item flipping between "Drafted"/"Not drafted" doesn't reflow
# the whole table. The Actions column (play + delete) isn't in the mockup
# and is sized to fit both icon buttons. Keep (a checkbox, not in the mockup
# either) is the bulk-review affordance for "Suggest Clips dumped in a pile
# of candidates, check off the ones worth keeping, discard the rest".
CHECK_COLUMN = 0
RANGE_COLUMN = 1
TEXT_COLUMN = 2
STATE_COLUMN = 3
ACTIONS_COLUMN = 4

CHECK_COLUMN_WIDTH = 36
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

    def set_cloze_highlights(self, spans: list[ClozeSpan]) -> None:
        """Highlight the marked cloze spans (ROADMAP.md Phase 5, extended
        to multiple spans in Phase 5.5), or clear all highlights if given
        none. Purely a rendering overlay (QTextEdit.ExtraSelection) —
        doesn't touch the actual edit cursor or selection, so it's safe to
        call on every keystroke."""
        if not spans:
            self.setExtraSelections([])
            return
        text_length = len(self.toPlainText())
        selections = []
        for span in spans:
            cursor = self.textCursor()
            cursor.setPosition(min(span.start, text_length))
            cursor.setPosition(min(span.end, text_length), QTextCursor.MoveMode.KeepAnchor)
            char_format = QTextCharFormat()
            char_format.setBackground(QColor(theme.CYPRUS_100))
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = char_format
            selections.append(selection)
        self.setExtraSelections(selections)


class ItemTableWidget(QTableWidget):
    """The clip deck: one row per item, columns Keep/Range/Sentence/State/Actions.

    Delete/Backspace is bound to discarding the selected item, per
    DESIGN.md §12's keyboard model. Also adds a couple of QListWidget-style
    convenience methods (setCurrentRow) so call sites elsewhere don't need
    to know this is backed by QTableWidget rather than QTableView cells.
    """

    delete_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(0, 5, parent)
        # No header text for Keep (a checkbox, self-explanatory once seen)
        # or Actions (just a row of icon buttons) — a label would only add
        # noise to either.
        self.setHorizontalHeaderLabels(
            [theme.section_label_text(t) for t in ("", "Range", "Sentence", "State", "")]
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
        header.setSectionResizeMode(CHECK_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(RANGE_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TEXT_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(STATE_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(ACTIONS_COLUMN, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(CHECK_COLUMN, CHECK_COLUMN_WIDTH)
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
    # _run_with_busy_dialog timing — see its docstring for why both exist.
    _START_DELAY_MS = 60
    _MIN_VISIBLE_MS = 400

    # Real values are measured at the end of _build_toolbar; class-level
    # (not set in __init__) so they're already 0 for any resizeEvent Qt
    # dispatches before then — as early as the self.resize() call below,
    # well before self._toolbar exists — rather than an AttributeError.
    _toolbar_text_width = 0
    _toolbar_icon_only_width = 0

    def __init__(self, session_path: Path | None = None):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 760)
        theme.ensure_fonts_loaded()
        self.setStyleSheet(theme.STYLESHEET)

        self._engine = PlaybackEngine(self)
        self._engine.positionChanged.connect(self._on_engine_position_changed)
        self._engine.durationChanged.connect(self._on_engine_duration_changed)
        self._engine.playingChanged.connect(self._on_engine_playing_changed)
        self._engine.errorOccurred.connect(self._on_engine_error)

        self._duration_ms = 0
        self._items = ItemList()
        self._transcript_text = ""
        self._template = NoteTemplate()
        self._template_library_path = default_template_library_path()
        self._audio_path: str | None = None
        self._deck_name = ""
        self._last_export_path: str | None = None
        self._session_path = session_path if session_path is not None else default_session_path()
        self._pending_selection: tuple[float, float] | None = None
        self._loop_range: tuple[float, float] | None = None
        self._loop_source: str | None = None  # "item" | "selection" | "row" | None
        self._loop_item_index: int | None = None
        # Whether reaching the end of _loop_range seeks back to its start
        # (the item editor's "Loop Preview"/"Play Selection (Loop)") or just
        # stops (the clip deck's row Play, a single listen-through while
        # scanning many rows rather than a repeated editing loop).
        self._loop_repeats = True
        # Which items (by id(), pruned in _refresh_item_list_widget whenever
        # an item is no longer in the list) currently have their Keep box
        # checked, for the "Discard Unchecked" bulk-review action.
        self._checked_item_ids: set[int] = set()
        self._loading_item_text = False
        self._loading_extra_fields = False
        self._loading_transcript_text = False
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

        central_layout.addWidget(self._build_deck_name_bar())
        central_layout.addSpacing(10)

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
        # Built (not yet added — that happens in left-to-right order below)
        # ahead of the editor panel: the editor panel's construction ends
        # by refreshing the card preview, which needs the preview labels
        # this panel owns to already exist.
        preview_panel = self._build_preview_panel()
        deck_splitter.addWidget(self._build_items_panel())
        deck_splitter.addWidget(self._build_editor_panel())
        deck_splitter.addWidget(preview_panel)
        deck_splitter.setStretchFactor(0, 2)
        deck_splitter.setStretchFactor(1, 2)
        deck_splitter.setStretchFactor(2, 2)
        main_splitter.addWidget(deck_splitter)

        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 2)

        central_layout.addWidget(main_splitter)
        self.setCentralWidget(central)

        self._build_status_bar()

    def _build_deck_name_bar(self) -> QWidget:
        # Its own full-width row rather than a cramped stacked label+input
        # squeezed into the toolbar (where it used to live, fighting a
        # dozen icon buttons for space and a fixed 180px cap on the input):
        # the deck name is what every export actually writes into, so it
        # gets real, dedicated space and a normal-sized label instead of a
        # tiny uppercase one.
        bar = QFrame(self)
        bar.setObjectName("deckNameBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        icon_label = QLabel(bar)
        icon_label.setPixmap(icon("mdi6.cards-outline", color=theme.ACTION_PRIMARY).pixmap(20, 20))
        layout.addWidget(icon_label)

        label = QLabel("Anki Deck Name", bar)
        label.setObjectName("deckNameBarLabel")
        layout.addWidget(label)

        self._deck_name_edit = QLineEdit(bar)
        self._deck_name_edit.setPlaceholderText("Exact name of the Anki deck to import into")
        self._deck_name_edit.setToolTip(
            "Enter the exact name of the Anki deck you want these cards to "
            "import into. If no deck with this name exists in Anki yet, "
            "importing the export will create one."
        )
        self._deck_name_edit.setEnabled(False)
        self._deck_name_edit.textEdited.connect(self._on_deck_name_edited)
        layout.addWidget(self._deck_name_edit, 1)

        return bar

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
        hint.setWordWrap(True)
        layout.addWidget(hint)

        transport = QFrame(panel)
        transport.setObjectName("panelFooter")
        transport_layout = QHBoxLayout(transport)
        transport_layout.setContentsMargins(12, 6, 12, 6)

        # Icon-only (with a tooltip standing in for the label) rather than
        # text buttons — "Play"/"Play Selection (Loop)" were the widest
        # things in this row, wide enough to force the whole panel (and its
        # QSplitter pane) to never shrink below that width, which is exactly
        # the room the transcript pane needs when its own content grows.
        self._play_button = QPushButton()
        self._play_button.setIcon(icon("mdi6.play"))
        self._play_button.setToolTip("Play")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._toggle_playback)
        transport_layout.addWidget(self._play_button)

        self._play_selection_button = QPushButton()
        self._play_selection_button.setIcon(icon("mdi6.repeat-variant"))
        self._play_selection_button.setToolTip("Play Selection (Loop)")
        self._play_selection_button.setEnabled(False)
        self._play_selection_button.clicked.connect(self._on_play_selection_clicked)
        transport_layout.addWidget(self._play_selection_button)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setObjectName("clockLabel")
        transport_layout.addWidget(self._time_label)

        transport_layout.addSpacing(8)

        self._add_item_button = QPushButton("Clip")
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

        # Editable: the raw transcript is shown as-is (no automatic
        # splitting — that only makes sense once forced alignment (Phase 9)
        # exists to do it against known audio timing) but a transcript is
        # rarely word-perfect (ASR mistakes, formatting quirks), so the user
        # can correct it in place rather than only ever selecting from it.
        # The user highlights whatever span they want, like in any text
        # editor, and "Use Selection as Text" below copies it onto the
        # currently selected item. No border of its own — the panel already
        # has one, and stacking a second rounded border directly against it
        # just looked like a rendering glitch.
        self._transcript_text_edit = QPlainTextEdit(panel)
        self._transcript_text_edit.setObjectName("transcriptTextEdit")
        self._transcript_text_edit.selectionChanged.connect(self._update_match_button_enabled)
        self._transcript_text_edit.textChanged.connect(self._on_transcript_text_edited)
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
        self._item_list_widget.itemChanged.connect(self._on_item_check_changed)
        layout.addWidget(self._item_list_widget, 1)

        footer = QFrame(panel)
        footer.setObjectName("panelFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 4, 12, 4)
        self._items_ready_label = QLabel("")
        self._items_ready_label.setObjectName("metaLabel")
        footer_layout.addWidget(self._items_ready_label)
        footer_layout.addStretch()
        # "Save these, delete rest" for a pile of Suggest Clips candidates:
        # check the Keep box on the ones worth keeping, then discard
        # whatever's left unchecked in one action, instead of deleting
        # unwanted clips one at a time.
        self._discard_unchecked_button = QPushButton("Discard Unchecked")
        self._discard_unchecked_button.setIcon(
            icon("mdi6.trash-can-outline", color=theme.ACTION_DANGER)
        )
        self._discard_unchecked_button.setObjectName("dangerButton")
        self._discard_unchecked_button.setToolTip(
            "Check the Keep box on the clips you want, then discard everything "
            "still unchecked"
        )
        self._discard_unchecked_button.setEnabled(False)
        self._discard_unchecked_button.clicked.connect(self._on_discard_unchecked_clicked)
        footer_layout.addWidget(self._discard_unchecked_button)
        self._clear_all_button = QPushButton("Clear All")
        self._clear_all_button.setIcon(icon("mdi6.trash-can-outline", color=theme.ACTION_DANGER))
        self._clear_all_button.setObjectName("dangerButton")
        self._clear_all_button.setEnabled(False)
        self._clear_all_button.clicked.connect(self._on_clear_all_clicked)
        footer_layout.addWidget(self._clear_all_button)
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
        body.setObjectName("scrollBody")
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
        self._item_text_edit.selectionChanged.connect(self._update_cloze_buttons_enabled)
        body_layout.addWidget(self._item_text_edit)

        body_layout.addWidget(self._section_label("Cloze"))
        cloze_row = QHBoxLayout()
        self._mark_cloze_button = QPushButton("Mark as Cloze")
        self._mark_cloze_button.setIcon(icon("mdi6.text-box-edit-outline"))
        self._mark_cloze_button.setEnabled(False)
        self._mark_cloze_button.setShortcut("Ctrl+Shift+C")
        self._mark_cloze_button.setToolTip(
            "Select a span of the text above first, then mark it as a cloze "
            "(Ctrl+Shift+C). A new span becomes the next cloze (c1, c2, "
            "...) — Anki turns each into its own card."
        )
        self._mark_cloze_button.clicked.connect(self._on_mark_cloze_clicked)
        cloze_row.addWidget(self._mark_cloze_button)
        cloze_row.addStretch()
        body_layout.addLayout(cloze_row)
        self._cloze_hint_label = QLabel("Select an item to mark a cloze.")
        self._cloze_hint_label.setObjectName("hintLabel")
        self._cloze_hint_label.setWordWrap(True)
        body_layout.addWidget(self._cloze_hint_label)
        # One row per marked span (c1, c2, ...), each with its own remove
        # button — rebuilt by _refresh_cloze_ui whenever the item/spans
        # change, same pattern as the deck row's Actions column.
        self._cloze_list_container = QWidget(body)
        self._cloze_list_layout = QVBoxLayout(self._cloze_list_container)
        self._cloze_list_layout.setContentsMargins(0, 0, 0, 0)
        self._cloze_list_layout.setSpacing(2)
        body_layout.addWidget(self._cloze_list_container)

        # One editable box per note-type field beyond the cloze-text field
        # and "Audio" (e.g. a "Definition" field added in the template
        # editor) — hidden entirely when the current template has none.
        # Rebuilt by _rebuild_extra_field_inputs whenever the item
        # selection or the template's field list changes.
        self._extra_fields_section = QWidget(body)
        extra_fields_section_layout = QVBoxLayout(self._extra_fields_section)
        extra_fields_section_layout.setContentsMargins(0, 0, 0, 0)
        extra_fields_section_layout.setSpacing(10)
        extra_fields_section_layout.addWidget(self._section_label("Additional Fields"))
        self._extra_fields_container = QWidget(self._extra_fields_section)
        self._extra_fields_layout = QVBoxLayout(self._extra_fields_container)
        self._extra_fields_layout.setContentsMargins(0, 0, 0, 0)
        self._extra_fields_layout.setSpacing(10)
        extra_fields_section_layout.addWidget(self._extra_fields_container)
        body_layout.addWidget(self._extra_fields_section)
        self._extra_fields_section.setVisible(False)
        self._extra_field_edits: dict[str, ItemTextEdit] = {}

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

        combine_row = QHBoxLayout()
        self._combine_with_next_button = QPushButton("Combine with Next")
        self._combine_with_next_button.setIcon(icon("mdi6.call-merge"))
        self._combine_with_next_button.setToolTip(
            "Merge this clip and the next one into a single item — useful "
            "when Suggest Clips splits one sentence across two clips."
        )
        self._combine_with_next_button.clicked.connect(self._on_combine_with_next_clicked)
        combine_row.addWidget(self._combine_with_next_button)
        body_layout.addLayout(combine_row)

        body_layout.addStretch(1)

        # A plain QVBoxLayout has no way to shrink gracefully once its
        # content outgrows the splitter panel's allocated height (the
        # panel doesn't grow to fit; the layout instead starts squeezing
        # children, up to and including clipping/overlapping ones with a
        # hard fixed size) — and this section only grows as fields are
        # added in the template editor, so a scroll area rather than a
        # bare body widget keeps it usable regardless of window height.
        scroll_area = QScrollArea(panel)
        scroll_area.setWidget(body)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        layout.addWidget(scroll_area, 1)

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
        self._refresh_cloze_ui(-1)
        self._rebuild_extra_field_inputs()
        return panel

    def _build_preview_panel(self) -> QWidget:
        # Split out from the item editor into its own panel, deliberately
        # departing from DESIGN.md §7 (which has the preview live inside
        # the editor drawer) — editing and reading-the-result-back read as
        # distinct enough activities to earn separate screen space, rather
        # than the preview competing for room with the edit controls above
        # it and needing a scroll to reach.
        panel = QWidget(self)
        panel.setObjectName("previewPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(panel)
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)
        header_layout.addWidget(self._section_label("Card Preview"))
        header_layout.addStretch()
        layout.addWidget(header)

        body = QWidget(panel)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 14, 14, 14)
        body_layout.setSpacing(10)

        # Anki generates one card per distinct cloze number, not one card
        # with every blank filled in at once — shown only when an item
        # actually has more than one, so it doesn't clutter the common
        # single-cloze case.
        self._multi_cloze_hint_label = QLabel("", body)
        self._multi_cloze_hint_label.setObjectName("hintLabel")
        self._multi_cloze_hint_label.setWordWrap(True)
        self._multi_cloze_hint_label.setVisible(False)
        body_layout.addWidget(self._multi_cloze_hint_label)

        front_caption = QLabel("Front")
        front_caption.setObjectName("hintLabel")
        body_layout.addWidget(front_caption)
        self._preview_front_label = QLabel("", body)
        self._preview_front_label.setWordWrap(True)
        self._preview_front_label.setTextFormat(Qt.TextFormat.RichText)
        self._preview_front_label.setObjectName("cardPreviewFace")
        body_layout.addWidget(self._preview_front_label)

        back_caption = QLabel("Back")
        back_caption.setObjectName("hintLabel")
        body_layout.addWidget(back_caption)
        self._preview_back_label = QLabel("", body)
        self._preview_back_label.setWordWrap(True)
        self._preview_back_label.setTextFormat(Qt.TextFormat.RichText)
        self._preview_back_label.setObjectName("cardPreviewFace")
        body_layout.addWidget(self._preview_back_label)

        body_layout.addStretch(1)
        layout.addWidget(body, 1)

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
        self._toolbar = QToolBar("Main", self)
        self._toolbar.setObjectName("mainToolbar")
        self._toolbar.setMovable(False)
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(self._toolbar)

        import_action = QAction(icon("mdi6.folder-open-outline", color=theme.PAPER_0), "Import Audio", self)
        import_action.setShortcut("Ctrl+O")
        import_action.triggered.connect(self._import_file)
        self._toolbar.addAction(import_action)
        self._toolbar.widgetForAction(import_action).setObjectName("primaryToolButton")

        record_action = QAction(icon("mdi6.microphone-outline"), "Record in-app", self)
        record_action.setEnabled(False)
        record_action.setToolTip("Not yet implemented")
        self._toolbar.addAction(record_action)

        self._toolbar.addSeparator()

        self._import_transcript_action = QAction(
            icon("mdi6.file-document-outline"), "Import Transcript", self
        )
        self._import_transcript_action.setEnabled(False)
        self._import_transcript_action.setToolTip("Import an audio file first")
        self._import_transcript_action.triggered.connect(self._import_transcript)
        self._toolbar.addAction(self._import_transcript_action)

        self._suggest_clips_action = QAction(icon("mdi6.auto-fix"), "Suggest Clips", self)
        self._suggest_clips_action.setEnabled(False)
        self._suggest_clips_action.setToolTip("Import an audio file first")
        self._suggest_clips_action.triggered.connect(self._on_suggest_clips_clicked)
        self._toolbar.addAction(self._suggest_clips_action)

        align_action = QAction(icon("mdi6.sync"), "Align Transcript", self)
        align_action.setEnabled(False)
        align_action.setToolTip(NOT_YET_IMPLEMENTED)
        self._toolbar.addAction(align_action)

        self._toolbar.addSeparator()

        self._template_action = QAction(icon("mdi6.card-text-outline"), "Note Template", self)
        self._template_action.triggered.connect(self._open_template_dialog)
        self._toolbar.addAction(self._template_action)

        self._export_action = QAction(icon("mdi6.export-variant"), "Export", self)
        self._export_action.setShortcut("Ctrl+E")
        self._export_action.setEnabled(False)
        self._export_action.setToolTip("Add at least one item first")
        self._export_action.triggered.connect(self._open_export_dialog)
        self._toolbar.addAction(self._export_action)

        self._quick_export_action = QAction(icon("mdi6.lightning-bolt-outline"), "Quick Export", self)
        self._quick_export_action.setShortcut("Ctrl+Shift+E")
        self._quick_export_action.setEnabled(False)
        self._quick_export_action.setToolTip("Export once first to set an output file")
        self._quick_export_action.triggered.connect(self._on_quick_export_clicked)
        self._toolbar.addAction(self._quick_export_action)

        # The one deliberate expanding gap in the toolbar (everywhere else
        # is a plain separator, all the same width) — pushing Preferences
        # to the far right is a standard place for it, not just leftover
        # space nothing else claimed.
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._toolbar.addWidget(spacer)

        preferences_action = QAction(icon("mdi6.cog-outline"), "Preferences", self)
        preferences_action.triggered.connect(self._open_preferences_dialog)
        self._toolbar.addAction(preferences_action)

        # How wide the toolbar actually needs to be in each button style,
        # measured once right after building it (while nothing has yet
        # squeezed it) — resizeEvent below uses these to switch to a
        # compact icon-only style once the window gets too narrow for full
        # text labels, and to stop the window shrinking any further once
        # even icon-only buttons wouldn't all fit. Replaces relying on
        # Qt's own toolbar overflow ("»") button, which hid actions behind
        # a second, easy-to-miss row rather than shrinking predictably.
        self._toolbar_icon_only_width = self._measure_toolbar_width(
            Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self._toolbar_text_width = self._measure_toolbar_width(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.setMinimumWidth(self._toolbar_icon_only_width)
        # The full toolbar turns out to need more than the 1280px default
        # window width from __init__ — widen the initial window rather than
        # opening already-compact on an otherwise perfectly roomy monitor.
        # If the actual screen is narrower than this, the window manager
        # clamps it and resizeEvent falls back to compact mode anyway.
        if self.width() < self._toolbar_text_width:
            self.resize(self._toolbar_text_width + 40, self.height())

    def _measure_toolbar_width(self, style: Qt.ToolButtonStyle) -> int:
        # QToolBar.sizeHint() doesn't actually respond to toolButtonStyle
        # changes before the toolbar has been shown/laid out at least once
        # (confirmed by hand — it kept returning the same value across both
        # styles) — each *button's* own sizeHint does respond immediately,
        # so this sums those directly instead, plus the toolbar's own QSS
        # padding/spacing (theme.py's `padding`/`spacing` on
        # QToolBar#mainToolbar) which won't show up in any widget's sizeHint.
        self._toolbar.setToolButtonStyle(style)
        widgets = [
            self._toolbar.widgetForAction(action)
            for action in self._toolbar.actions()
        ]
        widgets = [w for w in widgets if w is not None]
        total = sum(w.sizeHint().width() for w in widgets)
        if len(widgets) > 1:
            total += theme.SPACE_4 * (len(widgets) - 1)
        return total + theme.SPACE_5 * 2

    def _update_toolbar_compactness(self) -> None:
        if not hasattr(self, "_toolbar"):
            return
        compact = self.width() < self._toolbar_text_width
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        if self._toolbar.toolButtonStyle() != style:
            self._toolbar.setToolButtonStyle(style)

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        super().resizeEvent(event)
        self._update_toolbar_compactness()

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
        initial_deck_name: str | None = None,
        initial_last_export_path: str | None = None,
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

        self._stop_loop()
        self._items.clear()
        for item in initial_items or []:
            self._items.add(item)
        self._refresh_item_list_widget()
        self._set_transcript_text(initial_transcript_text)
        self._waveform.set_waveform(waveform_data)
        self._update_item_regions()
        self._engine.load(str(Path(path).resolve()))
        self._play_button.setEnabled(True)
        self._import_transcript_action.setEnabled(True)
        self._import_transcript_action.setToolTip("")
        self._suggest_clips_action.setEnabled(True)
        self._suggest_clips_action.setToolTip("")
        self.setWindowTitle(f"{APP_TITLE} — {Path(path).name}")

        self._audio_path = str(Path(path).resolve())
        self._deck_name = (
            initial_deck_name if initial_deck_name is not None else default_deck_name(path)
        )
        self._deck_name_edit.setEnabled(True)
        self._deck_name_edit.setText(self._deck_name)
        self._last_export_path = initial_last_export_path
        self._update_quick_export_enabled()
        self._save_session()

    def _restore_session(self) -> None:
        data = load_session(self._session_path)
        if data is None:
            return
        self._template = data.template
        self._load_audio_file(
            data.audio_path,
            initial_items=data.items,
            initial_transcript_text=data.transcript_text,
            initial_deck_name=data.deck_name or default_deck_name(data.audio_path),
            initial_last_export_path=data.last_export_path or None,
        )

    def _save_session(self) -> None:
        if self._audio_path is None:
            return
        save_session(
            self._session_path,
            self._audio_path,
            self._items,
            self._transcript_text,
            self._template,
            self._deck_name,
            self._last_export_path or "",
        )
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
        except (OSError, UnicodeDecodeError) as exc:
            QMessageBox.critical(
                self,
                "Failed to load transcript",
                f"{exc}\n\nThe file must be UTF-8 text.",
            )
            return
        self._set_transcript_text(normalize_transcript(raw_text))
        self._save_session()

    def _run_with_busy_dialog(self, title: str, message: str, func, on_done) -> None:
        """Show a modal, indeterminate progress popup, then run blocking
        `func()` and hand its result (or raised exception) to
        `on_done(result, exc)` — for long actions (Suggest Clips is the
        first of these) where a wait cursor alone leaves the user with no
        indication anything is happening.

        Confirmed by hand on a real desktop session that a dialog shown
        right before a blocking call can still flash and vanish too fast to
        ever be perceived, even once `func` itself is deferred to let the
        event loop paint it first: a fast-enough operation (e.g. `torch`
        already warm from a prior Suggest Clips click, or just a fast
        machine) can still finish inside the window between "compositor got
        a paint request" and "compositor actually flips a frame." So two
        delays, not one: `_START_DELAY_MS` before starting `func` at all
        (time for the window manager to actually paint the just-shown
        dialog), and `_MIN_VISIBLE_MS` the dialog is guaranteed to stay up
        for afterward, regardless of how fast `func` finishes — so it can't
        disappear before a human has had a chance to see it.
        Not cancellable: nothing on the other end (yet) runs on a
        background thread to actually interrupt.
        """
        dialog = QProgressDialog(message, "", 0, 0, self)
        dialog.setWindowTitle(title)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setCancelButton(None)
        dialog.setMinimumDuration(0)
        dialog.show()
        shown_at = time.monotonic()

        def _finish(result, exc) -> None:
            QApplication.restoreOverrideCursor()

            def _close_and_report() -> None:
                dialog.close()
                on_done(result, exc)

            elapsed_ms = (time.monotonic() - shown_at) * 1000
            QTimer.singleShot(max(0, round(self._MIN_VISIBLE_MS - elapsed_ms)), _close_and_report)

        def _run() -> None:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                result = func()
            except Exception as exc:  # noqa: BLE001 - handed to on_done, not crashed on
                _finish(None, exc)
                return
            _finish(result, None)

        QTimer.singleShot(self._START_DELAY_MS, _run)

    def _on_suggest_clips_clicked(self) -> None:
        if self._audio_path is None:
            return

        def _detect() -> list[Clip]:
            # Imported inside the busy dialog rather than at module load or
            # even eagerly here — `vad` imports torch at module level, which
            # is the actually-slow part (model loading is comparatively
            # quick), and a session that never clicks this button shouldn't
            # pay for it.
            from .. import vad

            return vad.suggest_snippets(self._audio_path)

        self._run_with_busy_dialog(
            "Suggest Clips",
            "Detecting speech in the recording…",
            _detect,
            self._on_suggest_clips_done,
        )

    def _on_suggest_clips_done(self, clips: list[Clip] | None, exc: Exception | None) -> None:
        if exc is not None:
            QMessageBox.critical(self, "Suggest Clips failed", str(exc))
            return

        if not clips:
            self.statusBar().showMessage("No speech detected.", 5000)
            return
        first_new_index = len(self._items)
        for clip in clips:
            self._items.add(Item(clip=clip, provenance=PROVENANCE_VAD))
        self._refresh_item_list_widget(select_index=first_new_index)
        self._update_item_regions()
        self._save_session()
        self.statusBar().showMessage(
            f"Added {len(clips)} suggested clip(s). Check Keep on the ones you want, "
            "then Discard Unchecked to drop the rest.",
            8000,
        )

    def _set_transcript_text(self, text: str) -> None:
        self._transcript_text = text
        self._loading_transcript_text = True
        try:
            self._transcript_text_edit.setPlainText(text)
        finally:
            self._loading_transcript_text = False
        self._transcript_panel.setVisible(bool(text))

    def _on_transcript_text_edited(self) -> None:
        if self._loading_transcript_text:
            return
        self._transcript_text = self._transcript_text_edit.toPlainText()
        self._save_session()

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
        was_playing = self._engine.is_playing()
        self._stop_loop()
        if was_playing:
            self._engine.pause()
        else:
            self._engine.play()

    def _seek_to_seconds(self, seconds: float) -> None:
        self._stop_loop()
        self._engine.seek(seconds)

    def _on_engine_position_changed(self, seconds: float) -> None:
        self._waveform.set_position(seconds)
        self._update_time_label(int(seconds * 1000))

    def _on_engine_duration_changed(self, seconds: float) -> None:
        self._duration_ms = int(seconds * 1000)
        self._waveform.set_duration(seconds)
        self._update_time_label(int(self._engine.position() * 1000))

    def _update_time_label(self, position_ms: int) -> None:
        self._time_label.setText(
            f"{format_time(position_ms / 1000)} / {format_time(self._duration_ms / 1000)}"
        )

    def _on_engine_playing_changed(self, playing: bool) -> None:
        if playing:
            self._play_button.setToolTip("Pause")
            self._play_button.setIcon(icon("mdi6.pause"))
        else:
            self._play_button.setToolTip("Play")
            self._play_button.setIcon(icon("mdi6.play"))
            # Covers both a user-initiated stop (_stop_loop calling
            # engine.stop_loop()) and the engine autonomously finishing a
            # non-repeating loop (clip-deck row play) — either way, once
            # the engine says it's no longer playing, the loop UI (button
            # text/icons, _loop_range bookkeeping) needs resetting.
            if self._loop_source is not None:
                self._reset_loop_ui()

    def _on_engine_error(self, message: str) -> None:
        QMessageBox.critical(self, "Playback error", message)

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
                self._engine.set_loop_bounds(*selection)

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

    def _on_clear_all_clicked(self) -> None:
        count = len(self._items)
        if count == 0:
            return
        plural = "" if count == 1 else "s"
        choice = QMessageBox.warning(
            self,
            "Clear all clips?",
            f"This will permanently discard all {count} item{plural} for the "
            "current file.\n\nContinue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        if self._loop_source == "item":
            self._stop_loop()
        self._items.clear()
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

    def _on_combine_with_next_clicked(self) -> None:
        index = self._item_list_widget.currentRow()
        if index < 0 or index >= len(self._items) - 1:
            return
        if self._loop_source == "item":
            self._stop_loop()
        first = self._items[index]
        second = self._items[index + 1]
        # min/max rather than assuming `second` starts after `first` — Move
        # Up/Down let items be reordered out of chronological order, so
        # list-adjacent items aren't guaranteed to be time-adjacent too.
        merged_clip = Clip(
            start_seconds=min(first.clip.start_seconds, second.clip.start_seconds),
            end_seconds=max(first.clip.end_seconds, second.clip.end_seconds),
        )
        merged_text = " ".join(t for t in (first.text.strip(), second.text.strip()) if t)
        # first's non-empty values win a key collision, since it's the item
        # the user had selected when choosing to combine.
        merged_extra_fields = {**second.extra_fields, **{k: v for k, v in first.extra_fields.items() if v}}
        # cloze_spans are dropped: their offsets are into the old, separate
        # texts and don't carry over into the merged text.
        merged = Item(
            clip=merged_clip,
            text=merged_text,
            extra_fields=merged_extra_fields,
            provenance=first.provenance if first.provenance == second.provenance else PROVENANCE_MANUAL,
        )
        self._items.replace(index, merged)
        self._items.remove(index + 1)
        self._refresh_item_list_widget(select_index=index)
        self._update_item_regions()
        self._save_session()

    def _on_item_region_edited(self, index: int, start: float, end: float) -> None:
        old = self._items[index]
        new_clip = Clip(start_seconds=start, end_seconds=end)
        self._items.replace(
            index,
            Item(
                clip=new_clip,
                text=old.text,
                cloze_spans=old.cloze_spans,
                extra_fields=old.extra_fields,
                provenance=old.provenance,
            ),
        )
        if self._loop_source == "item" and self._loop_item_index == index:
            self._loop_range = (start, end)
            self._engine.set_loop_bounds(start, end)
        self._refresh_item_list_widget()
        self._update_item_regions()
        if self._item_list_widget.currentRow() == index:
            self._update_card_preview()
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
        self._refresh_cloze_ui(index)
        self._rebuild_extra_field_inputs()

    def _on_item_text_changed(self) -> None:
        if self._loading_item_text:
            return
        index = self._item_list_widget.currentRow()
        if index < 0:
            return
        old = self._items[index]
        # Any text edit invalidates offsets into the old text, so all cloze
        # spans (if any) are dropped rather than left stale — Item(...)
        # already defaults cloze_spans to empty. extra_fields is unrelated
        # to the main text field, so it's carried over untouched.
        self._items.replace(
            index,
            Item(
                clip=old.clip,
                text=self._item_text_edit.toPlainText(),
                extra_fields=old.extra_fields,
                provenance=old.provenance,
            ),
        )
        # Refresh just this row in place, rather than a full table rebuild,
        # so the text edit's cursor position isn't disturbed mid-keystroke.
        self._populate_row(index, self._items[index])
        self._update_items_meta()
        self._refresh_cloze_ui(index)
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

    def _start_loop(
        self, loop_range: tuple[float, float], source: str, *, repeat: bool = True
    ) -> None:
        self._loop_range = loop_range
        self._loop_source = source
        self._loop_repeats = repeat
        self._engine.start_loop(loop_range[0], loop_range[1], repeat=repeat)
        self._preview_button.setText("Stop Preview" if source == "item" else "Loop Preview")
        self._preview_button.setIcon(icon("mdi6.stop" if source == "item" else "mdi6.repeat-variant"))
        self._play_selection_button.setToolTip(
            "Stop" if source == "selection" else "Play Selection (Loop)"
        )
        self._play_selection_button.setIcon(
            icon("mdi6.stop" if source == "selection" else "mdi6.repeat-variant")
        )

    def _stop_loop(self) -> None:
        # UI reset lives in _reset_loop_ui, reached reactively via
        # _on_engine_playing_changed(False) once engine.stop_loop() pauses
        # the transport — that same reactive path also covers a
        # non-repeating loop (clip-deck row play) finishing on its own, so
        # there's only one place that clears the loop UI state.
        if self._loop_source is None:
            return
        self._engine.stop_loop()

    def _reset_loop_ui(self) -> None:
        self._loop_range = None
        self._loop_source = None
        self._loop_item_index = None
        self._loop_repeats = True
        self._preview_button.setText("Loop Preview")
        self._preview_button.setIcon(icon("mdi6.repeat-variant"))
        self._play_selection_button.setToolTip("Play Selection (Loop)")
        self._play_selection_button.setIcon(icon("mdi6.repeat-variant"))

    def _refresh_item_list_widget(self, select_index: int | None = None) -> None:
        if select_index is None:
            select_index = self._item_list_widget.currentRow()
        # Drop any checked-id bookkeeping for items no longer in the list,
        # so a stale id can never be misread as "checked" again if a later
        # item object happens to get the same id() (CPython can and does
        # reuse a freed object's address).
        self._checked_item_ids &= {id(i) for i in self._items}
        self._item_list_widget.blockSignals(True)
        try:
            self._item_list_widget.setRowCount(len(self._items))
            for i, item in enumerate(self._items):
                self._populate_row(i, item)
        finally:
            self._item_list_widget.blockSignals(False)
        if 0 <= select_index < len(self._items):
            self._item_list_widget.setCurrentRow(select_index)
        self._update_item_buttons_enabled()
        self._update_items_meta()
        self._update_discard_unchecked_button()

    def _populate_row(self, row: int, item: Item) -> None:
        clip = item.clip
        range_text = (
            f"{format_time(clip.start_seconds)}–{format_time(clip.end_seconds)} "
            f"({format_time(clip.duration_seconds)})"
        )
        # The deck row shows the item's original text as typed/matched, not
        # a cloze-blanked rendering — DESIGN.md §6 originally called for a
        # blanked preview here, but the Cloze status badge already conveys
        # cloze progress and blanking made it harder to spot-check what a
        # clip's text actually says while scanning the deck.
        preview = item.text.strip().splitlines()[0] if item.text.strip() else "(no text)"
        if len(preview) > 60:
            preview = preview[:60] + "…"
        status_text, tone = self._item_status(item)

        check_item = QTableWidgetItem()
        check_item.setFlags(
            (check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable
        )
        check_item.setToolTip("Keep this clip")
        check_item.setCheckState(
            Qt.CheckState.Checked if id(item) in self._checked_item_ids else Qt.CheckState.Unchecked
        )
        self._item_list_widget.setItem(row, CHECK_COLUMN, check_item)

        range_item = QTableWidgetItem(range_text)
        range_item.setFlags(range_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        dot_color = theme.PROVENANCE_COLORS.get(item.provenance, theme.PROVENANCE_COLORS["manual"])
        range_item.setIcon(icon("mdi6.circle", color=dot_color))
        range_item.setToolTip(
            "Suggested by VAD" if item.provenance == PROVENANCE_VAD else "Manually created"
        )
        self._item_list_widget.setItem(row, RANGE_COLUMN, range_item)

        text_item = QTableWidgetItem(preview)
        text_item.setFlags(text_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if status_text != "Ready":
            text_item.setForeground(QColor(theme.TEXT_DISABLED))
        self._item_list_widget.setItem(row, TEXT_COLUMN, text_item)

        self._set_cell_widget(row, STATE_COLUMN, self._make_state_badge(status_text, tone))
        self._set_cell_widget(row, ACTIONS_COLUMN, self._make_row_actions(row))

    def _set_cell_widget(self, row: int, column: int, widget: QWidget) -> None:
        """QTableWidget.setCellWidget doesn't delete or hide the widget it
        replaces (a longstanding Qt gotcha), so a row that's repopulated
        many times over a session — every keystroke in the item text, every
        cloze mark/clear — would otherwise pile up stale, still-visible
        badge/action widgets on top of each other. Explicitly retire the
        old one before installing the new one."""
        old_widget = self._item_list_widget.cellWidget(row, column)
        self._item_list_widget.setCellWidget(row, column, widget)
        if old_widget is not None and old_widget is not widget:
            old_widget.hide()
            old_widget.deleteLater()

    def _item_status(self, item: Item) -> tuple[str, str]:
        """Three-state readiness per DESIGN.md §6 ("no text yet"/"no cloze
        yet"/"ready"), returned as (badge text, badge tone)."""
        if not item.text.strip():
            return "Not drafted", "hard"
        if not item.has_cloze:
            return "No cloze", "hard"
        return "Ready", "good"

    def _make_state_badge(self, status_text: str, tone: str) -> QWidget:
        badge = QLabel(status_text)
        badge.setObjectName("stateBadge")
        badge.setProperty("tone", tone)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Expanding (rather than the previous fixed-to-text width + stretch)
        # so every badge fills the column at the same width regardless of
        # its text — "Ready"/"No cloze"/"Not drafted" no longer render as
        # differently sized pills.
        badge.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(6, 0, 6, 0)
        container_layout.addWidget(badge)
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
        play_button.setToolTip("Play this clip")
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
        # Plays the clip once and stops, unlike the item editor's own "Loop
        # Preview" (_on_preview_clicked) — the clip deck is for a quick
        # listen while scanning many rows, not the repeated listening loop
        # that editing/transcribing a single item calls for.
        self._item_list_widget.setCurrentRow(row)
        if self._loop_source == "row" and self._loop_item_index == row:
            self._stop_loop()
            return
        item = self._items[row]
        self._loop_item_index = row
        self._start_loop(
            (item.clip.start_seconds, item.clip.end_seconds), source="row", repeat=False
        )

    def _on_row_delete_clicked(self, row: int) -> None:
        self._item_list_widget.setCurrentRow(row)
        self._on_remove_item_clicked()

    def _update_item_buttons_enabled(self) -> None:
        index = self._item_list_widget.currentRow()
        has_selection = index >= 0
        self._remove_item_button.setEnabled(has_selection)
        self._preview_button.setEnabled(has_selection)
        self._move_up_button.setEnabled(has_selection and index > 0)
        can_combine = has_selection and index < len(self._items) - 1
        self._move_down_button.setEnabled(can_combine)
        self._combine_with_next_button.setEnabled(can_combine)

    def _update_items_meta(self) -> None:
        count = len(self._items)
        ready = sum(1 for item in self._items if item.text.strip() and item.has_cloze)
        needs_cloze = sum(1 for item in self._items if item.text.strip() and not item.has_cloze)
        needs_text = count - ready - needs_cloze
        label = "1 item" if count == 1 else f"{count} items"
        self._items_count_label.setText(label)
        parts = []
        if ready:
            parts.append(f"{ready} ready")
        if needs_cloze:
            parts.append(f"{needs_cloze} need cloze")
        if needs_text:
            parts.append(f"{needs_text} need text")
        self._items_ready_label.setText(" · ".join(parts))
        self._status_items_label.setText(label)
        self._export_action.setEnabled(count > 0)
        self._export_action.setToolTip("" if count > 0 else "Add at least one item first")
        self._clear_all_button.setEnabled(count > 0)
        self._update_quick_export_enabled()

    def _update_item_regions(self) -> None:
        self._waveform.set_clip_regions(self._items.regions())

    # -- bulk "keep these, discard rest" review (Keep checkbox column) ------

    def _on_item_check_changed(self, table_item: QTableWidgetItem) -> None:
        if table_item.column() != CHECK_COLUMN:
            return
        row = table_item.row()
        if not (0 <= row < len(self._items)):
            return
        item_id = id(self._items[row])
        if table_item.checkState() == Qt.CheckState.Checked:
            self._checked_item_ids.add(item_id)
        else:
            self._checked_item_ids.discard(item_id)
        self._update_discard_unchecked_button()

    def _update_discard_unchecked_button(self) -> None:
        checked = len(self._checked_item_ids)
        total = len(self._items)
        unchecked = total - checked
        self._discard_unchecked_button.setEnabled(0 < checked < total)
        self._discard_unchecked_button.setText(
            f"Discard Unchecked ({unchecked})" if checked else "Discard Unchecked"
        )

    def _on_discard_unchecked_clicked(self) -> None:
        keep_indices = {
            i for i, item in enumerate(self._items) if id(item) in self._checked_item_ids
        }
        discard_count = len(self._items) - len(keep_indices)
        if discard_count <= 0:
            return
        plural = "" if discard_count == 1 else "s"
        choice = QMessageBox.warning(
            self,
            "Discard unchecked clips?",
            f"This will permanently discard the {discard_count} clip{plural} "
            "that aren't checked, keeping the rest.\n\nContinue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        if self._loop_source == "item":
            self._stop_loop()
        discard_indices = [i for i in range(len(self._items)) if i not in keep_indices]
        self._items.remove_many(discard_indices)
        self._checked_item_ids.clear()
        self._refresh_item_list_widget()
        self._update_item_regions()
        self._save_session()

    # -- cloze selection & card template (Phase 5, multi-cloze in 5.5) ------

    def _update_cloze_buttons_enabled(self) -> None:
        index = self._item_list_widget.currentRow()
        cursor = self._item_text_edit.textCursor()
        has_selection = cursor.hasSelection()
        overlaps = (
            index >= 0
            and has_selection
            and self._items[index].overlaps_existing_cloze(
                cursor.selectionStart(), cursor.selectionEnd()
            )
        )
        should_enable = index >= 0 and has_selection and not overlaps
        # Marking a cloze (button click or the Ctrl+Shift+C shortcut) leaves
        # the just-marked selection overlapping itself, so this button goes
        # straight from focused to disabled in the same call chain. Qt
        # responds to disabling a focused widget by handing focus to the
        # next one in tab order — here, "Loop Preview" — which then drags
        # the editor panel's scroll area down to keep that button visible,
        # so the UI appears to jump away from the item you were just
        # editing. Moving focus back to the text edit first heads that off.
        if not should_enable and self._mark_cloze_button.hasFocus():
            self._item_text_edit.setFocus()
        self._mark_cloze_button.setEnabled(should_enable)

    def _on_mark_cloze_clicked(self) -> None:
        index = self._item_list_widget.currentRow()
        cursor = self._item_text_edit.textCursor()
        if index < 0 or not cursor.hasSelection():
            return
        old = self._items[index]
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if old.overlaps_existing_cloze(start, end):
            return
        new_spans = [*old.cloze_spans, ClozeSpan(start=start, end=end)]
        self._items.replace(
            index,
            Item(
                clip=old.clip,
                text=old.text,
                cloze_spans=new_spans,
                extra_fields=old.extra_fields,
                provenance=old.provenance,
            ),
        )
        self._populate_row(index, self._items[index])
        self._update_items_meta()
        self._refresh_cloze_ui(index)
        self._save_session()

    def _on_remove_cloze_span(self, index: int, span: ClozeSpan) -> None:
        if index != self._item_list_widget.currentRow():
            return
        old = self._items[index]
        remaining = [s for s in old.cloze_spans if s != span]
        self._items.replace(
            index,
            Item(
                clip=old.clip,
                text=old.text,
                cloze_spans=remaining,
                extra_fields=old.extra_fields,
                provenance=old.provenance,
            ),
        )
        self._populate_row(index, self._items[index])
        self._update_items_meta()
        self._refresh_cloze_ui(index)
        self._save_session()

    def _refresh_cloze_ui(self, index: int) -> None:
        item = self._items[index] if index >= 0 else None
        spans = item.valid_cloze_spans() if item is not None else []
        self._item_text_edit.set_cloze_highlights(spans)
        self._rebuild_cloze_span_list(index, item, spans)
        self._update_cloze_buttons_enabled()
        self._update_card_preview()

    def _rebuild_cloze_span_list(
        self, index: int, item: Item | None, spans: list[ClozeSpan]
    ) -> None:
        while self._cloze_list_layout.count():
            child = self._cloze_list_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        if item is None:
            self._cloze_hint_label.setText("Select an item to mark a cloze.")
            self._cloze_hint_label.setVisible(True)
            return
        if not spans:
            self._cloze_hint_label.setText(
                "Select a span of the text above, then Mark as Cloze (Ctrl+Shift+C)."
            )
            self._cloze_hint_label.setVisible(True)
            return
        self._cloze_hint_label.setVisible(False)

        for cloze_number, span in enumerate(spans, start=1):
            row = QWidget(self._cloze_list_container)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(f'c{cloze_number}: “{item.text[span.start:span.end]}”', row)
            row_layout.addWidget(label)
            row_layout.addStretch()
            remove_button = QPushButton(row)
            remove_button.setIcon(icon("mdi6.close", color=theme.ACTION_DANGER))
            remove_button.setObjectName("rowIconButton")
            remove_button.setToolTip(f"Remove cloze c{cloze_number}")
            remove_button.setFixedSize(ROW_ICON_BUTTON_SIZE, ROW_ICON_BUTTON_SIZE)
            remove_button.clicked.connect(
                lambda _checked=False, idx=index, s=span: self._on_remove_cloze_span(idx, s)
            )
            row_layout.addWidget(remove_button)
            self._cloze_list_layout.addWidget(row)

    def _extra_field_names(self) -> list[str]:
        """Template fields with no automatically-derived value — everything
        except the cloze-text field (always the first field, by
        convention) and any field literally named "Audio". These are the
        fields `extra_field_inputs` shows editable boxes for in the item
        editor, and the only ones read from `item.extra_fields`."""
        fields = self._template.fields
        return [
            name
            for i, name in enumerate(fields)
            if i != 0 and name.strip().lower() != "audio"
        ]

    def _rebuild_extra_field_inputs(self) -> None:
        while self._extra_fields_layout.count():
            child = self._extra_fields_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._extra_field_edits = {}

        names = self._extra_field_names()
        if not names:
            self._extra_fields_section.setVisible(False)
            return

        index = self._item_list_widget.currentRow()
        item = self._items[index] if index >= 0 else None

        for name in names:
            field_container = QWidget(self._extra_fields_container)
            field_layout = QVBoxLayout(field_container)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(2)
            field_layout.addWidget(self._section_label(name))
            field_edit = ItemTextEdit(f"Type the {name.lower()} for this item…", field_container)
            field_edit.setFixedHeight(56)
            field_edit.setEnabled(item is not None)
            field_edit.textChanged.connect(
                lambda field_name=name: self._on_extra_field_text_changed(field_name)
            )
            field_layout.addWidget(field_edit)
            self._extra_fields_layout.addWidget(field_container)
            self._extra_field_edits[name] = field_edit

        self._loading_extra_fields = True
        try:
            for name, field_edit in self._extra_field_edits.items():
                field_edit.setPlainText(item.extra_fields.get(name, "") if item is not None else "")
        finally:
            self._loading_extra_fields = False

        # Made visible only after every row above already exists — doing
        # this before populating left the hidden->visible transition
        # computed against an empty container, and later additions never
        # fully recomputed the splitter panel's geometry (each row's own
        # sizeHint() was correct in isolation; the layout just never
        # re-queried it), showing up as the section's rows being clipped
        # to a sliver.
        self._extra_fields_section.setVisible(True)

    def _on_extra_field_text_changed(self, field_name: str) -> None:
        if self._loading_extra_fields:
            return
        index = self._item_list_widget.currentRow()
        field_edit = self._extra_field_edits.get(field_name)
        if index < 0 or field_edit is None:
            return
        old = self._items[index]
        new_extra_fields = dict(old.extra_fields)
        new_extra_fields[field_name] = field_edit.toPlainText()
        self._items.replace(
            index,
            Item(
                clip=old.clip,
                text=old.text,
                cloze_spans=old.cloze_spans,
                extra_fields=new_extra_fields,
                provenance=old.provenance,
            ),
        )
        self._update_card_preview()
        self._save_session()

    def _field_values_for_item(self, item: Item) -> dict[str, str]:
        fields = self._template.fields
        values: dict[str, str] = {}
        for i, name in enumerate(fields):
            if i == 0:
                values[name] = cloze_wrapped_text(item.text, item.valid_cloze_spans())
            elif name.strip().lower() == "audio":
                values[name] = (
                    f"🔊 {format_time(item.clip.start_seconds)}"
                    f"–{format_time(item.clip.end_seconds)}"
                )
            else:
                values[name] = item.extra_fields.get(name, "")
        return values

    def _sample_field_values(self) -> dict[str, str]:
        """Placeholder field values for the template editor's preview when
        no item is selected — bilingual per ROADMAP.md Phase 5's verify
        step, so the template editor's own preview isn't blank by default."""
        fields = self._template.fields or list(NoteTemplate().fields)
        values = {name: "" for name in fields}
        values[fields[0]] = "これは {{c1::サンプル}} な文です。"
        for name in fields:
            if name.strip().lower() == "audio":
                values[name] = "🔊 0:00–0:02"
        return values

    def _update_card_preview(self) -> None:
        index = self._item_list_widget.currentRow()
        if index < 0:
            self._preview_front_label.setText("")
            self._preview_back_label.setText("")
            self._multi_cloze_hint_label.setVisible(False)
            return
        values = self._field_values_for_item(self._items[index])

        cloze_count = cloze_index_count(values)
        if cloze_count > 1:
            self._multi_cloze_hint_label.setText(
                f"This will make {cloze_count} cards — showing card 1 only."
            )
        self._multi_cloze_hint_label.setVisible(cloze_count > 1)

        self._preview_front_label.setText(
            render_card(self._template.front_template, values, active_index=1, reveal=False)
        )
        self._preview_back_label.setText(
            render_card(self._template.back_template, values, active_index=1, reveal=True)
        )

    def _open_template_dialog(self) -> None:
        index = self._item_list_widget.currentRow()
        preview_values = (
            self._field_values_for_item(self._items[index])
            if index >= 0
            else self._sample_field_values()
        )
        dialog = NoteTemplateDialog(
            self._template, preview_values, self._template_library_path, self
        )
        dialog.template_changed.connect(self._on_template_changed)
        dialog.exec()

    def _on_template_changed(self, template: NoteTemplate) -> None:
        self._template = template
        self._rebuild_extra_field_inputs()
        self._update_card_preview()
        self._save_session()

    # -- preferences ----------------------------------------------------------

    def _open_preferences_dialog(self) -> None:
        dialog = PreferencesDialog(self)
        dialog.reset_all_confirmed.connect(self._on_reset_all_confirmed)
        dialog.exec()

    def _on_reset_all_confirmed(self) -> None:
        # Deletes the two files first and relaunches immediately after, in
        # the same call — no Qt event-loop turn runs in between where some
        # other queued autosave could recreate what was just deleted.
        self._session_path.unlink(missing_ok=True)
        self._template_library_path.unlink(missing_ok=True)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    # -- export (Phase 6) ----------------------------------------------------

    def _on_deck_name_edited(self, text: str) -> None:
        self._deck_name = text
        self._save_session()

    def _open_export_dialog(self) -> None:
        if len(self._items) == 0 or self._audio_path is None:
            return
        dialog = ExportDialog(
            self._items,
            self._template,
            self._audio_path,
            self._deck_name,
            self,
            initial_output_path=self._last_export_path,
        )
        dialog.exported.connect(self._on_exported)
        dialog.exec()

    def _on_exported(self, output_path: str) -> None:
        self._last_export_path = output_path
        self._update_quick_export_enabled()
        self._save_session()

    def _update_quick_export_enabled(self) -> None:
        can_quick_export = bool(self._last_export_path) and len(self._items) > 0
        self._quick_export_action.setEnabled(can_quick_export)
        self._quick_export_action.setToolTip(
            f"Re-export to {self._last_export_path}"
            if self._last_export_path
            else "Export once first to set an output file"
        )

    def _on_quick_export_clicked(self) -> None:
        if not self._last_export_path or len(self._items) == 0 or self._audio_path is None:
            return
        export_path = self._last_export_path

        def _do_export() -> None:
            export_apkg(
                self._items,
                self._template,
                self._audio_path,
                self._deck_name.strip(),
                export_path,
                skip_incomplete=False,
            )

        # A blocking export.export_apkg call previously ran with no visible
        # feedback beyond a status bar message shown only after the fact —
        # on a deck with several items (each clip gets its own audio slice
        # written to disk), that left the window looking frozen/unresponsive
        # while it ran, and the status bar message alone was easy to miss,
        # so a "did that actually do anything?" quick-export didn't feel
        # like it had. The same guaranteed-visible busy dialog Suggest Clips
        # uses covers both: a spinner while it's genuinely working, and a
        # brief, hard-to-miss confirmation once it's done.
        self._run_with_busy_dialog(
            "Quick Export", "Exporting…", _do_export, self._on_quick_export_done
        )

    def _on_quick_export_done(self, _result: None, exc: Exception | None) -> None:
        if isinstance(exc, ExportBlockedError):
            QMessageBox.warning(
                self,
                "Cannot quick-export",
                f"{len(exc.issues)} item(s) are missing text or a cloze — "
                "open Export to review and skip them, or fix them first.",
            )
            return
        if isinstance(exc, OSError):
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(f"Quick-exported to {self._last_export_path}", 5000)

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
        self._items.replace(
            item_index,
            Item(
                clip=old.clip,
                text=selected_text,
                extra_fields=old.extra_fields,
                provenance=old.provenance,
            ),
        )
        self._populate_row(item_index, self._items[item_index])
        self._update_items_meta()
        if self._item_list_widget.currentRow() == item_index:
            self._loading_item_text = True
            try:
                self._item_text_edit.setPlainText(self._items[item_index].text)
            finally:
                self._loading_item_text = False
        self._refresh_cloze_ui(item_index)
        self._save_session()
