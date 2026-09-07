from __future__ import annotations

import numpy as np
import soundfile as sf
import torch

from .clips import Clip

# Silero VAD is trained/shipped for exactly these two rates; anything else
# has to be resampled down before inference.
_MODEL_SAMPLE_RATE = 16_000

_model = None


def _load_model():
    global _model
    if _model is None:
        # Imported lazily (rather than at module load) since importing
        # torch/silero_vad is the slow part of using this module at all,
        # and most app sessions never click "Suggest Clips".
        from silero_vad import load_silero_vad

        _model = load_silero_vad()
    return _model


def _read_mono_16k(path: str) -> torch.Tensor:
    """Reads the full file via soundfile (same library already used for
    waveform rendering and export, rather than pulling in torchaudio's own
    I/O/backend dispatch just for this), downmixes to mono, and resamples
    to the 16kHz rate Silero VAD expects."""
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    mono = samples.mean(axis=1)
    if sample_rate != _MODEL_SAMPLE_RATE:
        duration = len(mono) / sample_rate
        target_length = max(1, round(duration * _MODEL_SAMPLE_RATE))
        source_x = np.linspace(0, 1, num=len(mono), endpoint=False)
        target_x = np.linspace(0, 1, num=target_length, endpoint=False)
        mono = np.interp(target_x, source_x, mono).astype(np.float32)
    return torch.from_numpy(mono)


def suggest_snippets(path: str) -> list[Clip]:
    """Runs Silero VAD (ROADMAP.md Phase 8) over the full recording at
    `path` and returns one Clip per detected speech segment, in order.
    Padding/min-duration filtering uses Silero's own defaults, which are
    tuned for exactly this kind of "find the phrases" task."""
    from silero_vad import get_speech_timestamps

    model = _load_model()
    wav = _read_mono_16k(path)
    timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=_MODEL_SAMPLE_RATE,
        return_seconds=True,
    )
    return [Clip(start_seconds=ts["start"], end_seconds=ts["end"]) for ts in timestamps]
