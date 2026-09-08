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
note below). **Phase 4 done.** **Phase 5 done.** **Phase 5.5 done.**
**Phase 6 done.** **Phase 8 done.** **Phase 9 skipped for now** (still
requires the GPU machine; picked up again later). **Phase 10 implemented,
pending Windows verification** (see below — building/running it can't
happen from this Linux dev environment). Next up: **Phase 9** whenever the
GPU machine is back in the loop, or **Phase 11** if that continues to wait.

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

## Phase 5 — Cloze selection & card template ✅
- Manual text-selection UI (highlight-to-select, like a text editor) to
  mark the cloze span within an item's text → wraps it as `{{c1::...}}`.
- Basic configurable note type editor: fields + template, mirroring
  Anki's own note-type editor (not hardcoded).
- Live preview of how a card will render.
- **Verify:** select a word/phrase in Japanese and Korean sample text,
  confirm correct cloze wrapping and preview rendering for both.

- **Implemented:** `Item` gained `cloze_start`/`cloze_end` (character
  offsets into `text`, `flashcard_generator/items.py`) rather than storing
  `{{c1::...}}` inline — the text field always shows/edits the raw phrase,
  and `template.cloze_wrapped_text`/`render_cloze_field` compute the
  wrapped/blanked forms on demand. In the item editor, highlighting a span
  in the text field and clicking "Mark as Cloze" sets the span (highlighted
  in the field via a non-intrusive text overlay); "Clear Cloze" removes it.
  Editing the text afterward drops the span rather than leaving it stale
  against the new text, since offsets no longer line up in general.
  `flashcard_generator/template.py` adds `NoteTemplate` (fields +
  front/back template strings, defaults mirroring genanki's own cloze
  model) and a template-rendering engine (`{{cloze:Field}}` and
  `{{Field}}` placeholders) shared by both the item editor's live card
  preview and the new template editor (toolbar's "Note Template", now
  wired up instead of a disabled stub) opened via
  `flashcard_generator/ui/template_dialog.py`. Both the per-item cloze
  span and the deck-wide `NoteTemplate` are persisted in
  `session.py`/`session.json`, per Phase 7's note that this would be a
  small, additive schema change.

  > **Superseded (Phase 5.5):** single-span `cloze_start`/`cloze_end` was
  > replaced by a `cloze_spans` list (multiple clozes per item), and the
  > single "Clear Cloze" button described below was replaced by a
  > per-span remove control. See Phase 5.5 below.
- **Design deviations (made during implementation):** DESIGN.md §7 describes
  clearing a cloze as "a single click on the highlighted span" — implemented
  instead as an explicit "Clear Cloze" button alongside "Mark as Cloze",
  since detecting a click specifically within a highlighted text-overlay
  region (as opposed to Qt's own text-selection click handling) added
  meaningful complexity for a marginal interaction win; the highlighted span
  and both controls are still directly in the item editor, not a separate
  dialog. Per-item field data beyond the text/cloze field and clip audio
  doesn't exist yet (Item still only models clip+text+cloze, per Phase 3),
  so a template's fields beyond the first (bound to the cloze text) and any
  field literally named "Audio" (bound to a clip-time placeholder) render
  empty in previews — acceptable since OUTLINE §2.3's hard requirement is
  cloze + audio, and richer per-item field data isn't called for by any
  phase through Phase 6.

## Phase 5.5 — Multi-cloze & a saved-template library ✅
- **Why this phase exists:** added after Phase 5 landed, out of the
  original build order (hence the half-numbering, to avoid renumbering
  every later phase) — Phase 5's template editor could only edit *the one
  currently active* template, with no way to save it and reuse it across
  sessions/decks, and `Item` could only record a single cloze span, when
  Anki notes routinely need several (each becomes its own generated card).
- Multiple cloze spans per item, each numbered by reading order (`c1`,
  `c2`, ...) rather than creation order — **recording only**: this phase
  does not change export (Phase 6 still doesn't exist yet), so it doesn't
  address how a multi-cloze note becomes multiple `.apkg` cards. That's
  Anki's/genanki's own job once a `{{c1::...}}`/`{{c2::...}}`-tagged field
  reaches it; Phase 6 picks this up.
- A saved-template library: define, name, save, and load multiple note
  templates, rather than only being able to edit the one template active
  for the current session.
- **Small fix:** the deck row's Sentence column shows the item's original
  text, not a cloze-blanked rendering.

- **Implemented:** `Item.cloze_start`/`cloze_end` replaced by
  `cloze_spans: list[ClozeSpan]` (`flashcard_generator/items.py`) — a new
  `ClozeSpan(start, end)` dataclass. `Item.valid_cloze_spans()` drops any
  span invalidated by a later text edit (as `has_cloze` already did) and
  returns the rest sorted left-to-right, which is also the order cloze
  numbers are assigned in — `template.cloze_wrapped_text` now takes a list
  of spans and numbers them `{{c1::...}}`, `{{c2::...}}`, ... by that
  order, skipping any span that overlaps an earlier one once sorted.
  `Item.overlaps_existing_cloze(start, end)` backs a new guard: "Mark as
  Cloze" is disabled whenever the current text selection would overlap an
  already-marked span, since overlapping cloze spans don't make sense. The
  item editor's Cloze section now lists every marked span (`c1: "..."`,
  `c2: "..."`, ...) with its own remove button, rebuilt on every change —
  "Mark as Cloze" adds a new span rather than replacing the existing one,
  and the old single "Clear Cloze" button is gone. `session.py` persists
  `cloze_spans` as a list of `[start, end]` pairs, with backward-compatible
  loading of the old single-span `cloze_start`/`cloze_end` format from
  session files written before this phase.

  For the template library: `NoteTemplate` gained a `name` field
  (`flashcard_generator/template.py`; default `"Default"`), and a new
  `flashcard_generator/template_library.py` persists a list of named
  `NoteTemplate`s to `~/.flashcard_generator/templates.json` — deliberately
  separate from `session.json`, since a saved template is meant to be
  reusable across sessions/decks, the same way Anki's own note types are
  global to the profile rather than scoped to one deck. The template
  editor (`ui/template_dialog.py`) gained a "Saved Templates" list with
  New/Load/Save/Delete: New resets the editor to a blank default template
  without touching the library; Load replaces the editor's contents with a
  selected saved entry (no confirmation prompt, consistent with the app's
  existing "nothing is precious" posture — DESIGN.md §1 — for reversible,
  power-user actions); Save writes the editor's current content under
  whatever name is in the Template Name field, overwriting an existing
  entry of that name or adding a new one; Delete removes the selected
  entry. Unlike field/template edits (which apply live to the session's
  active template on every keystroke, per Phase 5), library actions
  require an explicit click — a stray click shouldn't silently overwrite a
  saved preset.

  The Sentence-column fix: `_populate_row` in `ui/main_window.py` now
  shows `item.text` as-is; the earlier cloze-blanked rendering (`저는
  [...] 입니다`) was removed since the deck row's State badge (Not
  drafted/No cloze/Ready) already conveys cloze progress, and blanking
  made it harder to spot-check what a clip's text actually says while
  scanning the deck.
- **Verify:** mark two non-overlapping spans in one item's text, confirm
  both render as distinct `{{c1::...}}`/`{{c2::...}}` in the underlying
  text, and that the card preview blanks only the first (see the
  follow-up correction below for what the preview actually shows); save a
  template under a name, create a new one, then reload the saved one and
  confirm its fields/templates come back; confirm the Sentence column
  shows unblanked text for an item with a cloze marked.

- **Follow-up fix (post-implementation):** two bugs surfaced when actually
  saving templates: the "Saved Templates" list and its New/Load/Save/
  Delete button row visibly overlapped (the dialog was being `resize()`d
  before its layout existed, so the splitter panel's real minimum height
  was understated once the layout activated), and saving the *first*
  template left it looking selected (highlighted) while Load/Delete
  stayed disabled (`_reload_library_list` rebuilds the list with
  `blockSignals(True)`, which also suppressed the `currentRowChanged` that
  normally keeps those buttons in sync — `_on_save_template_clicked` never
  refreshed them itself). Fixed by moving the dialog's `resize()` to after
  the layout is built, and by having `_reload_library_list` refresh the
  button-enabled state itself at the end rather than leaving every caller
  to remember to.

- **Follow-up gap (post-implementation):** the Live Preview had no way to
  see what a field *other than* the cloze-text field or "Audio" would
  look like — those two are the only ones with a real data source (item
  text/cloze, clip time), so a custom field like "Definition" always
  rendered blank, per this phase's own note above about per-item field
  data not existing yet. Fixed without waiting on that larger change: the
  preview panel now shows one editable sample-value input per field
  (`ui/template_dialog.py`'s `_rebuild_sample_data_inputs`, rebuilt
  whenever the field list changes), seeded from whatever real/sample data
  was originally passed in and freely editable from there — purely a
  preview scratchpad, not written back to any item, and not persisted
  past the dialog's session (re-opening the dialog reseeds from real item
  data again, same as before).

- **Follow-up gap (post-implementation):** the sample-data preview above
  turned out to be a half-measure — a custom field like "Definition" could
  be *previewed* with typed-in sample text, but there was still no way to
  give a real item its own actual content for that field, so every real
  card would render it blank regardless of the preview. Fixed by giving
  `Item` an `extra_fields: dict[str, str]` (`items.py`) for any field
  beyond the cloze-text field and "Audio" — both of which stay
  always-derived, never stored — persisted in `session.json` alongside
  `cloze_spans`. The item editor grew an "Additional Fields" section
  (`ui/main_window.py`'s `_rebuild_extra_field_inputs`, mirroring the
  Cloze section's rebuild-on-change pattern), one editable box per such
  field, hidden entirely when the template has none; every other Item(...)
  construction site in the file (region edits, cloze marks, transcript
  matches, ...) was audited to carry `extra_fields` forward rather than
  silently dropping it. `_field_values_for_item` now reads real per-item
  content for these fields instead of always rendering blank, so both the
  item editor's own Card Preview and (once saved as a template) the
  Note Template dialog's preview show real data.

  Surfaced two more layout issues while wiring this up: the item editor's
  `body` panel is a plain `QVBoxLayout` inside a fixed-size splitter
  column with no scroll area, so once the *first* custom field's row
  pushed total content past the panel's available height, the layout had
  nowhere to shrink and started squeezing/clipping widgets rather than
  resizing the panel — same failure mode as the template dialog's
  New/Load/Save/Delete row overlap noted above, but here driven by
  genuine content overflow rather than a premature `resize()`. Wrapped
  `body` in a `QScrollArea` (`setWidgetResizable(True)`) so it scrolls
  instead. Separately — and specific to modifying this section's layout
  while the modal Note Template dialog is still open — the newly-added
  row takes a few extra layout passes to reach its final size (a modal
  dialog's nested event loop appears to need more recompute passes to
  fully settle a background window's layout than the same change made
  outside one); this resolves within milliseconds under normal event
  processing and isn't user-visible, but is worth knowing if a similar
  "briefly wrong size" symptom shows up elsewhere after this pattern
  (build hidden, populate, then reveal) is reused.

- **Design deviation (post-implementation):** the Card Preview was pulled
  out of the item editor into its own panel, to the editor's right —
  a deliberate departure from DESIGN.md §7, which has the preview living
  inside the editor drawer alongside the edit controls. With Additional
  Fields (above) pushing the editor's own content past a single screen's
  height often enough to need the scroll area it now has, editing and
  reading-the-result-back read as distinct enough activities to earn
  separate, always-visible space rather than the preview being one more
  thing to scroll past. The deck row is now a three-way `QSplitter`
  (`ui/main_window.py`'s `deck_splitter`: Clips | Item | Card Preview,
  stretch factors 2:2:2, still user-draggable) instead of two; a new
  `_build_preview_panel` builds the panel (mirroring the existing
  `panelHeader`/`panelFooter` structure other panels already use) and is
  constructed *before* the editor panel even though it's added to the
  splitter after it — the editor panel's own construction ends by
  refreshing the card preview, which needs the preview panel's labels to
  already exist. `previewPanel` was added alongside `editorPanel` in
  `theme.py`'s panel border/background rules so it reads as a sibling,
  not a bolted-on extra.

- **Correction (post-implementation):** the preview's original
  "blank/reveal every cloze together" behavior (noted a few paragraphs
  up) doesn't match what Anki actually does with multiple clozes — it
  generates one *separate card per distinct cloze number*, not one card
  with every blank filled in. On card 1 (the `c1` card), only `c1`'s own
  span is ever blanked; every other number (`c2`, `c3`, ...) belongs to a
  different card and is shown revealed, even on card 1's front.
  `template.render_cloze_field`/`render_card` gained an `active_index`
  parameter (default `1`) implementing exactly that — blank only the
  matching index, always reveal the rest — and a new
  `template.cloze_index_count(field_values)` counts the distinct cloze
  numbers present. Both the item editor's Card Preview panel and the
  Note Template dialog's own preview now render only the `c1` card and,
  when `cloze_index_count` is more than 1, show a brief hint above the
  Front/Back boxes ("This will make N cards — showing card 1 only") so
  the limitation is stated rather than silently implied. Previewing every card (not just `c1`) is left for whenever
  Phase 6 export needs that same logic to actually generate them — no
  reason to build a card-switcher here first.

## Phase 6 — Anki export (`.apkg`) ✅
- `genanki` integration: build `Model`/cloze model from the configured
  template, embed clip audio as media.
- Export action → produces a single `.apkg` file.
- **Verify:** export a deck, import the `.apkg` into a real Anki
  install, confirm cards display correctly and audio plays.

- **Implemented:** `flashcard_generator/export.py` builds a `genanki.Model`
  (`model_type=genanki.Model.CLOZE`) directly from the session's
  `NoteTemplate` — fields map 1:1, `front_template`/`back_template` become
  `qfmt`/`afmt`, so a custom template (Phase 5.5's saved-template library
  included) exports exactly as it previews. `export_apkg(items, template,
  audio_path, deck_name, output_path, skip_incomplete=False)` slices each
  item's clip out of the source audio with `soundfile` (`sf.read` with
  frame-accurate `start`/`stop`, written back out as a per-item WAV into a
  temp dir) and embeds it as a `genanki.Package` media file, referenced from
  the template's "Audio" field as Anki's own `[sound:clip_0000.wav]` syntax
  — everywhere else (item editor/template dialog previews) that field stays
  the human-readable "🔊 0:00–0:02" placeholder, since those never touch a
  real `.apkg`. `find_export_issues` flags any item missing text or a
  cloze span; `export_apkg` raises `ExportBlockedError` (carrying the
  offending items) unless the caller passes `skip_incomplete=True`, per
  DESIGN.md §9's block-by-default/explicit-override rule — never a silent
  partial export. Model/deck IDs are derived from a stable hash of the
  template name / deck name (`_stable_id`, sha256-based) rather than
  genanki's suggested `random.randrange`, so re-exporting the same
  template/deck reuses the same Anki note type and deck on reimport
  instead of spawning duplicates; note `guid`s are similarly derived from
  the audio path + clip range so re-exporting the same item updates rather
  than duplicates it in Anki. A multi-cloze item (Phase 5.5) exports
  exactly as genanki/Anki interpret it natively — one card per distinct
  `{{cN::...}}` — with no extra logic needed on this side.

  The export flow itself (DESIGN.md §9) is a single dialog
  (`flashcard_generator/ui/export_dialog.py`, opened via the toolbar's
  "Export" action — now wired up instead of a disabled stub, enabled only
  once at least one item exists, `Ctrl+E`): an "Anki Deck Name" field, an
  output path chosen via `QFileDialog.getSaveFileName` (suggested location
  `~/Downloads` when it exists), and a summary of item readiness. Items
  missing text/cloze are listed by range and reason and block the Export
  button until an explicit "Export anyway, skipping N incomplete items"
  checkbox is ticked, matching §9's override wording exactly. On success
  the dialog's content is replaced with the output path and a "Reveal in
  File Manager" button (`QDesktopServices.openUrl` on the output
  directory) plus Close, rather than just closing silently.
- **Follow-up (post-implementation):** the deck name turned out to need
  the same "in-app, one continuous session" treatment as the note template
  rather than being a dialog-local field the user retypes on every
  export — Anki's own `.apkg` import matches decks *by name*, so importing
  into a pre-existing deck (rather than spawning a new one each time)
  means the name has to be typed once and then stay put. `MainWindow`
  gained `self._deck_name`, defaulted from the audio filename
  (`export.default_deck_name`) on a fresh import and persisted alongside
  `template`/`transcript_text` in `session.py`/`session.json` (a new
  `deck_name` field, defaulting to `""` — i.e. "derive it from the audio
  filename" — for session files written before this change).

  The editable control itself lives directly on the main toolbar (an
  "Anki Deck Name:" label + `QLineEdit`, disabled until audio is loaded,
  positioned between "Note Template" and "Export" since it's export-facing
  configuration), not inside the export dialog — a first pass put it in
  the dialog with a `deck_name_changed` signal mirroring
  `NoteTemplateDialog.template_changed`, but since `QDialog.exec()` is
  modal, that would've blocked editing it at the exact moment (mid-export)
  the user most wants to check/change it. The export dialog now just
  displays the current value read-only, with a hint pointing back at the
  toolbar field.
- **Design deviation (made during implementation):** clip audio is
  embedded as WAV rather than a compressed format — `soundfile`/libsndfile
  can write MP3 in this environment, but that depends on the local
  libsndfile build having LAME support, which isn't guaranteed on the
  Windows target machine (OUTLINE §3); WAV needs no optional codec and Anki
  plays it natively. Revisit if exported deck size becomes a real problem;
  out of scope for this phase per OUTLINE §2.3's requirement (audio embedded
  and playable), which doesn't mention size.

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

## Phase 8 — VAD-assisted snippets *(GPU machine)* ✅
- Integrate `silero-vad`; "Suggest snippets" action generates
  audio-only breakpoints/clips from the full recording.
- Suggested clips flow into the same item list/curation as manual ones.
- **Verify:** run on a real recording, confirm suggested breakpoints are
  reasonable and mix cleanly with manually-created items.

> **GPU machine, in name only:** despite the roadmap heading, this phase
> doesn't actually need CUDA — `silero-vad`'s model is a ~2MB JIT/ONNX
> graph that runs in comfortably sub-real-time on CPU alone, and (checked
> before depending on it) the PyPI package bundles its model weights
> directly in the wheel rather than fetching them at runtime, satisfying
> OUTLINE.md's "shipped once via installer" requirement with no network
> access needed at inference time either. The CUDA requirement OUTLINE.md
> and this roadmap heading actually mean belongs to Phase 9
> (`faster-whisper`), not this one. Built and verified in a container with
> no GPU exposed at all.

- **Implemented:** `flashcard_generator/vad.py` wraps `silero-vad`
  (`load_silero_vad()` / `get_speech_timestamps()`), lazily importing
  `silero_vad`/`torch` only when a session actually clicks "Suggest Clips"
  rather than at app startup, since that import is slow and otherwise
  unused weight on every launch. Audio is read via `soundfile` (the same
  library already used for waveform rendering and export) and downmixed/
  resampled to the 16kHz rate Silero expects with plain `numpy.interp`,
  rather than going through `torchaudio`'s own I/O/backend-dispatch path —
  one less place needing a working system audio backend, and one fewer
  thing to keep in sync with the app's existing audio-reading conventions.
  `suggest_snippets(path)` returns a plain `list[Clip]`, using Silero's own
  default thresholds/padding rather than exposing them as settings (no
  phase calls for that yet).

  `Item` gained a `provenance` field (`items.py`; `PROVENANCE_MANUAL`/
  `PROVENANCE_VAD` constants) recording whether a clip was hand-placed or
  VAD-suggested — a small additive change in the same spirit as
  `cloze_spans`/`extra_fields` before it, since Phase 9's forced alignment
  will need a third value here. Persisted in `session.py` with the usual
  backward-compatible default (`manual`) for older session files; every
  `Item(...)` reconstruction site in `main_window.py` (region edits, cloze
  marks, extra-field edits, transcript-selection matches) was audited to
  carry the original item's `provenance` forward rather than silently
  resetting it to the default, mirroring the audit Phase 5.5 did for
  `extra_fields`.

  The toolbar's "Suggest Clips" stub (previously grouped with "Align
  Transcript" under one disabled-stub loop) is now wired up for real via
  `_on_suggest_clips_clicked`, enabled once audio is loaded (same pattern
  as "Import Transcript"): runs `vad.suggest_snippets` synchronously under
  a wait cursor and adds one `Item(provenance=PROVENANCE_VAD)` per detected
  segment straight into the session's `ItemList`, so they sort/reorder/
  delete/edit exactly like manual items with no separate code path. No
  threading — consistent with `compute_waveform` already blocking the UI
  thread on import, and fast enough in practice (a ~60s recording processes
  in a couple of seconds even on CPU) that it wasn't worth being the app's
  first background-worker infrastructure. A run that finds no speech shows
  a status-bar message rather than silently doing nothing.

- **Design deviation (scoped down from DESIGN.md §4/§6, deliberately):**
  DESIGN.md describes amber waveform-region coloring with a dashed
  "unconfirmed" fill that solidifies once a VAD clip has been reviewed, plus
  multi-select and bulk-delete in the item deck for clearing a bad VAD
  batch in one action. None of that is required by this phase's own verify
  step (suggested clips just need to "mix cleanly" with manual ones, which
  the existing single-select deck already does — an empty-text VAD item
  already renders as "Not drafted" via the pre-existing status badge, with
  no code change needed). Built instead: a small colored provenance dot on
  each deck row's Range cell (`theme.PROVENANCE_COLORS`, reusing the
  existing accent/grade tokens rather than introducing new ones), tooltipped
  "Manually created"/"Suggested by VAD". Waveform region coloring, the
  seen/reviewed fade, and multi-select bulk-delete are left for later if a
  real VAD-heavy session finds the one-at-a-time deck delete too slow —
  no reason to build them speculatively ahead of that.

- **Verify (done):** run against `sample/kokoro/001_1.wav` (an existing
  Japanese audiobook clip already checked into the repo) — confirmed
  suggested clips land as normal deck rows with sensible timestamps,
  distinguishable from manual items via the provenance dot, curated
  (edited/deleted/reordered) identically to hand-placed ones, and persist
  correctly across autosave/restore. Confirmed working end-to-end
  interactively against a real recording.

## Phase 9 — Forced alignment *(GPU machine)*
- Integrate `faster-whisper`; "Forced alignment" action takes the known
  transcript and generates fully-populated items (breakpoints + matched
  text) in one step.
- CUDA primary, CPU fallback; language param wired to a settings
  dropdown (ja/ko).
- **Verify:** run against a sample audio+transcript pair, confirm
  timestamps and matched text are correct for both languages.

## Phase 10 — Packaging *(implemented; verify on Windows)*
- `PyInstaller` build → single executable.
- **Verify:** run the built executable on the Windows target machine
  (the primary platform per §3), confirm no missing runtime deps.

> **Scope grew slightly during implementation:** the roadmap line above
> only calls for a PyInstaller executable, but "build an installer for
> Windows" was the actual ask — a bare `.exe` folder isn't something a
> non-technical end user installs/uninstalls cleanly. Added an Inno Setup
> layer on top of the PyInstaller output, producing one `Setup.exe` a user
> runs (Start Menu shortcut, optional desktop shortcut, proper uninstall
> entry in Apps & Features) — still satisfying "single executable" from the
> distribution side, just not literally the only file PyInstaller emits.

- **Implemented:** `packaging/flashcard_generator.spec` (PyInstaller) builds
  a **onedir** app (`COLLECT`, not `--onefile`) — `silero-vad` pulls in
  `torch`, and a onefile build would re-extract torch's DLLs into a temp
  dir on every launch, slow enough to feel broken on first impression;
  onedir avoids that at the cost of the installer being the thing that
  hides "it's actually a folder" from the user rather than PyInstaller
  itself. `qtawesome` (icon fonts) and `silero_vad` (VAD model weights)
  both ship real files as package data with no importable reference
  PyInstaller's static analysis can follow, so both are pulled in
  explicitly via `PyInstaller.utils.hooks.collect_data_files` — confirmed
  those calls actually resolve non-empty file lists (24 qtawesome files, 6
  silero_vad files) since a spec that silently collected zero files would
  only surface as a runtime crash the first time a packaged build opens a
  dialog with an icon or clicks "Suggest Clips". `packaging/installer.iss`
  (Inno Setup 6) wraps the PyInstaller `dist/FlashcardGenerator/` output
  into `FlashcardGeneratorSetup.exe`; `packaging/build_windows.ps1` chains
  both steps (PyInstaller, then Inno Setup if `ISCC.exe` is found).
  `pyproject.toml` gained a `packaging` dependency group
  (`pyinstaller`, `pyinstaller-hooks-contrib` — the latter for its
  community-maintained `torch` hook, since torch's DLL/import surface is
  large enough that PyInstaller's own built-in hooks aren't always
  sufficient). `.gitignore`'s blanket `*.spec` rule (aimed at
  PyInstaller's own auto-generated specs from ad-hoc `pyinstaller foo.py`
  runs) gained a `!/packaging/*.spec` carve-out so this hand-written one
  stays tracked.

  UPX compression is left off in the spec — it shrinks torch's large DLLs
  but has a history of triggering Windows Defender/AV false positives on
  PyInstaller output specifically, which isn't a tradeoff worth making by
  default for a personal-use tool.

- **Deliberately not verified as "done" here:** PyInstaller doesn't
  cross-compile — a Windows `.exe` can only be produced by running the
  build on Windows, so none of this could be built or run inside this
  repo's Linux dev container. What *was* checked here: the two
  `collect_data_files` calls resolve real files (above), and
  `uv sync --group packaging` installs cleanly. The actual build, the
  installer, and this phase's own verify step (run on the Windows target
  machine, confirm no missing runtime deps) all still need to happen on
  Windows — see `packaging/README.md` for the exact commands and a
  slightly expanded verify checklist (icon rendering and "Suggest Clips"
  specifically, since those are the two things depending on the
  hand-collected data files above, not just "does it launch").
- **No app icon yet:** nothing in `design_reference/` or elsewhere in the
  repo is an `.ico`, so the spec passes `icon=None` and Inno Setup's
  shortcuts fall back to the exe's own (PyInstaller default) icon. Add one
  later by pointing the spec's `icon=` at a real `.ico` file — noted in
  `packaging/README.md` rather than inventing placeholder branding here.

## Phase 11 — In-app recording *(deferred, no ETA)*
- Replace the Phase 1 stub with real WASAPI loopback capture
  (`soundcard`/`sounddevice`/`pyaudiowpatch`).
- **Verify:** record a loopback session in-app and confirm it's
  equivalent to an externally-recorded file for downstream phases.

---

**Explicitly out of scope for all phases** (§7): automated difficulty
filtering, AnkiConnect, freeform Whisper transcription.
