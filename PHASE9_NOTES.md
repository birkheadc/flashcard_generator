# Phase 9 — Open Questions

Raised while scoping ROADMAP.md's Phase 9 (forced alignment), before any
implementation started. Parking these — work on Phase 9 is on hold until
we pick this back up.

## 1. `faster-whisper` doesn't actually do forced alignment

It's a transcription model: feed it audio, it freely decodes text with
timestamps. "Forced alignment" (snapping *known* text to audio timing) is a
different operation. Two common ways to fake it on top of Whisper:

- Transcribe freely with `word_timestamps=True`, then fuzzy-match the ASR
  output against the known transcript to steal its timestamps and swap in
  the ground-truth text.
- Use a real CTC forced-aligner instead of/alongside Whisper (e.g.
  `torchaudio.functional.forced_align`, or what WhisperX does with a
  wav2vec2 aligner).

Need to pick one before writing `flashcard_generator/alignment.py`.

## 2. Transcript may be much longer than the clip

Checked the existing sample data: `sample/kokoro/001_transcript_full.txt`
is the *entire novel* (1597 lines), but `sample/kokoro/001_1.wav` is only
~62 seconds of narration. So this phase isn't just "align text to audio
1:1" — it's "find which slice of a much longer transcript this clip
corresponds to, then align within that slice." That's a real design
decision, not an implementation detail, and interacts with question 1
(whichever matching approach we pick has to also do this localization
step).

## 3. Model size vs. packaging requirement

OUTLINE.md requires ML models "shipped once via installer," no runtime
fetch. VAD's model is ~2MB and bundles fine. Whisper checkpoints run from
~75MB (tiny) to ~3GB (large-v3), and `faster-whisper` defaults to lazily
downloading from HuggingFace on first use rather than bundling. Need to
pick a default model size and confirm it can actually be bundled at
install time, not fetched at inference time.

## 4. No Korean test data

We only have a Japanese sample checked into the repo
(`sample/kokoro/`). Phase 9's own verify step requires both `ja` and `ko`.
Need a Korean audio+transcript pair before the phase can be verified
end-to-end.

## 5. CUDA can only be verified on the other machine

This dev container has no GPU (`torch.cuda.is_available()` is `False`, no
`nvidia-smi`) — same situation Phase 8 was built under. The CPU fallback
path can be built and verified here; the CUDA path needs the actual GPU
machine.

## 6. UI wiring not yet built

- `ui/main_window.py:700` has a disabled "Align Transcript" toolbar stub
  to wire up, enabled once both audio *and* a transcript are loaded
  (mirroring `_on_suggest_clips_clicked`'s pattern from Phase 8).
- DESIGN.md §10 calls for a ja/ko settings dropdown that doesn't exist
  yet anywhere in the app — this would be the first real "settings" UI.
  Needs a home: toolbar control (like Phase 6's deck-name field) vs. an
  actual settings panel.
- `items.py` already anticipates this with `PROVENANCE_MANUAL`/
  `PROVENANCE_VAD`; just needs `PROVENANCE_ALIGNED` plus the same
  Item-reconstruction-site audit Phase 8 did for `provenance`.
