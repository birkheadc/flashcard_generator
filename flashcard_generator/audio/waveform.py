from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soundfile as sf

# Fixed resolution the audio file is reduced to on load, so we don't need to
# re-read the source file on every resize or zoom change. The waveform is
# drawn as fixed-width bars that each average a slice of these columns;
# zooming in shrinks the slice a bar covers, revealing more real detail
# instead of stretching pixels. This needs to comfortably exceed the widest
# any single bar's slice will ever get *narrower* than one column — i.e. it
# should stay ahead of MAX_ZOOM in waveform_view.py — or zooming past that
# point just repeats the same column across neighboring bars.
NUM_COLUMNS = 20_000

# Long recordings haven't been exercised end-to-end yet (memory, UI
# responsiveness, playback). Importing past this warns and requires
# confirmation rather than refusing outright — see AudioTooLongError.
MAX_DURATION_SECONDS = 30 * 60

_BLOCK_SIZE = 1 << 16


@dataclass
class WaveformData:
    peaks_min: np.ndarray
    peaks_max: np.ndarray
    duration_seconds: float
    sample_rate: int


class AudioTooLongError(RuntimeError):
    def __init__(self, duration_seconds: float, max_duration_seconds: float):
        self.duration_seconds = duration_seconds
        self.max_duration_seconds = max_duration_seconds
        super().__init__(
            f"Audio is {duration_seconds / 60:.1f} minutes long; "
            f"the app currently supports up to {max_duration_seconds / 60:.0f} minutes."
        )


def compute_waveform(
    path: str, num_columns: int = NUM_COLUMNS, allow_long: bool = False
) -> WaveformData:
    info = sf.info(path)
    if not allow_long and info.duration > MAX_DURATION_SECONDS:
        raise AudioTooLongError(info.duration, MAX_DURATION_SECONDS)
    total_frames = info.frames
    sample_rate = info.samplerate
    duration_seconds = info.duration

    peaks_min = np.zeros(num_columns, dtype=np.float32)
    peaks_max = np.zeros(num_columns, dtype=np.float32)

    if total_frames == 0 or num_columns == 0:
        return WaveformData(peaks_min, peaks_max, duration_seconds, sample_rate)

    running_min = np.full(num_columns, np.inf, dtype=np.float32)
    running_max = np.full(num_columns, -np.inf, dtype=np.float32)

    offset = 0
    for block in sf.blocks(path, blocksize=_BLOCK_SIZE, dtype="float32", always_2d=True):
        mono = block.mean(axis=1)
        frame_indices = offset + np.arange(len(mono))
        columns = np.minimum(frame_indices * num_columns // total_frames, num_columns - 1)
        np.minimum.at(running_min, columns, mono)
        np.maximum.at(running_max, columns, mono)
        offset += len(mono)

    touched = np.isfinite(running_min)
    peaks_min[touched] = running_min[touched]
    peaks_max[touched] = running_max[touched]

    return WaveformData(peaks_min, peaks_max, duration_seconds, sample_rate)
