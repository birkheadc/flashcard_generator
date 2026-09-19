from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

from .pcm import PcmTrack, decode_pcm

# How often we top up the sink's buffer. Short enough that the buffer never
# runs dry between ticks, long enough not to burn CPU on a hot loop — see
# _BUFFER_MS below, which needs to comfortably exceed this.
_PUMP_INTERVAL_MS = 30

# Size of QAudioSink's internal buffer. Also bounds how far the write
# pointer can run ahead of what's actually audible — see _update_position.
_BUFFER_MS = 200

# Short linear amplitude ramp (silence -> full volume) applied to the very
# first real audio frames pushed after every restart (first play, resume,
# seek, loop-restart). Targets the actual likely cause of the startup/seek
# crackle: the waveform jumping discontinuously from 0 straight to
# whatever sample the clip happens to start on — an instantaneous jump in
# speaker position that clicks regardless of how much silence precedes
# it, since the same hard edge just happens later instead of disappearing.
# A leading silence buffer was tried first on the theory that the backend
# needed warm-up time before real content arrived; hands-on hardware
# testing (cranked up to 10s with zero audible difference) ruled that
# theory out, so it's been removed rather than left in as dead weight.
_FADE_IN_MS = 8

_SAMPLE_FORMAT = QAudioFormat.SampleFormat.Int16
_BYTES_PER_SAMPLE = 2
_CHANNELS = 2
_FRAME_SIZE = _BYTES_PER_SAMPLE * _CHANNELS


def _apply_fade_in(chunk: np.ndarray, start_frame: int, fade_frames: int) -> np.ndarray:
    """Return a copy of `chunk` with a linear 0->1 ramp applied over the
    frames from `start_frame` to `fade_frames` into the fade (chunk itself
    may start anywhere within, or entirely past, that range)."""
    n = chunk.shape[0]
    ramp = np.minimum(1.0, (start_frame + np.arange(n)) / fade_frames).astype(np.float32)
    return (chunk.astype(np.float32) * ramp[:, None]).astype(np.int16)


class PlaybackEngine(QObject):
    """Raw-PCM playback via QAudioSink, replacing QMediaPlayer/QAudioOutput.

    The whole file is decoded to PCM once at load() (see pcm.py) and kept
    in memory, so nothing in the real-time path below ever touches disk.

    Looping and seeking are both just arithmetic on `_write_pos`, an index
    we own into that in-memory buffer — there's no async "seek the decoder
    and hope it lands before play() fires" step for either of them, which
    is what made QMediaPlayer prone to popping/clipping on Windows. A
    QTimer (`_pump`) periodically pushes more PCM into the sink; loop
    wrap-around happens by splicing the fill within a single tick rather
    than by stopping and restarting anything.

    `positionChanged` is a *cosmetic* estimate (write pointer minus what's
    still sitting unplayed in the sink's buffer, see _update_position) —
    unlike the old design, nothing about correctness depends on it being
    exact, only the UI cursor's smoothness.
    """

    positionChanged = Signal(float)  # seconds
    durationChanged = Signal(float)  # seconds
    playingChanged = Signal(bool)
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._track: PcmTrack | None = None
        self._format: QAudioFormat | None = None
        self._device = None
        self._sink: QAudioSink | None = None
        self._io = None
        self._playing = False

        # Raw index (frames) of the next sample we'll push into the sink.
        # Wraps back to the loop start on a repeating loop.
        self._write_pos = 0
        self._loop: tuple[int, int] | None = None  # (start_frame, end_frame)
        self._loop_repeats = True
        self._reached_end = False

        # Bookkeeping for _update_position: how many frames we've pushed,
        # and where playback resumed, since the last flush (load/seek/
        # start_loop). Frames pushed only ever grows forward even when
        # `_write_pos` wraps for a loop; see _update_position for how the
        # two combine into a track-relative "audible now" position.
        self._pushed_since_epoch = 0
        self._epoch_start_pos = 0

        self._timer = QTimer(self)
        self._timer.setInterval(_PUMP_INTERVAL_MS)
        self._timer.timeout.connect(self._pump)

    # -- loading --------------------------------------------------------

    def load(self, path: str) -> None:
        self._teardown()

        try:
            track = decode_pcm(path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self.errorOccurred.emit(str(exc))
            return

        fmt = QAudioFormat()
        fmt.setSampleRate(track.sample_rate)
        fmt.setChannelCount(_CHANNELS)
        fmt.setSampleFormat(_SAMPLE_FORMAT)

        device = QMediaDevices.defaultAudioOutput()
        if device.isNull() or not device.isFormatSupported(fmt):
            self.errorOccurred.emit(
                f"The system audio device doesn't support {track.sample_rate} Hz playback."
            )
            return

        # Deliberately doesn't construct QAudioSink yet — only validates
        # that the device *can* handle this format. Opening the device is
        # deferred to _start_output(), called from play()/start_loop(), so
        # a load() (or a seek() before ever pressing play) doesn't touch
        # real audio hardware at all. That's not just laziness: eagerly
        # constructing/starting a QAudioSink here was confirmed to have an
        # observable side effect on Qt's focus handling under the
        # offscreen test platform, breaking unrelated UI tests that merely
        # loaded a file without ever intending to play it.
        self._track = track
        self._format = fmt
        self._device = device
        self._write_pos = 0
        self._epoch_start_pos = 0
        self._pushed_since_epoch = 0

        self.durationChanged.emit(track.frame_count / track.sample_rate)
        self._update_position()

    def _teardown(self) -> None:
        self._timer.stop()
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        self._sink = None
        self._io = None
        self._track = None
        self._format = None
        self._device = None
        self._write_pos = 0
        self._loop = None
        self._loop_repeats = True
        self._reached_end = False
        self._playing = False

    # -- transport --------------------------------------------------------

    def play(self) -> None:
        if self._track is None or self._playing:
            return
        # Always a full restart from the current position, whether this is
        # the very first play() for this file or a resume from pause().
        # sink.resume() was tried for the latter first and looked correct
        # at the Qt state-machine level (state transitions to ActiveState
        # fine), but real hardware testing showed it doesn't reliably
        # restart actual audible output. _write_pos is untouched by
        # pause(), so restarting from it here resumes from exactly where
        # playback left off.
        self._start_output()
        self._set_playing(True)

    def pause(self) -> None:
        if not self._playing:
            return
        self._timer.stop()
        if self._sink is not None and self._sink.state() != QAudio.State.StoppedState:
            # _write_pos runs up to _BUFFER_MS ahead of what's actually
            # audible (that's the point of buffering ahead of the
            # hardware) — pull it back to what's actually been heard so
            # far before suspending, or resuming later would restart from
            # the write pointer and skip forward by however much was
            # still buffered-but-unheard at the moment of pause. seek()
            # doesn't need this: it always sets an intentional target
            # position directly, overriding whatever was buffered.
            self._write_pos = self._audible_position_frame()
            self._sink.suspend()
        self._set_playing(False)

    def toggle(self) -> None:
        self.pause() if self._playing else self.play()

    def seek(self, seconds: float) -> None:
        if self._track is None:
            return
        # Clear any active loop ourselves rather than trusting the caller
        # to have called stop_loop() first — otherwise the very next pump
        # tick would see the new position past the (still-set) loop end
        # and immediately wrap back to it.
        self._loop = None
        self._loop_repeats = True
        self._reached_end = False
        self._flush_to(self._clamp_frame(seconds))
        self._update_position()

    def start_loop(self, start_seconds: float, end_seconds: float, *, repeat: bool = True) -> None:
        if self._track is None:
            return
        start_frame = self._clamp_frame(start_seconds)
        end_frame = self._clamp_frame(end_seconds)
        self._loop = (start_frame, end_frame)
        self._loop_repeats = repeat
        self._reached_end = False
        self._flush_to(start_frame)
        self._update_position()
        self.play()

    def set_loop_bounds(self, start_seconds: float, end_seconds: float) -> None:
        """Adjust the active loop's bounds without restarting playback —
        used when the clip currently being previewed has its edges dragged
        live on the waveform. Just moves where _fill wraps; nothing to
        flush since we're not jumping the write pointer."""
        if self._track is None or self._loop is None:
            return
        self._loop = (self._clamp_frame(start_seconds), self._clamp_frame(end_seconds))

    def stop_loop(self) -> None:
        if self._loop is None:
            return
        # pause() first, while _loop is still set — its position
        # correction (_audible_position_frame) needs the loop's bounds to
        # clamp against; clearing them first would let it clamp against
        # the whole track instead and land _write_pos somewhere way past
        # the loop, especially after several wraps.
        self.pause()
        self._loop = None
        self._loop_repeats = True

    def position(self) -> float:
        if self._track is None:
            return 0.0
        return self._write_pos / self._track.sample_rate

    def is_playing(self) -> bool:
        return self._playing

    # -- internals --------------------------------------------------------

    def _clamp_frame(self, seconds: float) -> int:
        assert self._track is not None
        frame = int(round(seconds * self._track.sample_rate))
        return max(0, min(frame, self._track.frame_count))

    def _flush_to(self, frame: int) -> None:
        """Jump the write pointer to `frame`. If output has already been
        started at least once, restarts it there immediately (via
        _start_output) so stale buffered audio can't play after a seek/
        loop restart; otherwise just updates the position bookkeeping —
        _start_output sets the epoch itself once a later play() actually
        opens the device.

        Only restarts if `_io is not None` (already started once) —
        otherwise there's nothing buffered to flush, and opening the
        device here would happen on a mere load()/seek(), before the user
        ever presses play. That's not just wasteful: it's an observable
        side effect (confirmed to disturb Qt focus handling under the
        offscreen test platform) for something that should be lazy."""
        self._write_pos = frame
        if self._io is not None:
            self._start_output()
        else:
            self._epoch_start_pos = frame
            self._pushed_since_epoch = 0

    def _start_output(self) -> None:
        """(Re)start real audio output from the current _write_pos — the
        one place that opens the device. Replaces the QAudioSink outright
        (stop the old one, construct a fresh one) rather than reset()+
        start()-ing the existing sink: reset()+start() was tried first and,
        per hands-on hardware testing, the startup crackle came back on
        every restart even with a fade-in applied on top of it (see
        _FADE_IN_MS) — the fade only ever helped on a genuinely fresh
        sink's first-ever start, which points at state that reset()
        doesn't actually clear (Qt-side or WASAPI-side, we have no
        visibility into which) but a brand new sink object can't carry
        over. The first real chunk _fill pushes afterward still gets the
        fade-in regardless, since a discontinuity in the content is a
        separate, real concern from whatever this addresses.

        Used by play() (first-ever start, and resuming after pause — see
        play()'s comment on why resume() isn't used) and by _flush_to
        (seek/loop restart while already playing)."""
        if self._format is None or self._device is None:
            return
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        self._sink = QAudioSink(self._device, self._format, self)
        self._sink.setBufferSize(self._format.bytesForDuration(_BUFFER_MS * 1000))
        self._io = self._sink.start()
        self._epoch_start_pos = self._write_pos
        self._pushed_since_epoch = 0

    def _set_playing(self, playing: bool) -> None:
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            self._timer.start()
        else:
            self._timer.stop()
        self.playingChanged.emit(playing)

    def _pump(self) -> None:
        if self._track is None or self._sink is None or self._io is None:
            return
        if not self._reached_end:
            frames_free = self._sink.framesFree()
            if frames_free > 0:
                self._write_pos = self._fill(frames_free)
        self._update_position()

    def _fade_in_frame_count(self) -> int:
        if self._track is None:
            return 0
        return max(1, int(_FADE_IN_MS * self._track.sample_rate / 1000))

    def _fill(self, frames_free: int) -> int:
        assert self._track is not None
        samples = self._track.samples
        total = self._track.frame_count
        pos = self._write_pos
        remaining = frames_free
        fade_frames = self._fade_in_frame_count()
        while remaining > 0:
            boundary = min(self._loop[1], total) if self._loop is not None else total
            if pos >= boundary:
                if self._loop is not None and self._loop_repeats:
                    pos = self._loop[0]
                    continue
                self._reached_end = True
                break
            chunk_len = min(remaining, boundary - pos)
            chunk = samples[pos : pos + chunk_len]
            if self._pushed_since_epoch < fade_frames:
                chunk = _apply_fade_in(chunk, self._pushed_since_epoch, fade_frames)
            written = self._io.write(chunk.tobytes()) // _FRAME_SIZE
            pos += written
            self._pushed_since_epoch += written
            remaining -= written
            if written < chunk_len:
                break
        return pos

    def _audible_position_frame(self) -> int:
        """Best estimate of what's actually reached the speakers right
        now: the write pointer minus whatever's still sitting in the
        sink's buffer, unplayed. Used both for the cosmetic UI position
        (_update_position) and, critically, to correct _write_pos back to
        reality before pause() suspends output — see pause()'s comment."""
        if self._track is None:
            return 0
        if self._sink is None or self._io is None:
            # No sink yet, or one that's never been started (loaded/seeked
            # but not yet played) — nothing's buffered.
            buffered_frames = 0
        else:
            buffered_bytes = max(0, self._sink.bufferSize() - self._sink.bytesFree())
            buffered_frames = buffered_bytes // _FRAME_SIZE
        audible_since_epoch = max(0, self._pushed_since_epoch - buffered_frames)
        boundary = self._loop[1] if self._loop is not None else self._track.frame_count

        if self._loop is not None and not self._reached_end:
            # Still actively repeating: wrap the audible estimate the same
            # way _fill wraps the write pointer.
            loop_len = max(1, boundary - self._loop[0])
            return self._epoch_start_pos + (audible_since_epoch % loop_len)
        # Not looping anymore (or never was): a modulo here would wrap
        # back to 0 exactly as we reach the boundary, so the "reached end"
        # check in _update_position would never fire. Clamp linearly
        # instead.
        return min(boundary, self._epoch_start_pos + audible_since_epoch)

    def _update_position(self) -> None:
        if self._track is None:
            return
        audible_pos = self._audible_position_frame()
        boundary = self._loop[1] if self._loop is not None else self._track.frame_count

        self.positionChanged.emit(audible_pos / self._track.sample_rate)

        if self._reached_end and audible_pos >= boundary:
            self._finish_playback()

    def _finish_playback(self) -> None:
        # pause() first, while _loop/_reached_end are still set — see
        # stop_loop()'s comment on why the order matters here.
        self.pause()
        self._loop = None
        self._loop_repeats = True
        self._reached_end = False
