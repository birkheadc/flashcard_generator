from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..audio.waveform import WaveformData
from . import theme

# Pixel tolerance for grabbing the edge of the current selection or an
# existing clip region to resize it, rather than starting something new.
_EDGE_HIT_PIXELS = 6.0

# Dragging an edge can't collapse a region to zero (or negative) width.
_MIN_REGION_DURATION = 0.05

# Bars are drawn at a fixed on-screen pitch rather than one line per pixel.
# Zooming widens the widget (see WaveformView), which fits more of these
# fixed-width bars across the same total duration — so zooming in raises
# how much of the timeline each bar covers on-screen (fidelity), rather
# than stretching existing bars wider.
_BAR_WIDTH = 3.0
_BAR_GAP = 2.0
_BAR_PITCH = _BAR_WIDTH + _BAR_GAP

# Keeps near-silent stretches visible as a thin bar instead of vanishing.
_MIN_BAR_HALF_HEIGHT = 1.5

# Floor for the widget's on-screen height, independent of however tall a
# previous _relayout_content() pass happened to make it — see WaveformView
# (waveform_view.py), which reads this rather than the widget's current
# minimumHeight() to size it against the scroll viewport, since setFixedSize
# there mutates minimumHeight() too and would otherwise ratchet it upward.
MIN_HEIGHT = 150

# Blank space reserved at each edge of the track so the ruler's first and
# last tick labels (see TimeRulerWidget in waveform_view.py) have room to
# render in full, rather than being centered on the very edge pixel and
# clipped off the widget. WaveformWidget and TimeRulerWidget are always the
# same width and must agree on this inset so a given x still means the same
# point in time in both.
EDGE_MARGIN = 28.0


def time_to_x(t: float, duration_seconds: float, width: float, margin: float = EDGE_MARGIN) -> float:
    if duration_seconds <= 0:
        return 0.0
    usable_width = max(width - 2 * margin, 0.0)
    fraction = min(max(t / duration_seconds, 0.0), 1.0)
    return margin + fraction * usable_width


def x_to_time(x: float, duration_seconds: float, width: float, margin: float = EDGE_MARGIN) -> float:
    if duration_seconds <= 0 or width <= 0:
        return 0.0
    usable_width = max(width - 2 * margin, 0.0)
    if usable_width <= 0:
        return 0.0
    fraction = min(max((x - margin) / usable_width, 0.0), 1.0)
    return fraction * duration_seconds


class WaveformWidget(QWidget):
    """Paints fixed-width amplitude bars for a loaded WaveformData, a
    playhead, existing clip regions, and a pending selection.

    - Plain click/drag: seek (emits seek_requested).
    - Shift+click+drag: select a region (emits selection_changed).
    - Click/drag the edge of the current selection or an existing clip
      region: resize it in place (emits selection_changed live, or
      clip_region_edited once the drag is released).
    """

    seek_requested = Signal(float)
    selection_changed = Signal(object)  # tuple[float, float] | None
    clip_region_edited = Signal(int, float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data: WaveformData | None = None
        self._position_seconds = 0.0
        self._duration_seconds = 0.0
        self._selection: tuple[float, float] | None = None
        self._clip_regions: list[tuple[float, float]] = []
        self._drag_mode: str | None = None  # "seek" | "select" | "edit_selection" | "edit_clip"
        self._selection_anchor: float | None = None
        self._editing_index: int | None = None
        self._editing_edge: str | None = None  # "start" | "end"
        self.setMinimumHeight(MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_waveform(self, data: WaveformData | None) -> None:
        self._data = data
        self._position_seconds = 0.0
        self._duration_seconds = data.duration_seconds if data else 0.0
        self._clip_regions = []
        self._drag_mode = None
        self._selection_anchor = None
        self._editing_index = None
        self._editing_edge = None
        self._set_selection(None)
        self.update()

    def set_duration(self, seconds: float) -> None:
        # Authoritative duration comes from the media player once it opens
        # the file, which can differ slightly from soundfile's estimate.
        self._duration_seconds = seconds
        self.update()

    def set_position(self, seconds: float) -> None:
        self._position_seconds = seconds
        self.update()

    # -- selection ----------------------------------------------------------

    @property
    def selection(self) -> tuple[float, float] | None:
        return self._selection

    def set_selection(self, start: float, end: float) -> None:
        lo, hi = (start, end) if start <= end else (end, start)
        lo = min(max(lo, 0.0), self._duration_seconds)
        hi = min(max(hi, 0.0), self._duration_seconds)
        self._set_selection((lo, hi) if hi > lo else None)

    def clear_selection(self) -> None:
        self._set_selection(None)

    def _set_selection(self, selection: tuple[float, float] | None) -> None:
        self._selection = selection
        self.selection_changed.emit(selection)
        self.update()

    # -- clip regions (visualization + edge-editing) -------------------------

    def set_clip_regions(self, regions: list[tuple[float, float]]) -> None:
        self._clip_regions = list(regions)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.PAPER_0))

        width = self.width()
        height = self.height()
        mid_y = height / 2

        if self._duration_seconds > 0 and width > 0:
            for start, end in self._clip_regions:
                self._fill_time_range(painter, start, end, height, QColor(15, 92, 87, 35))
            if self._selection is not None:
                self._fill_time_range(
                    painter, self._selection[0], self._selection[1], height, QColor(200, 85, 61, 45)
                )

        track_left = EDGE_MARGIN
        track_right = max(width - EDGE_MARGIN, track_left)
        painter.setPen(QPen(QColor(theme.INK_5)))
        painter.drawLine(int(track_left), int(mid_y), int(track_right), int(mid_y))

        usable_width = track_right - track_left
        if self._data is not None and width > 0 and usable_width > 0:
            peaks_min = self._data.peaks_min
            peaks_max = self._data.peaks_max
            num_columns = len(peaks_min)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.ACCENT))
            # Only draw the bars Qt actually asked us to repaint. At high
            # zoom this widget can be far wider than the visible viewport, so
            # painting the full width on every playhead update would scale
            # with zoom instead of with what's on screen.
            dirty = event.rect()
            first_bar = max(0, int((dirty.left() - track_left) // _BAR_PITCH))
            last_bar = min(
                int(usable_width // _BAR_PITCH), int((dirty.right() - track_left) // _BAR_PITCH)
            )
            for bar in range(first_bar, last_bar + 1):
                x = track_left + bar * _BAR_PITCH
                # Each bar's height is the average amplitude of the slice of
                # source columns its fixed-width footprint covers, rather
                # than a single column sampled at its position. That's what
                # lets zooming in reveal more of the underlying detail: the
                # same bar width now maps to a narrower, less-averaged slice.
                col_start = min(int((x - track_left) / usable_width * num_columns), num_columns - 1)
                col_end = max(
                    col_start + 1,
                    min(int((x + _BAR_PITCH - track_left) / usable_width * num_columns), num_columns),
                )
                amplitude = float((peaks_max[col_start:col_end] - peaks_min[col_start:col_end]).mean()) / 2.0
                half_height = max(amplitude * mid_y, _MIN_BAR_HALF_HEIGHT)
                painter.drawRoundedRect(
                    QRectF(x, mid_y - half_height, _BAR_WIDTH, half_height * 2), 1.0, 1.0
                )
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._duration_seconds > 0 and width > 0 and self._data is not None:
            playhead_x = int(self._x_at_time(self._position_seconds))
            painter.setPen(QPen(QColor(theme.INK_0), 2))
            painter.drawLine(playhead_x, 0, playhead_x, height)

        painter.end()

    def _fill_time_range(
        self, painter: QPainter, start: float, end: float, height: int, color: QColor
    ) -> None:
        x_start = int(self._x_at_time(start))
        x_end = int(self._x_at_time(end))
        painter.fillRect(x_start, 0, max(1, x_end - x_start), height, color)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        x = event.position().x()
        hit = self._hit_test_edge(x)
        if hit is not None:
            kind, index, edge = hit
            self._drag_mode = "edit_selection" if kind == "selection" else "edit_clip"
            self._editing_index = index
            self._editing_edge = edge
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._drag_mode = "select"
            t = self._time_at_x(x)
            self._selection_anchor = t
            self.set_selection(t, t)
            return
        self._drag_mode = "seek"
        self._seek_to_x(x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = event.position().x()
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self._update_hover_cursor(x)
            return
        if self._drag_mode == "edit_selection":
            self._drag_selection_edge(x)
        elif self._drag_mode == "edit_clip":
            self._drag_clip_edge(x)
        elif self._drag_mode == "select" and self._selection_anchor is not None:
            self.set_selection(self._selection_anchor, self._time_at_x(x))
        elif self._drag_mode == "seek":
            self._seek_to_x(x)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode == "edit_clip" and self._editing_index is not None:
            start, end = self._clip_regions[self._editing_index]
            self.clip_region_edited.emit(self._editing_index, start, end)
        self._drag_mode = None
        self._selection_anchor = None
        self._editing_index = None
        self._editing_edge = None

    def _drag_selection_edge(self, x: float) -> None:
        if self._selection is None:
            return
        t = self._time_at_x(x)
        start, end = self._selection
        if self._editing_edge == "start":
            self.set_selection(t, end)
        else:
            self.set_selection(start, t)

    def _drag_clip_edge(self, x: float) -> None:
        if self._editing_index is None:
            return
        t = self._time_at_x(x)
        start, end = self._clip_regions[self._editing_index]
        if self._editing_edge == "start":
            start = min(max(t, 0.0), end - _MIN_REGION_DURATION)
        else:
            end = max(min(t, self._duration_seconds), start + _MIN_REGION_DURATION)
        self._clip_regions[self._editing_index] = (start, end)
        self.update()

    def _hit_test_edge(self, x: float) -> tuple[str, int | None, str] | None:
        if self._duration_seconds <= 0 or self.width() <= 0:
            return None
        if self._selection is not None:
            for edge, t in (("start", self._selection[0]), ("end", self._selection[1])):
                if abs(self._x_at_time(t) - x) <= _EDGE_HIT_PIXELS:
                    return ("selection", None, edge)
        for i, (start, end) in enumerate(self._clip_regions):
            for edge, t in (("start", start), ("end", end)):
                if abs(self._x_at_time(t) - x) <= _EDGE_HIT_PIXELS:
                    return ("clip", i, edge)
        return None

    def _update_hover_cursor(self, x: float) -> None:
        hit = self._hit_test_edge(x)
        self.setCursor(
            Qt.CursorShape.SizeHorCursor if hit is not None else Qt.CursorShape.ArrowCursor
        )

    def _time_at_x(self, x: float) -> float:
        return x_to_time(x, self._duration_seconds, self.width())

    def _x_at_time(self, t: float) -> float:
        return time_to_x(t, self._duration_seconds, self.width())

    def _seek_to_x(self, x: float) -> None:
        if self._duration_seconds <= 0 or self.width() <= 0:
            return
        self.seek_requested.emit(self._time_at_x(x))
