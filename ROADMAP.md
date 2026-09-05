# Development Roadmap

Derived from [OUTLINE.md](OUTLINE.md). Ordered per its build-order priority:
manual workflow first (no ML, works on either machine), ML features
(VAD, forced alignment) layered on afterward since they need the GPU
machine. Each phase is independently verifiable before moving to the next.

> **Note:** Development paused after Phase 3 for an overall redesign of the
> UI (see [DESIGN.md](DESIGN.md)), rebuilding the app on a properly designed
> layout rather than the ad-hoc widget arrangement each earlier phase had
> bolted onto. That pass included disabled/stubbed entry points for several
> not-yet-built later-phase features (Import Transcript, Suggest Clips,
> Align Transcript, Note Template, Export), sized and positioned where
> they'll live once real, per DESIGN.md §3 — the same treatment already
> given the Phase 11 "Record in-app" stub. Each is wired up for real as its
> own phase lands; Phase 4 below is the first of those.

Status: **Phase 3 done.** **Phase 7 pulled forward and done early** (see
note below). **Phase 4 done.** Next up: **Phase 5**.

## Phase 0 — Bootstrap ✅
PySide6 app skeleton, `MainWindow` renders. Done.

## Phase 1 — Audio import & playback ✅
- "Import file" dialog (`QFileDialog`) to load a full-length audio file.
- Playback via `QMediaPlayer` / `QAudioOutput`: play, pause, seek.
- Waveform rendering for the loaded file (`QPainter` or a `QGraphicsView`
  scene, fed by `soundfile`/`pydub` sample data).
- Stub the "Record in-app" entry point as a disabled button/menu item
  showing "not yet implemented" (§2.1) — cheap to add now while the
  import/playback UI shell is being built.
- **Verify:** load a real ~30-min recording, see its waveform, scrub and
  play/pause smoothly.

## Phase 2 — Manual breakpoints & clips ✅
- Click-to-place breakpoints on the waveform; select a region as a clip
  (start/end times).
- Loop-preview playback of just the selected region.
- In-memory clip list (add/reorder/remove).
- **Verify:** manually carve a long recording into several clips and
  play each one back in isolation.

## Phase 3 — Item model: clip + text (pure manual flow) ✅
- Each clip gets a free-typed text field → forms an "item"
  (`audio_span + text`).
- Curation: delete any item regardless of how it was created.
- This phase alone is a complete, usable manual workflow per §1/§2.2 —
  the app is minimally useful end-to-end after this (modulo export).
- **Verify:** build a full session of items by hand, with no transcript
  and no ML, starting from a raw recording.

> **Note:** Phase 7 (session persistence) was pulled forward and
> implemented right after this phase, out of build order — see Phase 7
> below for why and what's scoped down as a result.

## Phase 4 — Transcript import & manual matching ✅
- Load a plain-text transcript.
- UI to associate a span of the transcript with a clip (manual pairing) as
  an alternative to free-typing.
- **Verify:** import a transcript alongside an audio file and manually
  match several spans to clips.

> **Design correction (made during implementation):** the original plan
> above (and DESIGN.md §5) called for auto-splitting the transcript into
> discrete sections on import, matched to clips one section at a time.
> That only makes sense once forced alignment (Phase 9) exists to cut
> sections against known audio timing — for *manual* matching there's no
> reliable way to guess where one section ends and the next begins, so
> auto-splitting would just produce arbitrary, likely-wrong boundaries.
> Dropped in favor of showing the raw transcript untouched and letting the
> user highlight whatever span they want, same as free-text selection in
> any editor. DESIGN.md §5 is stale on this point; this note is the
> current source of truth until it's updated.

- **Implemented:** "Import Transcript" (toolbar) reads a plain-text file
  (`flashcard_generator/transcript.py`) and shows it as-is — no splitting —
  in a read-only, text-selectable pane to the right of the waveform (hidden
  until a transcript is loaded). Pairing: select an item in the clip deck,
  highlight any span of the transcript by hand, "Use Selection as Text"
  copies that span onto the item's text field (equivalent to typing it —
  no persistent link back to a "section," since none exists). The
  transcript text persists across autosave/restore alongside the items
  (`session.py`), following Phase 7's note that this would be a small,
  additive schema change. Forced alignment (Phase 9), when it lands, will
  use the full transcript text plus VAD-suggested clip boundaries to
  generate matched items directly — it won't leave behind reusable
  "sections" either.

## Phase 5 — Cloze selection & card template
- Manual text-selection UI (highlight-to-select, like a text editor) to
  mark the cloze span within an item's text → wraps it as `{{c1::...}}`.
- Basic configurable note type editor: fields + template, mirroring
  Anki's own note-type editor (not hardcoded).
- Live preview of how a card will render.
- **Verify:** select a word/phrase in Japanese and Korean sample text,
  confirm correct cloze wrapping and preview rendering for both.

## Phase 6 — Anki export (`.apkg`)
- `genanki` integration: build `Model`/cloze model from the configured
  template, embed clip audio as media.
- Export action → produces a single `.apkg` file.
- **Verify:** export a deck, import the `.apkg` into a real Anki
  install, confirm cards display correctly and audio plays.

## Phase 7 — Session persistence ✅ *(done early, out of order)*
- Pulled forward from its normal place in the build order: manually
  rebuilding the item list after every app restart was slowing down
  development itself (no code-reload story for a Qt desktop app), and
  the crash-recovery benefit is worth having as early as possible for
  end users too.
- Implemented so far: silent autosave of source audio path + the item
  list (clip spans + text) to a fixed on-disk location
  (`~/.flashcard_generator/session.json`, `flashcard_generator/session.py`),
  written after every add/remove/reorder/edit; silently restored on
  the next launch. No explicit Save/Open UI — it's one continuous
  session, not named/multiple sessions.
- **Scoped down vs. the original plan:** no transcript or cloze-selection
  fields yet, since those data models don't exist until Phases 4–5.
  Extending the schema for them when those phases land is a small,
  additive change to `session.py`, not a rework.
- **Verify (done):** close/kill the app mid-session (including a
  simulated crash — no clean shutdown path taken) and relaunch;
  confirm audio and all items (spans + text) are restored automatically.

*— Everything above works with no ML dependency, on either machine. —*

## Phase 8 — VAD-assisted snippets *(GPU machine)*
- Integrate `silero-vad`; "Suggest snippets" action generates
  audio-only breakpoints/clips from the full recording.
- Suggested clips flow into the same item list/curation as manual ones.
- **Verify:** run on a real recording, confirm suggested breakpoints are
  reasonable and mix cleanly with manually-created items.

## Phase 9 — Forced alignment *(GPU machine)*
- Integrate `faster-whisper`; "Forced alignment" action takes the known
  transcript and generates fully-populated items (breakpoints + matched
  text) in one step.
- CUDA primary, CPU fallback; language param wired to a settings
  dropdown (ja/ko).
- **Verify:** run against a sample audio+transcript pair, confirm
  timestamps and matched text are correct for both languages.

## Phase 10 — Packaging
- `PyInstaller` build → single executable.
- **Verify:** run the built executable on the Windows target machine
  (the primary platform per §3), confirm no missing runtime deps.

## Phase 11 — In-app recording *(deferred, no ETA)*
- Replace the Phase 1 stub with real WASAPI loopback capture
  (`soundcard`/`sounddevice`/`pyaudiowpatch`).
- **Verify:** record a loopback session in-app and confirm it's
  equivalent to an externally-recorded file for downstream phases.

---

**Explicitly out of scope for all phases** (§7): automated difficulty
filtering, AnkiConnect, freeform Whisper transcription.
