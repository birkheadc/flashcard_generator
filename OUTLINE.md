# Language Flashcard Bootstrapper — Project Outline

## 1. Purpose

A personal tool to remove repetitive manual work from the process of building
Anki flashcards from native-language listening material. The manual process
being streamlined:

1. Record audio from native material (currently via Windows loopback / Audacity)
2. Break the recording into individual phrase/sentence clips — picking phrases
   that are neither too easy nor too hard — saving each as its own audio file
3. Create Anki flashcards: audio + hand-typed or copy-pasted text

This will be a **Python desktop application**.

**Development priority:** development happens across two machines — a
GPU-equipped main computer and a barebones laptop with no GPU. The GPU-only
features (forced alignment via `faster-whisper`) can't be relied on during
laptop sessions, so **build order starts with the manual workflow first**:
the UI for setting breakpoints in audio by hand and matching them to
transcript sections (or free-typing text) works with no ML dependency at all
and is usable on either machine. VAD assistance and forced alignment layer on
top of that once the core manual flow works.

## 2. Key Design Decisions

### 2.1 Audio Input
- **UI supports two entry points**: "Import file" and "Record in-app." Both
  are first-class options in the interface, not one primary path with a
  workaround.
- **v1 implements file import only.** The user provides a pre-recorded,
  full-length audio file (e.g. a 30-minute episode or chapter), recorded
  externally via Audacity or similar.
- **In-app recording is a disabled/stubbed option** for now. When it's
  implemented, it should use a native Windows audio library with direct
  WASAPI loopback access (e.g. `soundcard`/`sounddevice`, or
  `pyaudiowpatch`), not scheduled for v1 — the entry point exists in the UI,
  but selecting it can just show "not yet implemented" until then.

### 2.2 Phrase Segmentation & Matching
- **Single-page workflow.** Once audio (and optionally a transcript) are
  loaded, the user builds up a set of clip+text items using any combination
  of three tools, freely mixed within the same session:
  - **Forced alignment** (requires a transcript) — one action that generates
    multiple complete items at once: breakpoints and matched text both
    auto-populated, via Whisper timestamp alignment against the known text.
  - **Suggest snippets** (Silero VAD) — generates audio-only breakpoints;
    creates the clips but not the text. Works with or without a transcript,
    since VAD only needs the audio. The user fills in text afterward for
    each snippet, either by matching it to a transcript section or
    free-typing.
  - **Manual creation** — the user places a breakpoint and enters text for
    one item at a time, by hand.
- **Curation:** at any point, the user can delete items they judge too easy,
  too hard, or otherwise don't want — regardless of which tool created them.
- Once satisfied with the resulting set of items, the user moves on to card
  creation.
- **Explicitly ruled out:** Whisper generating text from scratch. Its only
  role in this app is forced alignment of text that already exists — it
  never invents a transcript.

### 2.3 Anki Export
- **Decision:** generate a **`.apkg` file directly** (via `genanki`), with
  audio embedded — the user just double-clicks to import, no manual media
  copying or CSV import step. **AnkiConnect support is out of scope** —
  `.apkg` only.
- **Card format is user-configurable in-app**, similar to Anki's own note
  type editor — not a hardcoded single template. `genanki.Model` supports
  arbitrary fields and templates, so this maps directly onto genanki's model
  system.
- **Cloze deletion is a hard requirement.** The core personal use case: cloze
  the target word within the phrase, with the goal of active recall (writing
  the word out from memory). `genanki` supports Anki's native cloze model
  type directly (`genanki.CLOZE_MODEL`-style setup) — the target word is
  wrapped in `{{c1::...}}` syntax within the field text.
  - Word/span selection for clozing should be **manual text selection** in
    the UI (like highlighting text in an editor) rather than automated word
    detection — this works uniformly across Japanese, Korean, or any language
    without needing per-language tokenization logic. See §6 for a possible
    later enhancement.

## 3. Architecture Decisions

| Decision | Choice | Why |
|---|---|---|
| Deployment shape | **Desktop application** | ML models (Whisper, VAD) are large; shipped once via installer, not fetched at runtime. |
| Language | **Python** | Best-in-class, most-mature libraries for every piece of the actual pipeline (VAD, transcription, Anki export). User wants the practice. Claude Code doing most of the writing reduces the cost of using an unfamiliar language. |
| UI framework | **PySide6** (Qt for Python) | Native widget toolkit. Qt's canvas tools (`QPainter`/`QGraphicsView`) and multimedia (`QMediaPlayer`) are well suited to the interactive waveform/snippet-selection UI, which is the hardest UI problem in the app. |
| PySide6 vs PyQt6 | **PySide6** | Same underlying Qt, but LGPLv3-licensed (vs PyQt6's GPL/commercial split) — no future constraint on distribution, and it's the Qt Company's official binding. |
| Platform target | **Windows (primary), Linux (nice-to-have)** | Developed on Linux; PySide6 is genuinely cross-platform so this isn't a major extra burden. |

## 4. Technical Stack

| Piece | Library | Notes |
|---|---|---|
| UI | **PySide6** | Windows, widgets, waveform view, playback (`QMediaPlayer`/`QAudioOutput`) |
| Voice activity detection | **silero-vad** | Powers "suggest snippets" — noise-robust audio breakpoint detection, independent of transcript availability |
| Forced alignment | **faster-whisper** (GPU/CUDA, CPU fallback) | Aligns an *existing* transcript to audio for timestamps — never used for freeform transcription. GPU gives roughly a 4–10x speedup over CPU; user has a GPU, so CUDA is the primary path with CPU as a portability fallback |
| Audio slicing/export | **pydub** / **soundfile** | Cutting the long recording into individual clips |
| Anki export | **genanki** | Generates `.apkg` with embedded audio — sole export mechanism (AnkiConnect out of scope) |
| Packaging | **PyInstaller** (tentative) | Single executable; one-time install cost, no runtime model fetching |

## 5. Resolved Questions

| Question | Decision |
|---|---|
| Anki export mechanism | `.apkg` file only, via `genanki` |
| Transcription mode | Whisper never generates text from scratch. Forced alignment matches text to audio only when a transcript exists. VAD-based snippet suggestion creates audio breakpoints only (no text) and works regardless of transcript availability. |
| GPU acceleration | Yes — user has a GPU. CUDA primary, CPU fallback for portability |

## 6. Language Configuration (Japanese & Korean)

**No installer-level "language pack" selection needed:**

- **`faster-whisper`** uses Whisper's multilingual checkpoints, which are
  trained on 99 languages (including Japanese and Korean) in a **single model
  file**. Language is just an inference-time parameter (`language="ja"` or
  `language="ko"`), not a separate download — one settings dropdown, not an
  install-time prompt.
- **`silero-vad`** operates on raw audio, not language — no per-language
  config needed at all.
- **Optional future accuracy improvement:** language-specific fine-tuned
  Whisper variants exist (e.g. `kotoba-whisper` for Japanese, distilled from
  large-v3 specifically on Japanese data) and are drop-in compatible with
  `faster-whisper`'s API. Worth keeping as a swappable model path later if
  the general multilingual model's Japanese/Korean accuracy isn't good enough
  in practice — not needed for v1.
- **Cloze word-selection** is manual (per §2.3), which sidesteps a real
  complication: Japanese has no spaces between words, and Korean's spacing is
  coarser than word-level (particles attach directly to nouns/verbs), so
  automatic word-boundary detection for either language would need a
  language-specific morphological tokenizer (e.g. `fugashi`/MeCab for
  Japanese). Manual selection avoids that dependency entirely for v1; it
  remains a possible later nice-to-have (smarter double-click-to-select-word
  behavior per language) but isn't required.

## 7. Explicitly Out of Scope

- Automated difficulty filtering — target-word/phrase selection stays a
  fully manual judgment call.
- AnkiConnect / live push to a running Anki instance.
- Freeform auto-transcription (Whisper is forced-alignment only, per §2.2).