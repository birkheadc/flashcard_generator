from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..audio.waveform import WaveformData


class WaveformWidget(QWidget):
    """Paints min/max peak columns for a loaded WaveformData and a playhead.

    Click-or-drag anywhere to seek; emits seek_requested(seconds).
    """

    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data: WaveformData | None = None
        self._position_seconds = 0.0
        self._duration_seconds = 0.0
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_waveform(self, data: WaveformData | None) -> None:
        self._data = data
        self._position_seconds = 0.0
        self._duration_seconds = data.duration_seconds if data else 0.0
        self.update()

    def set_duration(self, seconds: float) -> None:
        # Authoritative duration comes from the media player once it opens
        # the file, which can differ slightly from soundfile's estimate.
        self._duration_seconds = seconds
        self.update()

    def set_position(self, seconds: float) -> None:
        self._position_seconds = seconds
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        width = self.width()
        height = self.height()
        mid_y = height / 2

        painter.setPen(QPen(QColor("#3a3a3a")))
        painter.drawLine(0, int(mid_y), width, int(mid_y))

        if self._data is not None and width > 0:
            peaks_min = self._data.peaks_min
            peaks_max = self._data.peaks_max
            num_columns = len(peaks_min)
            painter.setPen(QPen(QColor("#4fc3f7")))
            for x in range(width):
                idx = min(int(x * num_columns / width), num_columns - 1)
                y_top = mid_y - float(peaks_max[idx]) * mid_y
                y_bottom = mid_y - float(peaks_min[idx]) * mid_y
                painter.drawLine(x, int(y_top), x, int(y_bottom))

            if self._duration_seconds > 0:
                fraction = min(max(self._position_seconds / self._duration_seconds, 0.0), 1.0)
                playhead_x = int(fraction * width)
                painter.setPen(QPen(QColor("#ff5252"), 2))
                painter.drawLine(playhead_x, 0, playhead_x, height)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._seek_to_x(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._seek_to_x(event.position().x())

    def _seek_to_x(self, x: float) -> None:
        if self._duration_seconds <= 0 or self.width() <= 0:
            return
        fraction = min(max(x / self.width(), 0.0), 1.0)
        self.seek_requested.emit(fraction * self._duration_seconds)
