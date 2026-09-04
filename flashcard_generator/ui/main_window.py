from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..audio.waveform import AudioTooLongError, compute_waveform
from ..clips import Clip, ClipList
from .format_time import format_time
from .waveform_view import WaveformView

SUPPORTED_EXTENSIONS = ["wav", "flac", "ogg", "mp3", "aiff"]
AUDIO_FILE_FILTER = (
    "Audio files (" + " ".join(f"*.{ext}" for ext in SUPPORTED_EXTENSIONS) + ");;All files (*)"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flashcard Generator")
        self.resize(1100, 450)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._duration_ms = 0
        self._clips = ClipList()
        self._pending_selection: tuple[float, float] | None = None
        self._loop_range: tuple[float, float] | None = None
        self._loop_source: str | None = None  # "clip" | "selection" | None
        self._loop_clip_index: int | None = None

        self._build_ui()
        self._build_toolbar()

    def _build_ui(self) -> None:
        playback_panel = QWidget(self)
        layout = QVBoxLayout(playback_panel)

        self._waveform = WaveformView(playback_panel)
        self._waveform.seek_requested.connect(self._seek_to_seconds)
        self._waveform.selection_changed.connect(self._on_selection_changed)
        self._waveform.clip_region_edited.connect(self._on_clip_region_edited)
        layout.addWidget(self._waveform)

        hint = QLabel("Shift+drag to select a region · drag a region's edge to resize it")
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

        controls = QHBoxLayout()
        self._play_button = QPushButton("Play")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._toggle_playback)
        controls.addWidget(self._play_button)

        self._play_selection_button = QPushButton("Play Selection (Loop)")
        self._play_selection_button.setEnabled(False)
        self._play_selection_button.clicked.connect(self._on_play_selection_clicked)
        controls.addWidget(self._play_selection_button)

        self._time_label = QLabel("0:00 / 0:00")
        controls.addWidget(self._time_label)
        controls.addStretch()

        layout.addLayout(controls)

        splitter = QSplitter(self)
        splitter.addWidget(playback_panel)
        splitter.addWidget(self._build_clip_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _build_clip_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("Clips"))

        self._clip_list_widget = QListWidget(panel)
        self._clip_list_widget.currentRowChanged.connect(self._update_clip_buttons_enabled)
        layout.addWidget(self._clip_list_widget)

        self._add_clip_button = QPushButton("Add Clip")
        self._add_clip_button.setEnabled(False)
        self._add_clip_button.setToolTip("Select a region on the waveform (Shift+drag) first")
        self._add_clip_button.clicked.connect(self._on_add_clip_clicked)
        layout.addWidget(self._add_clip_button)

        reorder_row = QHBoxLayout()
        self._move_up_button = QPushButton("Move Up")
        self._move_up_button.clicked.connect(self._on_move_clip_up)
        reorder_row.addWidget(self._move_up_button)
        self._move_down_button = QPushButton("Move Down")
        self._move_down_button.clicked.connect(self._on_move_clip_down)
        reorder_row.addWidget(self._move_down_button)
        layout.addLayout(reorder_row)

        self._preview_button = QPushButton("Loop Preview")
        self._preview_button.clicked.connect(self._on_preview_clicked)
        layout.addWidget(self._preview_button)

        self._remove_clip_button = QPushButton("Remove")
        self._remove_clip_button.clicked.connect(self._on_remove_clip_clicked)
        layout.addWidget(self._remove_clip_button)

        self._update_clip_buttons_enabled()
        return panel

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        import_action = QAction("Import file…", self)
        import_action.setShortcut("Ctrl+O")
        import_action.triggered.connect(self._import_file)
        toolbar.addAction(import_action)

        record_action = QAction("Record in-app", self)
        record_action.setEnabled(False)
        record_action.setToolTip("Not yet implemented")
        toolbar.addAction(record_action)

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import audio file", "", AUDIO_FILE_FILTER)
        if not path:
            return
        self._load_audio_file(path)

    def _load_audio_file(self, path: str) -> None:
        if len(self._clips) > 0 and not self._confirm_discard_clips():
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
        self._clips.clear()
        self._refresh_clip_list_widget()
        self._waveform.set_waveform(waveform_data)
        self._update_clip_regions()
        self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self._play_button.setEnabled(True)
        self.setWindowTitle(f"Flashcard Generator — {Path(path).name}")

    def _confirm_discard_clips(self) -> bool:
        count = len(self._clips)
        plural = "" if count == 1 else "s"
        choice = QMessageBox.warning(
            self,
            "Discard clips?",
            f"Loading a new file will discard the {count} clip{plural} you've "
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
        self._stop_loop()
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
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
        else:
            self._play_button.setText("Play")

    def _on_player_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            QMessageBox.critical(self, "Playback error", error_string)

    # -- clips ----------------------------------------------------------

    def _on_selection_changed(self, selection: tuple[float, float] | None) -> None:
        self._pending_selection = selection
        self._add_clip_button.setEnabled(selection is not None)
        self._play_selection_button.setEnabled(selection is not None)
        if self._loop_source == "selection":
            if selection is None:
                self._stop_loop()
            else:
                self._loop_range = selection

    def _on_add_clip_clicked(self) -> None:
        if self._pending_selection is None:
            return
        start, end = self._pending_selection
        self._clips.add(Clip(start_seconds=start, end_seconds=end))
        self._waveform.clear_selection()
        self._refresh_clip_list_widget(select_index=len(self._clips) - 1)
        self._update_clip_regions()

    def _on_remove_clip_clicked(self) -> None:
        index = self._clip_list_widget.currentRow()
        if index < 0:
            return
        if self._loop_source == "clip":
            self._stop_loop()
        self._clips.remove(index)
        self._refresh_clip_list_widget()
        self._update_clip_regions()

    def _on_move_clip_up(self) -> None:
        index = self._clip_list_widget.currentRow()
        if index <= 0:
            return
        if self._loop_source == "clip":
            self._stop_loop()
        self._clips.move(index, index - 1)
        self._refresh_clip_list_widget(select_index=index - 1)
        self._update_clip_regions()

    def _on_move_clip_down(self) -> None:
        index = self._clip_list_widget.currentRow()
        if index < 0 or index >= len(self._clips) - 1:
            return
        if self._loop_source == "clip":
            self._stop_loop()
        self._clips.move(index, index + 1)
        self._refresh_clip_list_widget(select_index=index + 1)
        self._update_clip_regions()

    def _on_clip_region_edited(self, index: int, start: float, end: float) -> None:
        old = self._clips[index]
        self._clips.replace(index, Clip(start_seconds=start, end_seconds=end, label=old.label))
        if self._loop_source == "clip" and self._loop_clip_index == index:
            self._loop_range = (start, end)
        self._refresh_clip_list_widget()
        self._update_clip_regions()

    def _on_preview_clicked(self) -> None:
        index = self._clip_list_widget.currentRow()
        if index < 0:
            return
        if self._loop_source == "clip" and self._loop_clip_index == index:
            self._stop_loop()
            return
        clip = self._clips[index]
        self._loop_clip_index = index
        self._start_loop((clip.start_seconds, clip.end_seconds), source="clip")

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
        self._preview_button.setText("Stop Preview" if source == "clip" else "Loop Preview")
        self._play_selection_button.setText(
            "Stop" if source == "selection" else "Play Selection (Loop)"
        )

    def _stop_loop(self) -> None:
        if self._loop_source is None:
            return
        self._loop_range = None
        self._loop_source = None
        self._loop_clip_index = None
        self._player.pause()
        self._preview_button.setText("Loop Preview")
        self._play_selection_button.setText("Play Selection (Loop)")

    def _refresh_clip_list_widget(self, select_index: int | None = None) -> None:
        if select_index is None:
            select_index = self._clip_list_widget.currentRow()
        self._clip_list_widget.clear()
        for i, clip in enumerate(self._clips):
            text = (
                f"{i + 1}. {format_time(clip.start_seconds)}–{format_time(clip.end_seconds)} "
                f"({format_time(clip.duration_seconds)})"
            )
            self._clip_list_widget.addItem(text)
        if 0 <= select_index < len(self._clips):
            self._clip_list_widget.setCurrentRow(select_index)
        self._update_clip_buttons_enabled()

    def _update_clip_buttons_enabled(self) -> None:
        index = self._clip_list_widget.currentRow()
        has_selection = index >= 0
        self._remove_clip_button.setEnabled(has_selection)
        self._preview_button.setEnabled(has_selection)
        self._move_up_button.setEnabled(has_selection and index > 0)
        self._move_down_button.setEnabled(has_selection and index < len(self._clips) - 1)

    def _update_clip_regions(self) -> None:
        self._waveform.set_clip_regions(self._clips.regions())
