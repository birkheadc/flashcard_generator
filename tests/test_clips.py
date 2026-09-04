from __future__ import annotations

import pytest

from flashcard_generator.clips import Clip


def test_clip_rejects_non_positive_duration():
    with pytest.raises(ValueError):
        Clip(start_seconds=5.0, end_seconds=5.0)
    with pytest.raises(ValueError):
        Clip(start_seconds=5.0, end_seconds=4.0)


def test_clip_duration_seconds():
    clip = Clip(start_seconds=2.0, end_seconds=5.5)
    assert clip.duration_seconds == pytest.approx(3.5)
