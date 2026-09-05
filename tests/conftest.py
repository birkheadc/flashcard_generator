from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf


@pytest.fixture
def session_path(tmp_path):
    """Where a test's autosaved session goes, isolated from the real one."""
    return tmp_path / "session.json"


@pytest.fixture(autouse=True)
def _isolate_default_session_path(session_path, monkeypatch):
    """Point MainWindow()'s default session path at a per-test tmp file.

    Without this, every MainWindow() created in a test would read/write the
    developer's real ~/.flashcard_generator/session.json.
    """
    monkeypatch.setattr(
        "flashcard_generator.ui.main_window.default_session_path", lambda: session_path
    )


@pytest.fixture
def template_library_path(tmp_path):
    """Where a test's saved-template library goes, isolated from the real
    one (ROADMAP.md Phase 5.5)."""
    return tmp_path / "templates.json"


@pytest.fixture(autouse=True)
def _isolate_default_template_library_path(template_library_path, monkeypatch):
    """Point MainWindow()'s default template library path at a per-test
    tmp file — same reasoning as `_isolate_default_session_path` above."""
    monkeypatch.setattr(
        "flashcard_generator.ui.main_window.default_template_library_path",
        lambda: template_library_path,
    )


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
