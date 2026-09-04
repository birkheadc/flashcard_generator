from __future__ import annotations

import pytest

from flashcard_generator.clips import Clip, ClipList


def test_clip_rejects_non_positive_duration():
    with pytest.raises(ValueError):
        Clip(start_seconds=5.0, end_seconds=5.0)
    with pytest.raises(ValueError):
        Clip(start_seconds=5.0, end_seconds=4.0)


def test_clip_duration_seconds():
    clip = Clip(start_seconds=2.0, end_seconds=5.5)
    assert clip.duration_seconds == pytest.approx(3.5)


def test_add_appends_and_returns_index():
    clips = ClipList()
    first = clips.add(Clip(0.0, 1.0))
    second = clips.add(Clip(1.0, 2.0))

    assert first == 0
    assert second == 1
    assert len(clips) == 2
    assert clips[0].start_seconds == 0.0
    assert clips[1].start_seconds == 1.0


def test_remove_deletes_by_index():
    clips = ClipList()
    clips.add(Clip(0.0, 1.0))
    clips.add(Clip(1.0, 2.0))

    clips.remove(0)

    assert len(clips) == 1
    assert clips[0].start_seconds == 1.0


def test_move_reorders_clips():
    clips = ClipList()
    clips.add(Clip(0.0, 1.0))
    clips.add(Clip(1.0, 2.0))
    clips.add(Clip(2.0, 3.0))

    clips.move(2, 0)

    assert [c.start_seconds for c in clips] == [2.0, 0.0, 1.0]


def test_clear_empties_the_list():
    clips = ClipList()
    clips.add(Clip(0.0, 1.0))

    clips.clear()

    assert len(clips) == 0


def test_regions_returns_start_end_tuples():
    clips = ClipList()
    clips.add(Clip(0.0, 1.5))
    clips.add(Clip(2.0, 3.0))

    assert clips.regions() == [(0.0, 1.5), (2.0, 3.0)]


def test_iteration_and_len():
    clips = ClipList()
    clips.add(Clip(0.0, 1.0))
    clips.add(Clip(1.0, 2.0))

    assert len(clips) == 2
    assert [c.end_seconds for c in clips] == [1.0, 2.0]
