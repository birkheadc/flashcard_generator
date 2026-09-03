from __future__ import annotations

import numpy as np
import pytest

from flashcard_generator.audio.waveform import WaveformData
from flashcard_generator.ui.waveform_widget import WaveformWidget


def _make_data(duration: float = 10.0, num_columns: int = 100) -> WaveformData:
    peaks_min = np.full(num_columns, -0.5, dtype=np.float32)
    peaks_max = np.full(num_columns, 0.5, dtype=np.float32)
    return WaveformData(peaks_min, peaks_max, duration, 44100)


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
