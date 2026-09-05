from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from flashcard_generator.audio.waveform import WaveformData
from flashcard_generator.ui.waveform_widget import WaveformWidget


def _make_data(duration: float = 10.0, num_columns: int = 100) -> WaveformData:
    peaks_min = np.full(num_columns, -0.5, dtype=np.float32)
    peaks_max = np.full(num_columns, 0.5, dtype=np.float32)
    return WaveformData(peaks_min, peaks_max, duration, 44100)


def _mouse_event(
    x: float, buttons: bool = False, shift: bool = False, ctrl: bool = False
) -> QMouseEvent:
    modifiers = Qt.KeyboardModifier.NoModifier
    if shift:
        modifiers |= Qt.KeyboardModifier.ShiftModifier
    if ctrl:
        modifiers |= Qt.KeyboardModifier.ControlModifier
    held = Qt.MouseButton.LeftButton if buttons else Qt.MouseButton.NoButton
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(x, 10),
        QPointF(x, 10),
        Qt.MouseButton.LeftButton,
        held,
        modifiers,
    )


def test_seek_emits_fraction_of_duration(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))

    received = []
    widget.seek_requested.connect(received.append)

    widget._seek_to_x(100)  # click at the horizontal midpoint

    assert len(received) == 1
    assert received[0] == pytest.approx(5.0, abs=0.2)


def test_seek_before_duration_known_does_nothing(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 150)

    received = []
    widget.seek_requested.connect(received.append)
    widget._seek_to_x(100)

    assert received == []


def test_paint_does_not_crash(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(300, 150)
    widget.set_waveform(_make_data())
    widget.set_position(3.0)
    widget.show()

    pixmap = widget.grab()

    assert pixmap.size().width() == 300


def test_paint_with_selection_and_clips_does_not_crash(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(300, 150)
    widget.set_waveform(_make_data())
    widget.set_selection(1.0, 4.0)
    widget.set_clip_regions([(5.0, 7.0)])
    widget.show()

    pixmap = widget.grab()

    assert pixmap.size().width() == 300


def test_set_selection_normalizes_order_and_clamps():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))

    widget.set_selection(6.0, 2.0)
    assert widget.selection == (2.0, 6.0)

    widget.set_selection(-5.0, 50.0)
    assert widget.selection == (0.0, 10.0)


def test_set_selection_zero_width_clears_selection():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))
    widget.set_selection(2.0, 5.0)

    widget.set_selection(4.0, 4.0)

    assert widget.selection is None


def test_selection_changed_emits_on_set_and_clear():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))

    received = []
    widget.selection_changed.connect(received.append)

    widget.set_selection(1.0, 3.0)
    widget.clear_selection()

    assert received == [(1.0, 3.0), None]


def test_drag_select_with_shift_then_release():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))

    received = []
    widget.selection_changed.connect(received.append)

    widget.mousePressEvent(_mouse_event(x=widget._x_at_time(3.0), shift=True))
    widget.mouseMoveEvent(_mouse_event(x=widget._x_at_time(6.0), buttons=True, shift=True))
    widget.mouseReleaseEvent(_mouse_event(x=widget._x_at_time(6.0)))

    assert widget.selection == pytest.approx((3.0, 6.0), abs=0.05)
    assert received[-1] == pytest.approx((3.0, 6.0), abs=0.05)


def test_plain_click_still_seeks_and_does_not_start_selection():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))

    seeks = []
    widget.seek_requested.connect(seeks.append)

    widget.mousePressEvent(_mouse_event(x=100))

    assert seeks == [pytest.approx(5.0, abs=0.2)]
    assert widget.selection is None


def test_new_waveform_resets_selection():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))
    widget.set_selection(1.0, 2.0)
    widget.set_clip_regions([(0.0, 1.0)])

    widget.set_waveform(_make_data(duration=20.0))

    assert widget.selection is None
    assert widget._clip_regions == []


def test_drag_selection_start_edge_resizes_it():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))
    widget.set_selection(3.0, 6.0)

    widget.mousePressEvent(_mouse_event(x=widget._x_at_time(3.0)))  # grab start edge
    assert widget._drag_mode == "edit_selection"

    widget.mouseMoveEvent(_mouse_event(x=widget._x_at_time(1.0), buttons=True))
    widget.mouseReleaseEvent(_mouse_event(x=widget._x_at_time(1.0)))

    assert widget.selection == pytest.approx((1.0, 6.0), abs=0.05)


def test_drag_selection_end_edge_resizes_it():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))
    widget.set_selection(3.0, 6.0)

    widget.mousePressEvent(_mouse_event(x=widget._x_at_time(6.0)))  # grab end edge
    widget.mouseMoveEvent(_mouse_event(x=widget._x_at_time(8.0), buttons=True))
    widget.mouseReleaseEvent(_mouse_event(x=widget._x_at_time(8.0)))

    assert widget.selection == pytest.approx((3.0, 8.0), abs=0.05)


def test_drag_clip_region_edge_emits_clip_region_edited_on_release():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))
    widget.set_clip_regions([(3.0, 6.0)])

    received = []
    widget.clip_region_edited.connect(lambda *args: received.append(args))

    widget.mousePressEvent(_mouse_event(x=widget._x_at_time(6.0)))  # grab clip's end edge
    assert widget._drag_mode == "edit_clip"
    widget.mouseMoveEvent(_mouse_event(x=widget._x_at_time(8.0), buttons=True))

    assert received == []  # not emitted until release
    widget.mouseReleaseEvent(_mouse_event(x=widget._x_at_time(8.0)))

    assert len(received) == 1
    index, start, end = received[0]
    assert index == 0
    assert start == pytest.approx(3.0, abs=0.05)
    assert end == pytest.approx(8.0, abs=0.05)


def test_drag_clip_edge_cannot_cross_the_other_edge():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))
    widget.set_clip_regions([(3.0, 6.0)])

    widget.mousePressEvent(_mouse_event(x=widget._x_at_time(3.0)))  # grab clip's start edge
    widget.mouseMoveEvent(_mouse_event(x=widget._x_at_time(9.0), buttons=True))  # drag past end edge
    widget.mouseReleaseEvent(_mouse_event(x=widget._x_at_time(9.0)))

    start, end = widget._clip_regions[0]
    assert start < end


def test_click_away_from_any_edge_does_not_start_edit():
    widget = WaveformWidget()
    widget.resize(200, 150)
    widget.set_waveform(_make_data(duration=10.0))
    widget.set_clip_regions([(3.0, 6.0)])

    widget.mousePressEvent(_mouse_event(x=90))  # well inside the clip, not on an edge

    assert widget._drag_mode == "seek"
