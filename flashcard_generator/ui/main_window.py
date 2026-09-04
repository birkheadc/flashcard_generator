from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..audio.waveform import AudioTooLongError, compute_waveform
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
        self.resize(900, 400)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._duration_ms = 0

        self._build_ui()
        self._build_toolbar()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        self._waveform = WaveformView(central)
        self._waveform.seek_requested.connect(self._seek_to_seconds)
        layout.addWidget(self._waveform)

        controls = QHBoxLayout()
        self._play_button = QPushButton("Play")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._toggle_playback)
        controls.addWidget(self._play_button)

        self._time_label = QLabel("0:00 / 0:00")
        controls.addWidget(self._time_label)
        controls.addStretch()

        layout.addLayout(controls)
        self.setCentralWidget(central)

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
        self._waveform.set_waveform(waveform_data)
        self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self._play_button.setEnabled(True)
        self.setWindowTitle(f"Flashcard Generator — {Path(path).name}")

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
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _seek_to_seconds(self, seconds: float) -> None:
        self._player.setPosition(int(seconds * 1000))

    def _on_position_changed(self, position_ms: int) -> None:
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
