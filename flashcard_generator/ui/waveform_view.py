from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..audio.waveform import WaveformData
from .format_time import format_time
from .waveform_widget import WaveformWidget

MIN_ZOOM = 1.0
MAX_ZOOM = 64.0
ZOOM_STEP = 2.0

RULER_HEIGHT = 24

# Candidate tick spacings (seconds), tried smallest-first until one is wide
# enough on screen not to crowd its neighbors.
_NICE_INTERVALS = [
    0.1, 0.2, 0.5,
    1, 2, 5, 10, 15, 30,
    60, 120, 300, 600, 900, 1800,
    3600,
]


def _nice_tick_interval(pixels_per_second: float, min_pixel_spacing: float = 60.0) -> float:
    if pixels_per_second <= 0:
        return _NICE_INTERVALS[-1]
    target = min_pixel_spacing / pixels_per_second
    for interval in _NICE_INTERVALS:
        if interval >= target:
            return interval
    return _NICE_INTERVALS[-1]


class TimeRulerWidget(QWidget):
    """Timeline ruler: tick marks with time labels plus a playhead marker.

    Kept the same width as the WaveformWidget it sits above (both are laid
    out by WaveformView), so a given x means the same point in time in both.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._duration_seconds = 0.0
        self._position_seconds = 0.0
        self.setFixedHeight(RULER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_duration(self, seconds: float) -> None:
        self._duration_seconds = seconds
        self.update()

    def set_position(self, seconds: float) -> None:
        self._position_seconds = seconds
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#252525"))

        width = self.width()
        height = self.height()

        if self._duration_seconds > 0 and width > 0:
            pixels_per_second = width / self._duration_seconds
            interval = _nice_tick_interval(pixels_per_second)

            painter.setPen(QPen(QColor("#9a9a9a")))
            tick_count = int(self._duration_seconds / interval) + 2
            for i in range(tick_count):
                t = i * interval
                if t > self._duration_seconds:
                    break
                x = int(t * pixels_per_second)
                painter.drawLine(x, height - 6, x, height)
                label = f"{t:.1f}s" if interval < 1 else format_time(t)
                painter.drawText(x + 3, height - 8, label)

            fraction = min(max(self._position_seconds / self._duration_seconds, 0.0), 1.0)
            playhead_x = int(fraction * width)
            painter.setPen(QPen(QColor("#ff5252"), 2))
            painter.drawLine(playhead_x, 0, playhead_x, height)

        painter.end()


class WaveformView(QWidget):
    """Zoomable, scrollable waveform display: toolbar + ruler + waveform.

    Wraps WaveformWidget rather than modifying it, so the existing widget
    keeps painting over exactly its own width; zoom is realized by resizing
    that widget (and the ruler beside it) inside a QScrollArea.
    """

    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._zoom = MIN_ZOOM
        self._duration_seconds = 0.0

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Zoom:"))

        self._zoom_out_button = QPushButton("−")
        self._zoom_out_button.setFixedWidth(28)
        self._zoom_out_button.setToolTip("Zoom out")
        self._zoom_out_button.clicked.connect(self._on_zoom_out)
        toolbar.addWidget(self._zoom_out_button)

        self._zoom_in_button = QPushButton("+")
        self._zoom_in_button.setFixedWidth(28)
        self._zoom_in_button.setToolTip("Zoom in")
        self._zoom_in_button.clicked.connect(self._on_zoom_in)
        toolbar.addWidget(self._zoom_in_button)

        self._zoom_fit_button = QPushButton("Fit")
        self._zoom_fit_button.setToolTip("Reset zoom to fit the whole file")
        self._zoom_fit_button.clicked.connect(self._on_zoom_fit)
        toolbar.addWidget(self._zoom_fit_button)

        self._zoom_label = QLabel("100%")
        toolbar.addWidget(self._zoom_label)
        toolbar.addStretch()
        outer_layout.addLayout(toolbar)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer_layout.addWidget(self._scroll_area)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._ruler = TimeRulerWidget(self._content)
        content_layout.addWidget(self._ruler)

        self._waveform = WaveformWidget(self._content)
        content_layout.addWidget(self._waveform)

        self._scroll_area.setWidget(self._content)

        # Ctrl+wheel zooms (anchored on the cursor); plain wheel scrolls
        # horizontally, since there's nothing to scroll vertically here.
        self._waveform.installEventFilter(self)
        self._ruler.installEventFilter(self)

        self._waveform.seek_requested.connect(self.seek_requested)

        self._update_buttons_enabled()

    # -- public API, mirrors the plain WaveformWidget's -------------------

    def set_waveform(self, data: WaveformData | None) -> None:
        self._waveform.set_waveform(data)
        self._duration_seconds = data.duration_seconds if data else 0.0
        self._ruler.set_duration(self._duration_seconds)
        self._zoom = MIN_ZOOM
        self._zoom_label.setText("100%")
        self._relayout_content()
        self._scroll_area.horizontalScrollBar().setValue(0)
        self._update_buttons_enabled()

    def set_duration(self, seconds: float) -> None:
        self._duration_seconds = seconds
        self._waveform.set_duration(seconds)
        self._ruler.set_duration(seconds)

    def set_position(self, seconds: float) -> None:
        self._waveform.set_position(seconds)
        self._ruler.set_position(seconds)
        self._autoscroll_to(seconds)

    # -- zoom ---------------------------------------------------------------

    def _on_zoom_in(self) -> None:
        self._set_zoom(self._zoom * ZOOM_STEP)

    def _on_zoom_out(self) -> None:
        self._set_zoom(self._zoom / ZOOM_STEP)

    def _on_zoom_fit(self) -> None:
        self._set_zoom(MIN_ZOOM)

    def _set_zoom(self, zoom: float, anchor_fraction: float | None = None) -> None:
        zoom = min(max(zoom, MIN_ZOOM), MAX_ZOOM)
        if zoom == self._zoom:
            return
        if anchor_fraction is None:
            anchor_fraction = self._visible_center_fraction()
        self._zoom = zoom
        self._zoom_label.setText(f"{round(zoom * 100)}%")
        self._relayout_content()
        self._scroll_to_fraction(anchor_fraction)
        self._update_buttons_enabled()

    def _update_buttons_enabled(self) -> None:
        self._zoom_in_button.setEnabled(self._zoom < MAX_ZOOM - 1e-9)
        at_fit = self._zoom <= MIN_ZOOM + 1e-9
        self._zoom_out_button.setEnabled(not at_fit)
        self._zoom_fit_button.setEnabled(not at_fit)

    # -- layout / scrolling ---------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        super().resizeEvent(event)
        self._relayout_content()

    def _relayout_content(self) -> None:
        viewport_width = self._scroll_area.viewport().width()
        viewport_height = self._scroll_area.viewport().height()
        if viewport_width <= 0:
            return
        content_width = max(viewport_width, round(viewport_width * self._zoom))
        waveform_height = max(self._waveform.minimumHeight(), viewport_height - RULER_HEIGHT)

        self._ruler.setFixedWidth(content_width)
        self._waveform.setFixedSize(content_width, waveform_height)
        self._content.setFixedSize(content_width, RULER_HEIGHT + waveform_height)

    def _visible_center_fraction(self) -> float:
        if self._content.width() <= 0:
            return 0.0
        viewport_width = self._scroll_area.viewport().width()
        center_x = self._scroll_area.horizontalScrollBar().value() + viewport_width / 2
        return min(max(center_x / self._content.width(), 0.0), 1.0)

    def _scroll_to_fraction(self, fraction: float) -> None:
        bar = self._scroll_area.horizontalScrollBar()
        viewport_width = self._scroll_area.viewport().width()
        target = round(fraction * self._content.width() - viewport_width / 2)
        bar.setValue(max(0, min(target, bar.maximum())))

    def _autoscroll_to(self, seconds: float) -> None:
        """Keep the playhead in view once it nears the edge of a zoomed-in view."""
        if self._duration_seconds <= 0 or self._content.width() <= 0:
            return
        bar = self._scroll_area.horizontalScrollBar()
        if bar.maximum() <= 0:
            return  # whole file already visible

        fraction = min(max(seconds / self._duration_seconds, 0.0), 1.0)
        x = fraction * self._content.width()
        viewport_width = self._scroll_area.viewport().width()
        margin = viewport_width * 0.1
        left = bar.value()
        right = left + viewport_width
        if x < left + margin or x > right - margin:
            target = round(x - viewport_width / 2)
            bar.setValue(max(0, min(target, bar.maximum())))

    # -- ctrl+wheel zoom, plain wheel horizontal scroll ------------------

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001 - Qt override signature
        if event.type() == QEvent.Type.Wheel and obj in (self._waveform, self._ruler):
            self._handle_wheel(event)
            return True
        return super().eventFilter(obj, event)

    def _handle_wheel(self, event) -> None:  # noqa: ANN001 - QWheelEvent
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            content_width = self._content.width()
            anchor_fraction = event.position().x() / content_width if content_width else 0.0
            factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
            self._set_zoom(self._zoom * factor, anchor_fraction=anchor_fraction)
        else:
            bar = self._scroll_area.horizontalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
