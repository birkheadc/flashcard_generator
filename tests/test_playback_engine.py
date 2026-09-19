from __future__ import annotations

import pytest

from flashcard_generator.audio.playback_engine import PlaybackEngine


@pytest.fixture
def engine(qtbot):
    eng = PlaybackEngine()
    yield eng
    eng._teardown()


def test_load_reports_duration_and_starts_at_zero(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=2.0)
    durations = []
    engine.durationChanged.connect(durations.append)

    engine.load(path)

    assert durations and durations[0] == pytest.approx(2.0, abs=0.05)
    assert engine.position() == pytest.approx(0.0, abs=0.01)
    assert not engine.is_playing()


def test_play_advances_position_in_real_time(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=2.0)
    engine.load(path)

    engine.play()

    assert engine.is_playing()
    qtbot.waitUntil(lambda: engine.position() > 0, timeout=3000)


def test_pause_freezes_position(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=2.0)
    engine.load(path)
    engine.play()
    qtbot.waitUntil(lambda: engine.position() > 0, timeout=3000)

    engine.pause()
    assert not engine.is_playing()
    frozen = engine.position()
    qtbot.wait(100)
    assert engine.position() == pytest.approx(frozen, abs=0.005)


def test_pause_pulls_write_pos_back_to_audible_position(qtbot, engine, wav_file):
    # Regression test: _write_pos runs ahead of what's actually audible by
    # up to the sink's buffer size (that's the point of buffering ahead).
    # pause() used to leave it untouched, so a later resume would restart
    # from the write-ahead position and audibly skip forward by however
    # much was still buffered-but-unheard at the moment of pause.
    path = wav_file(duration_seconds=2.0)
    engine.load(path)
    engine.play()
    qtbot.waitUntil(lambda: engine.position() > 0, timeout=3000)
    write_pos_before_pause = engine._write_pos

    engine.pause()

    assert engine._write_pos < write_pos_before_pause


def test_stop_loop_after_many_wraps_leaves_write_pos_within_loop(qtbot, engine, wav_file):
    # Regression test: stop_loop() used to clear _loop before calling
    # pause(), so pause()'s position correction (_audible_position_frame)
    # would clamp against the whole track instead of the loop's own
    # bounds, potentially landing _write_pos far past the loop after it
    # had wrapped several times.
    path = wav_file(duration_seconds=2.0)
    engine.load(path)
    engine.start_loop(0.0, 0.05, repeat=True)
    qtbot.wait(300)  # let it wrap several times over

    engine.stop_loop()

    assert engine._write_pos <= engine._clamp_frame(0.05)


def test_resuming_after_pause_reopens_the_output_channel(qtbot, engine, wav_file):
    # Regression test: play() used to call sink.resume() to come out of
    # pause, which looked correct at the Qt state-machine level (state
    # transitions to ActiveState fine) but was confirmed on real hardware
    # not to reliably restart actual audible output — the user had to
    # manually seek to get sound back. Fixed by always doing a full
    # reset()+start() restart instead (the same mechanism seek() already
    # relies on, confirmed working). start() returns a fresh QIODevice
    # each call, so _io changing identity here is what actually
    # distinguishes "restarted" from "merely resumed" — this test can't
    # observe real audio, but it can observe that the fix's mechanism is
    # actually being exercised.
    path = wav_file(duration_seconds=2.0)
    engine.load(path)
    engine.play()
    qtbot.waitUntil(lambda: engine.position() > 0, timeout=3000)
    io_before_pause = engine._io

    engine.pause()
    engine.play()

    assert engine._io is not None
    assert engine._io is not io_before_pause
    assert engine.is_playing()


def test_seek_updates_position_synchronously(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=2.0)
    engine.load(path)

    engine.seek(1.0)

    assert engine.position() == pytest.approx(1.0, abs=0.01)


def test_seek_past_end_clamps_to_track_length(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=1.0)
    engine.load(path)

    engine.seek(5.0)

    assert engine.position() == pytest.approx(1.0, abs=0.01)


def test_repeating_loop_wraps_instead_of_running_past_end(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=10.0)
    engine.load(path)

    engine.start_loop(1.0, 2.0, repeat=True)
    assert engine.is_playing()

    # Force the write pointer past the loop end the way several real ticks
    # would, and pump once directly (the same style the old QMediaPlayer
    # tests used to inject a synthetic positionChanged) to check the wrap
    # splice lands back at the loop start rather than continuing past it.
    engine._write_pos = engine._clamp_frame(2.5)
    engine._pump()

    assert engine.is_playing()
    assert engine.position() < 2.0
    assert engine._write_pos > engine._clamp_frame(1.0)


def test_non_repeating_loop_stops_at_end_instead_of_wrapping(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=2.0)
    engine.load(path)

    engine.start_loop(0.0, 0.05, repeat=False)
    assert engine.is_playing()

    qtbot.waitUntil(lambda: not engine.is_playing(), timeout=3000)
    assert engine._loop is None


def test_stop_loop_pauses_and_clears_loop_range(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=10.0)
    engine.load(path)
    engine.start_loop(1.0, 2.0, repeat=True)
    qtbot.waitUntil(lambda: engine.position() > 0, timeout=3000)

    engine.stop_loop()

    assert not engine.is_playing()
    assert engine._loop is None


def test_seek_clears_any_active_loop(qtbot, engine, wav_file):
    path = wav_file(duration_seconds=10.0)
    engine.load(path)
    engine.start_loop(1.0, 2.0, repeat=True)

    engine.seek(5.0)

    assert engine.position() == pytest.approx(5.0, abs=0.01)
    assert engine._loop is None


def test_load_new_file_tears_down_previous_playback(qtbot, engine, wav_file):
    first = wav_file(duration_seconds=1.0)
    second = wav_file(duration_seconds=3.0)
    engine.load(first)
    engine.play()
    qtbot.waitUntil(lambda: engine.position() > 0, timeout=3000)

    durations = []
    engine.durationChanged.connect(durations.append)
    engine.load(second)

    assert not engine.is_playing()
    assert durations[-1] == pytest.approx(3.0, abs=0.05)


def test_unsupported_sample_rate_reports_error_instead_of_hanging(qtbot, engine, wav_file):
    # 800Hz isn't a rate the real output device can negotiate a QAudioFormat
    # for (confirmed against the actual default device, not assumed) — this
    # must surface as errorOccurred, not raise, and definitely not reach a
    # blocking QMessageBox from inside load() itself.
    path = wav_file(duration_seconds=1.0, sample_rate=800)
    errors = []
    engine.errorOccurred.connect(errors.append)

    engine.load(path)

    assert errors
    assert "800" in errors[0]
    assert engine._track is None


def test_unsupported_extension_reports_error_instead_of_raising(qtbot, engine, tmp_path):
    bogus = tmp_path / "not_audio.wav"
    bogus.write_text("not actually audio")
    errors = []
    engine.errorOccurred.connect(errors.append)

    engine.load(str(bogus))

    assert errors
    assert engine._track is None
