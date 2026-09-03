from __future__ import annotations

import numpy as np
import pytest

from flashcard_generator.audio.waveform import compute_waveform


def test_compute_waveform_basic_properties(wav_file):
    path = wav_file(duration_seconds=2.0, sample_rate=44100, frequency=440.0)

    data = compute_waveform(path, num_columns=100)

    assert data.sample_rate == 44100
    assert data.duration_seconds == pytest.approx(2.0, abs=0.01)
    assert len(data.peaks_min) == 100
    assert len(data.peaks_max) == 100
    assert np.all(data.peaks_min <= data.peaks_max)
    # 0.5-amplitude sine wave should get close to the full range somewhere.
    assert data.peaks_max.max() > 0.4
    assert data.peaks_min.min() < -0.4


def test_compute_waveform_stereo_is_averaged(wav_file):
    path = wav_file(duration_seconds=1.0, channels=2)

    data = compute_waveform(path, num_columns=50)

    assert len(data.peaks_min) == 50
    assert np.isfinite(data.peaks_min).all()
    assert np.isfinite(data.peaks_max).all()


def test_compute_waveform_missing_file_raises():
    with pytest.raises(Exception):
        compute_waveform("/no/such/file.wav")


def test_compute_waveform_num_columns_exceeds_frames(wav_file):
    # A very short file with more requested columns than audio frames.
    path = wav_file(duration_seconds=0.001, sample_rate=8000)

    data = compute_waveform(path, num_columns=4000)

    assert len(data.peaks_min) == 4000
    assert not np.isnan(data.peaks_min).any()
    assert not np.isnan(data.peaks_max).any()
