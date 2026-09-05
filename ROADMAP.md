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
note below). **Phase 4 done.** **Phase 5 done.** **Phase 5.5 done.** Next
up: **Phase 6**.

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
