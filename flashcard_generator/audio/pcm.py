from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soundfile as sf


@dataclass
class PcmTrack:
    """Whole-file interleaved stereo PCM, decoded once at load time.

    Kept entirely in memory (int16, stereo) so PlaybackEngine's real-time
    push loop never touches disk — see playback_engine.py.
    """

    samples: np.ndarray  # int16, shape (frame_count, 2)
    sample_rate: int

    @property
    def frame_count(self) -> int:
        return self.samples.shape[0]


def decode_pcm(path: str) -> PcmTrack:
    samples, sample_rate = sf.read(path, dtype="int16", always_2d=True)
    if samples.shape[1] == 1:
        samples = np.repeat(samples, 2, axis=1)
    elif samples.shape[1] > 2:
        # Multichannel sources beyond stereo aren't part of this app's use
        # case (speech recordings for flashcards); keep the first two
        # channels rather than building a downmix nobody needs yet.
        samples = samples[:, :2]
    return PcmTrack(samples=np.ascontiguousarray(samples), sample_rate=sample_rate)
