from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..audio.waveform import WaveformData
from . import theme
from .format_time import format_time
from .waveform_widget import WaveformWidget

MIN_ZOOM = 1.0
MAX_ZOOM = 64.0
ZOOM_STEP = 0.25  # flat increment per step (25% of MIN_ZOOM), not a multiplier
ZOOM_SLIDER_RESOLUTION = 1000  # slider's own int range; independent of ZOOM_STEP

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
        painter.fillRect(self.rect(), QColor(theme.PAPER_1))

        width = self.width()
        height = self.height()

        if self._duration_seconds > 0 and width > 0:
            pixels_per_second = width / self._duration_seconds
            interval = _nice_tick_interval(pixels_per_second)

            painter.setPen(QPen(QColor(theme.TEXT_DISABLED)))
            metrics = QFontMetrics(painter.font())
            tick_count = int(self._duration_seconds / interval) + 2
            for i in range(tick_count):
                t = i * interval
                if t > self._duration_seconds:
                    break
                x = int(t * pixels_per_second)
                painter.drawLine(x, height - 6, x, height)
                label = f"{t:.1f}s" if interval < 1 else format_time(t)
                # Centered directly above its tick; skipped rather than
                # clamped if that would run the label off either edge.
                label_x = x - metrics.horizontalAdvance(label) // 2
                if label_x >= 0 and label_x + metrics.horizontalAdvance(label) <= width:
                    painter.drawText(label_x, height - 8, label)

            fraction = min(max(self._position_seconds / self._duration_seconds, 0.0), 1.0)
            playhead_x = int(fraction * width)
            painter.setPen(QPen(QColor(theme.INK_0), 2))
            painter.drawLine(playhead_x, 0, playhead_x, height)

        painter.end()


class _HorizontalScrollArea(QScrollArea):
    """A QScrollArea for timeline content: genuinely horizontal wheel input
    (a horizontal trackpad swipe, or the OS's own shift+wheel convention,
    which typically arrives as a horizontal delta already) pans sideways.
    Ctrl+wheel requests a zoom instead of scrolling.

    Plain *vertical* wheel input is deliberately left alone rather than
    remapped to horizontal panning — spinning a normal mouse wheel
    shouldn't shove the timeline sideways. It falls through to the
    default QScrollArea behavior, which scrolls vertically if this view
    ever actually has something to scroll to there (normally it doesn't —
    content is sized to fill the viewport's height) and otherwise no-ops.

    Overriding wheelEvent directly here — rather than installing an event
    filter on specific child widgets — means every wheel event that
    bubbles up through this scroll area is covered (any child widget that
    doesn't itself handle wheelEvent, like the plain QWidget-based ruler
    and waveform canvas, ignores it by default and Qt bubbles it up to
    here), not just events landing on the one or two widgets we thought to
    filter.
    """

    zoom_requested = Signal(float, float)  # (direction: +1/-1, anchor_fraction 0..1)

    def wheelEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta == 0:
                delta = event.pixelDelta().y() or event.pixelDelta().x()
            if delta == 0:
                event.ignore()
                return
            content = self.widget()
            content_width = content.width() if content else 0
            anchor_fraction = event.position().x() / content_width if content_width else 0.0
            self.zoom_requested.emit(1.0 if delta > 0 else -1.0, anchor_fraction)
            event.accept()
            return

        horizontal_delta = event.angleDelta().x() or event.pixelDelta().x()
        if horizontal_delta == 0:
            super().wheelEvent(event)
            return
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - horizontal_delta)
        event.accept()


class WaveformView(QWidget):
    """Zoomable, scrollable waveform display: toolbar + ruler + waveform.

    Wraps WaveformWidget rather than modifying it, so the existing widget
    keeps painting over exactly its own width; zoom is realized by resizing
    that widget (and the ruler beside it) inside a QScrollArea.
    """

    seek_requested = Signal(float)
    selection_changed = Signal(object)  # tuple[float, float] | None
    clip_region_edited = Signal(int, float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._zoom = MIN_ZOOM
        self._duration_seconds = 0.0

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Built here (so it shares zoom state/logic with the rest of this
        # widget) but deliberately *not* added to outer_layout — the caller
        # embeds `self.zoom_bar` whererever it belongs in its own layout
        # (the transport row under the waveform, per the design), rather
        # than it always sitting in its own row above the ruler.
        self.zoom_bar = self._build_zoom_bar()

        self._scroll_area = _HorizontalScrollArea(self)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.zoom_requested.connect(self._on_zoom_wheel)
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

        # Qt is supposed to bubble an ignored wheel event up from a plain
        # QWidget (the ruler, the waveform canvas — neither overrides
        # wheelEvent, so both ignore it by default) to its QScrollArea
        # ancestor, which is what would normally reach
        # _HorizontalScrollArea.wheelEvent on its own. That bubbling lives
        # in the platform windowing dispatch path though, not in
        # QCoreApplication::notify — it doesn't fire for a directly
        # sendEvent()-ed wheel event, and isn't worth trusting blindly
        # across Qt/platform versions either. Filtering these two widgets
        # explicitly and forwarding to the same handler removes that
        # uncertainty rather than relying on bubbling actually happening.
        self._waveform.installEventFilter(self)
        self._ruler.installEventFilter(self)

        # The viewport only reaches its real size once this widget is
        # actually shown/laid out — set_waveform() called beforehand (e.g.
        # restoring a session on startup) sees a stale, tiny viewport and
        # _relayout_content() no-ops. Watch the viewport itself for its
        # resize, since that's the one event guaranteed to fire once the
        # real size is known, and redo the layout then.
        self._scroll_area.viewport().installEventFilter(self)

        self._waveform.seek_requested.connect(self.seek_requested)
        self._waveform.selection_changed.connect(self.selection_changed)
        self._waveform.clip_region_edited.connect(self.clip_region_edited)

        self._update_buttons_enabled()

    def _build_zoom_bar(self) -> QWidget:
        bar = QWidget(self)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        caption = QLabel(theme.section_label_text("Zoom"), bar)
        caption.setObjectName("sectionLabel")
        row.addWidget(caption)

        self._zoom_out_button = QPushButton("−", bar)
        self._zoom_out_button.setObjectName("zoomStepButton")
        self._zoom_out_button.setFixedSize(22, 22)
        self._zoom_out_button.setToolTip("Zoom out")
        self._zoom_out_button.clicked.connect(self._on_zoom_out)
        row.addWidget(self._zoom_out_button)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal, bar)
        self._zoom_slider.setFixedWidth(96)
        self._zoom_slider.setRange(0, ZOOM_SLIDER_RESOLUTION)
        self._zoom_slider.setValue(self._zoom_to_slider_value(MIN_ZOOM))
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        row.addWidget(self._zoom_slider)

        self._zoom_in_button = QPushButton("+", bar)
        self._zoom_in_button.setObjectName("zoomStepButton")
        self._zoom_in_button.setFixedSize(22, 22)
        self._zoom_in_button.setToolTip("Zoom in")
        self._zoom_in_button.clicked.connect(self._on_zoom_in)
        row.addWidget(self._zoom_in_button)

        self._zoom_fit_button = QPushButton("Fit", bar)
        self._zoom_fit_button.setToolTip("Reset zoom to fit the whole file")
        self._zoom_fit_button.clicked.connect(self._on_zoom_fit)
        row.addWidget(self._zoom_fit_button)

        self._zoom_label = QLabel("100%", bar)
        self._zoom_label.setObjectName("metaLabel")
        self._zoom_label.setFixedWidth(38)
        row.addWidget(self._zoom_label)

        return bar

    # -- public API, mirrors the plain WaveformWidget's -------------------

    def set_waveform(self, data: WaveformData | None) -> None:
        self._waveform.set_waveform(data)
        self._duration_seconds = data.duration_seconds if data else 0.0
        self._ruler.set_duration(self._duration_seconds)
        self._zoom = MIN_ZOOM
        self._zoom_label.setText("100%")
        self._sync_zoom_slider()
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

    @property
    def selection(self) -> tuple[float, float] | None:
        return self._waveform.selection

    def clear_selection(self) -> None:
        self._waveform.clear_selection()

    def set_clip_regions(self, regions: list[tuple[float, float]]) -> None:
        self._waveform.set_clip_regions(regions)

    # -- zoom ---------------------------------------------------------------

    def _on_zoom_in(self) -> None:
        self._set_zoom(self._zoom + ZOOM_STEP)

    def _on_zoom_out(self) -> None:
        self._set_zoom(self._zoom - ZOOM_STEP)

    def _on_zoom_fit(self) -> None:
        self._set_zoom(MIN_ZOOM)

    def _on_zoom_wheel(self, direction: float, anchor_fraction: float) -> None:
        self._set_zoom(self._zoom + direction * ZOOM_STEP, anchor_fraction=anchor_fraction)

    def _zoom_to_slider_value(self, zoom: float) -> int:
        fraction = (zoom - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)
        return round(fraction * ZOOM_SLIDER_RESOLUTION)

    def _slider_value_to_zoom(self, value: int) -> float:
        fraction = value / ZOOM_SLIDER_RESOLUTION
        return MIN_ZOOM + fraction * (MAX_ZOOM - MIN_ZOOM)

    def _sync_zoom_slider(self) -> None:
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(self._zoom_to_slider_value(self._zoom))
        self._zoom_slider.blockSignals(False)

    def _on_zoom_slider_changed(self, value: int) -> None:
        self._set_zoom(self._slider_value_to_zoom(value))

    def _set_zoom(self, zoom: float, anchor_fraction: float | None = None) -> None:
        zoom = min(max(zoom, MIN_ZOOM), MAX_ZOOM)
        if zoom == self._zoom:
            return
        if anchor_fraction is None:
            anchor_fraction = self._visible_center_fraction()
        self._zoom = zoom
        self._zoom_label.setText(f"{round(zoom * 100)}%")
        self._sync_zoom_slider()
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

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001 - Qt override signature
        if event.type() == QEvent.Type.Wheel and obj in (self._waveform, self._ruler):
            self._scroll_area.wheelEvent(event)
            return True
        if event.type() == QEvent.Type.Resize and obj is self._scroll_area.viewport():
            self._relayout_content()
            return False
        return super().eventFilter(obj, event)
