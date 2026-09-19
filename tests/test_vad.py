from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from flashcard_generator.clips import Clip
from flashcard_generator.vad import suggest_snippets

REAL_SPEECH_SAMPLE = Path(__file__).parent / "fixtures" / "speech_sample.wav"


def test_suggest_snippets_finds_speech_in_a_real_recording():
    clips = suggest_snippets(str(REAL_SPEECH_SAMPLE))

    assert len(clips) > 0
    duration = sf.info(str(REAL_SPEECH_SAMPLE)).duration
    for clip in clips:
        assert isinstance(clip, Clip)
        assert 0.0 <= clip.start_seconds < clip.end_seconds <= duration


def test_suggest_snippets_returns_nothing_for_silence(tmp_path):
    silence = np.zeros(16_000 * 5, dtype=np.float32)
    path = tmp_path / "silence.wav"
    sf.write(str(path), silence, 16_000)

    assert suggest_snippets(str(path)) == []


def test_suggest_snippets_resamples_non_16k_audio(wav_file):
    # A pure sine tone isn't speech, so this doesn't assert on detection —
    # it's here to confirm the 44.1kHz -> 16kHz resample path (real-world
    # recordings are essentially never natively 16kHz) doesn't raise.
    path = wav_file(duration_seconds=3.0, sample_rate=44_100)

    suggest_snippets(path)  # must not raise
