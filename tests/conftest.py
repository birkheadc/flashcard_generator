from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf


@pytest.fixture
def wav_file(tmp_path):
    """Writes a synthetic sine-wave WAV file and returns its path."""

    def _make(
        duration_seconds: float = 1.0,
        sample_rate: int = 44100,
        frequency: float = 440.0,
        channels: int = 1,
        amplitude: float = 0.5,
    ) -> str:
        t = np.arange(int(sample_rate * duration_seconds), dtype=np.float32) / sample_rate
        tone = (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
        if channels > 1:
            tone = np.tile(tone[:, None], (1, channels))
        path = tmp_path / "test.wav"
        sf.write(str(path), tone, sample_rate)
        return str(path)

    return _make
