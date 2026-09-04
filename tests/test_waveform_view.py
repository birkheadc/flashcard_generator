from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from flashcard_generator.audio.waveform import WaveformData
from flashcard_generator.ui.waveform_view import MAX_ZOOM, MIN_ZOOM, ZOOM_STEP, WaveformView


def _make_data(duration: float = 60.0, num_columns: int = 100) -> WaveformData:
    peaks_min = np.full(num_columns, -0.5, dtype=np.float32)
    peaks_max = np.full(num_columns, 0.5, dtype=np.float32)
    return WaveformData(peaks_min, peaks_max, duration, 44100)


def _wheel_event(x: float, delta_y: int, ctrl: bool = False) -> QWheelEvent:
    modifiers = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    return QWheelEvent(
        QPointF(x, 10),
        QPointF(x, 10),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def _ready_view(qtbot, width: int = 400, height: int = 200) -> WaveformView:
    view = WaveformView()
    qtbot.addWidget(view)
    view.resize(width, height)
    view.show()
    qtbot.waitExposed(view)
    view.set_waveform(_make_data())
    return view


def test_waveform_sized_correctly_when_loaded_before_first_show(qtbot):
    # Mirrors session-restore-on-launch: set_waveform() runs while the
    # widget still has its pre-layout placeholder size, before resize()/
    # show() have ever run, so the viewport width _relayout_content()
    # reads at that point is stale/tiny.
    view = WaveformView()
    qtbot.addWidget(view)

    view.set_waveform(_make_data())

    view.resize(400, 200)
    view.show()
    qtbot.waitExposed(view)
    qtbot.wait(10)

    assert view._waveform.width() == view._scroll_area.viewport().width()
    assert view._waveform.width() > 100
    assert view._content.width() == view._scroll_area.viewport().width()


def test_fit_zoom_content_matches_viewport(qtbot):
    view = _ready_view(qtbot)

    assert view._zoom == MIN_ZOOM
    assert view._content.width() == view._scroll_area.viewport().width()
    assert not view._zoom_out_button.isEnabled()
    assert not view._zoom_fit_button.isEnabled()
    assert view._zoom_in_button.isEnabled()


def test_zoom_in_widens_content_and_enables_zoom_out(qtbot):
    view = _ready_view(qtbot)
    viewport_width = view._scroll_area.viewport().width()

    view._on_zoom_in()

    assert view._zoom == pytest.approx(MIN_ZOOM + ZOOM_STEP)
    assert view._content.width() == pytest.approx(viewport_width * (MIN_ZOOM + ZOOM_STEP), abs=1)
    assert view._waveform.width() == view._content.width()
    assert view._ruler.width() == view._content.width()
    assert view._zoom_out_button.isEnabled()


def test_zoom_fit_resets_after_zooming_in(qtbot):
    view = _ready_view(qtbot)
    viewport_width = view._scroll_area.viewport().width()

    view._on_zoom_in()
    view._on_zoom_in()
    view._on_zoom_fit()

    assert view._zoom == MIN_ZOOM
    assert view._content.width() == viewport_width
    assert not view._zoom_out_button.isEnabled()


def test_zoom_in_clamps_to_max_and_disables_button(qtbot):
    view = _ready_view(qtbot)

    for _ in range(260):  # (MAX_ZOOM - MIN_ZOOM) / ZOOM_STEP, plus headroom
        view._on_zoom_in()

    assert view._zoom == MAX_ZOOM
    assert not view._zoom_in_button.isEnabled()


def test_zoom_out_clamps_to_min(qtbot):
    view = _ready_view(qtbot)

    view._on_zoom_out()

    assert view._zoom == MIN_ZOOM


def test_loading_new_waveform_resets_zoom_and_scroll(qtbot):
    view = _ready_view(qtbot)
    view._on_zoom_in()
    view._on_zoom_in()
    assert view._zoom > MIN_ZOOM

    view.set_waveform(_make_data(duration=10.0))

    assert view._zoom == MIN_ZOOM
    assert view._scroll_area.horizontalScrollBar().value() == 0


def test_seek_from_waveform_forwards_through_view(qtbot):
    view = _ready_view(qtbot)
    received = []
    view.seek_requested.connect(received.append)

    view._waveform._seek_to_x(view._waveform.width() / 2)

    assert len(received) == 1
    assert received[0] == pytest.approx(30.0, abs=1.0)


def test_ruler_paints_without_crashing(qtbot):
    view = _ready_view(qtbot)
    view.set_position(15.0)
    view.show()

    pixmap = view._ruler.grab()

    assert pixmap.size().width() == view._ruler.width()


def test_autoscroll_follows_playhead_when_zoomed_in(qtbot):
    view = _ready_view(qtbot)
    for _ in range(4):
        view._on_zoom_in()
    bar = view._scroll_area.horizontalScrollBar()
    bar.setValue(0)

    view.set_position(55.0)  # near the end of a 60s file, off the left edge

    assert bar.value() > 0


def test_autoscroll_does_nothing_at_fit_zoom(qtbot):
    view = _ready_view(qtbot)
    bar = view._scroll_area.horizontalScrollBar()

    view.set_position(59.0)

    assert bar.value() == 0


def test_ctrl_wheel_zooms_in_and_out(qtbot):
    view = _ready_view(qtbot)

    view._scroll_area.wheelEvent(_wheel_event(x=50, delta_y=120, ctrl=True))
    assert view._zoom == pytest.approx(MIN_ZOOM + ZOOM_STEP)

    view._scroll_area.wheelEvent(_wheel_event(x=50, delta_y=-120, ctrl=True))
    assert view._zoom == pytest.approx(MIN_ZOOM)


def test_selection_changed_forwards_from_inner_widget(qtbot):
    view = _ready_view(qtbot)
    received = []
    view.selection_changed.connect(received.append)

    view._waveform.set_selection(2.0, 5.0)

    assert received == [(2.0, 5.0)]
    assert view.selection == (2.0, 5.0)


def test_clear_selection_delegates_to_inner_widget(qtbot):
    view = _ready_view(qtbot)
    view._waveform.set_selection(2.0, 5.0)

    view.clear_selection()

    assert view.selection is None


def test_clip_region_edited_forwards_from_inner_widget(qtbot):
    view = _ready_view(qtbot)
    view.set_clip_regions([(2.0, 5.0)])
    received = []
    view.clip_region_edited.connect(lambda *args: received.append(args))

    view._waveform.clip_region_edited.emit(0, 2.0, 8.0)

    assert received == [(0, 2.0, 8.0)]


def test_set_clip_regions_delegates_to_inner_widget(qtbot):
    view = _ready_view(qtbot)

    view.set_clip_regions([(1.0, 2.0)])

    assert view._waveform._clip_regions == [(1.0, 2.0)]


def test_plain_vertical_wheel_does_not_pan(qtbot):
    # Spinning a normal mouse wheel (vertical delta only) must NOT shove
    # the timeline sideways — that was surprising, unwanted behavior.
    # Only genuinely horizontal input (see the test below) should pan.
    view = _ready_view(qtbot)
    for _ in range(8):  # enough steps to give the scrollbar plenty of range
        view._on_zoom_in()
    bar = view._scroll_area.horizontalScrollBar()
    bar.setValue(bar.maximum() // 2)
    start = bar.value()

    view._scroll_area.wheelEvent(_wheel_event(x=50, delta_y=-120, ctrl=False))

    assert bar.value() == start


def test_horizontal_wheel_input_pans(qtbot):
    # A horizontal trackpad swipe, or the OS's own shift+wheel convention
    # (which typically arrives as a horizontal delta already) — either
    # way, genuinely horizontal input should pan the timeline.
    view = _ready_view(qtbot)
    for _ in range(8):
        view._on_zoom_in()
    bar = view._scroll_area.horizontalScrollBar()
    bar.setValue(bar.maximum() // 2)
    start = bar.value()

    event = QWheelEvent(
        QPointF(50, 10),
        QPointF(50, 10),
        QPoint(0, 0),
        QPoint(-120, 0),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    view._scroll_area.wheelEvent(event)

    assert bar.value() == start + 120
