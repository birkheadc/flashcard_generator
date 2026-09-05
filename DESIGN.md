# UI Design — Language Flashcard Bootstrapper

This document describes the target end-state UI, independent of how it's
currently built. It's a rethink from first principles, grounded only in the
functional requirements in [OUTLINE.md](OUTLINE.md) and the phase scope in
[ROADMAP.md](ROADMAP.md) — not in any existing widget layout. It's meant to
drive a visual mockup first, then implementation.

## 1. Who this is for and how it's used

One user (the developer), reviewing 20–60 minute native-audio recordings,
building 20–100+ flashcards per session, often over multiple sittings on two
different machines. Sessions are long and repetitive: play a stretch of
audio, decide if a phrase is flashcard-worthy, carve it out, pair it with
text, move on. The UI's job is to make that loop as fast and low-friction as
possible — this is a personal production tool, not a polished consumer app.
Consequences for design:

- **Density over whitespace.** The user will use this for hours; screen
  space should favor seeing more waveform/more items over decorative margin.
- **Keyboard-first.** Mouse-only waveform work (clicking precise breakpoints)
  is unavoidable, but everything else — play/pause, confirm, delete, next
  item — should have a keyboard shortcut so hands don't leave the keyboard
  between clips.
- **Nothing is precious.** Items created by VAD or forced alignment are
  starting points, not commitments — deleting, editing, and re-doing must
  feel as cheap as the action that created them.
- **One continuous workspace.** Per OUTLINE §2.2 this is explicitly a
  single-page workflow, not a wizard. Import → segment → match → curate →
  export all happen in one window, and the three segmentation tools (manual,
  VAD, forced alignment) are freely interleaved, not separate modes.
- **CJK text is the common case, not an edge case.** Japanese and Korean
  text should render, wrap, and select as comfortably as the rest of the UI —
  never treated as an afterthought bolted onto a Latin-first design.

## 2. Overall layout

A single resizable main window, three horizontal zones stacked top to
bottom: a slim global toolbar, a large split workspace (waveform+transcript
above, item deck below), and a status bar. A right-hand editor drawer slides
in over the deck when an item is open for detail editing.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [Import Audio] [Import Transcript] [Record ▾ disabled] [Template] [Export]│ ← toolbar
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   WAVEFORM                                              │  TRANSCRIPT     │
│   ▂▃▅▇▆▃▁▂▄▆▇▅▃▂▁▂▃▅▇▆▅▃▂▁▃▅▇▆▃▂▁▂▄▆                     │  段落 1 …       │
│   ──────█████────────██████──────█████──────            │  段落 2 …       │
│          ↑clip        ↑clip       ↑VAD (unconfirmed)     │  段落 3 …       │
│                                                            │  ...           │
│   [Suggest Snippets]  [Forced Alignment]  zoom ──○──      │  (droppable    │
│                                                            │   onto clips)  │
├──────────────────────────────────────────────────────────────────────────┤
│  ITEM DECK (list, reorderable)                              ┌────────────┐│
│  ▸ 00:12–00:15  manual   「そうですね」                       │ ITEM       ││
│  ▸ 00:41–00:44  VAD      (no text yet)                       │ EDITOR     ││
│  ▸ 01:03–01:08  aligned  cloze preview: 저는 {{c1}} 입니다     │ (drawer,   ││
│  ...                                                          │ opens on   ││
│                                                                │ selection) ││
├──────────────────────────────────────────────────────────────────────────┤
│  ▶ 00:41 / 28:14      14 items · autosaved 2s ago            🇯🇵 ja       │ ← status bar
└──────────────────────────────────────────────────────────────────────────┘
```

The waveform/transcript split and the deck/editor split are both
user-draggable, with the transcript pane collapsing to a thin strip (or
fully hidden) when no transcript is loaded — the waveform then takes the
full width, so the pure-manual, no-transcript flow (Phase 3) never feels
like it's missing a piece of UI.

## 3. Toolbar

Left-aligned, grouped by workflow stage rather than alphabetically:

- **Import Audio** — file picker; replaces the current session's source
  audio (with a confirmation if a session is already in progress).
- **Record ▾** — dropdown/button, visibly disabled with a tooltip
  ("Not yet implemented — see roadmap") per OUTLINE §2.1. It stays visible
  and in the same position it'll occupy once real, rather than being hidden,
  so the eventual feature doesn't reshuffle the toolbar.
- **Import Transcript** — loads a plain-text transcript and populates the
  transcript pane; disabled/hinted until audio is loaded.
- **Template** — opens the note-type/template editor (§7).
- **Export** — opens the export flow (§8); disabled until at least one item
  exists.

Far right of the toolbar: a compact settings icon (alignment language
ja/ko, theme) — see §9.

## 4. Waveform pane

The primary work surface. Horizontally scrollable/zoomable, always full
window height available to it (modulo the transcript pane's width).

- **Playhead** — a thin vertical line, click-to-seek anywhere on the ruler
  above the waveform.
- **Breakpoints** — thin draggable vertical markers the user places by
  clicking. Dragging an existing breakpoint adjusts it live, with audio
  scrubbing feedback.
- **Clip regions** — the space between two breakpoints, once marked as a
  clip, is shaded (a distinct fill, e.g. translucent accent color) and
  double-clicking it loops-plays just that region. Regions are draggable at
  both edges to fine-tune start/end after creation.
- **Source-of-origin color coding**, consistent across the waveform *and*
  the item deck below, so provenance is recognizable at a glance without
  reading a label:
  - Manual — neutral accent (e.g. blue)
  - VAD-suggested — amber, and rendered with a lighter/dashed fill until the
    user has reviewed it at least once (viewed or played), at which point it
    solidifies to the normal fill — a lightweight "seen" signal that helps
    the user track review progress across a long recording.
  - Forced-alignment — green, since these arrive with text already attached.
- **Zoom control** — a slider or +/- with keyboard shortcuts, needed because
  a 30–60 minute recording can't usefully show sample-level detail at full
  width; horizontal scroll/pan (trackpad/shift+wheel) moves through it.
- **Action row directly under the waveform**: "Suggest Snippets" (VAD) and
  "Forced Alignment" (only enabled once a transcript is loaded) sit right
  where the user is looking, rather than buried in the toolbar — these are
  the two automation entry points and should be one click away from the
  audio they act on.

## 5. Transcript pane

> **Superseded (Phase 4 implementation):** the "list of pre-cut sections"
> design below was dropped — see ROADMAP.md Phase 4's design-correction
> note. Auto-splitting a transcript into sections only makes sense once
> forced alignment (Phase 9) can cut them against known audio timing;
> for manual matching there's no reliable place to draw those boundaries
> automatically. What's actually built: the raw transcript shown untouched
> in a read-only, text-selectable field, CJK-safe font/line-height (§10)
> as below. The user highlights any span by hand (ordinary text-editor
> selection, not a fixed list) and a "Use Selection as Text" button copies
> it onto the currently selected item — a plain text-field write, not a
> tracked "match" with its own visual state. No drag-and-drop, no
> matched/unmatched indicator, since there's no discrete section to carry
> that state. The rest of this section (now historical) described the
> original per-section design:

A simple vertical list of transcript sections (paragraph/line-split on
import). Each section:

- Shows its raw text, CJK-safe font/line-height (§10).
- Has a visual "matched" state once assigned to a clip (dimmed/checked),
  and an "unmatched" state (full contrast) — so remaining work is scannable
  as an at-a-glance list, not something the user has to click into each
  item to discover.
- Assignment is drag-and-drop: drag a section onto a clip region in the
  waveform, or onto a row in the item deck. A click-based alternative
  (select section, select clip, "Match" button) exists for precision/
  accessibility, since drag-and-drop alone is a poor fit for a keyboard-
  heavy workflow.
- Forced alignment (§4) populates both breakpoints and matches in one step;
  matched sections from that path show the same "matched" state as manual
  pairing, with the "aligned" provenance color from §4 carried onto the
  item itself, not the transcript row.

When no transcript is loaded, this pane collapses (§2) rather than showing
an empty list — an empty list would imply the feature is broken, not
optional. (Still true: the pane collapses when there's no transcript,
whether or not it holds pre-cut sections.)

## 6. Item deck

The accumulating list of clip+text items — the actual output of the
segmentation stage, and the thing the user curates before moving to export.
A dense, single-line-per-item list/table, reorderable by drag:

| Column | Content |
|---|---|
| Provenance dot | Color from §4 (manual/VAD/aligned) |
| Time range | `00:41–00:44` |
| Text preview | Free text, or cloze-rendered preview once a cloze span is set (`저는 {{c1}} 입니다` shown as `저는 [...] 입니다`) |
| Status | "no text yet" (VAD items awaiting pairing) / "no cloze yet" once Phase 5 lands / ready |
| Actions | Play (loop-preview inline, no need to open the editor), Delete |

Selecting a row (click, or arrow keys + Enter) opens the **item editor**
drawer (§2, right side) for full editing. Delete is available directly on
the row *and* in the editor, since "this one's not good enough" is a
judgment made constantly during review and shouldn't require opening the
item first.

Multi-select (shift/ctrl-click or shift+arrow) + bulk delete matters here:
VAD can produce a batch of suggestions where several are obviously unusable,
and clearing them one at a time would be exactly the kind of friction this
tool exists to remove.

## 7. Item editor (drawer)

> **Superseded (post-Phase-5.5 implementation):** the live card preview
> described below no longer lives inside this drawer — see ROADMAP.md
> Phase 5.5's design-deviation note. Additional Fields (also added after
> this section was written) pushed the drawer's own content past a single
> screen's height often enough to need a scroll area, and at that point
> the preview read as one more thing to scroll past rather than the
> always-visible check-your-work panel it's meant to be. It's now a
> separate panel to this drawer's right (still part of the same deck row,
> still appears/updates for whichever item is selected here) — everything
> else in this section is unchanged.

Opens for one selected item at a time; everything about that item lives
here so the deck row can stay a single line.

- **Text field** — the item's text, free-typed or transcript-matched.
  Editable regardless of origin (a matched transcript section is a starting
  point, not a lock).
- **Cloze selection** (Phase 5) — click-and-drag text selection directly in
  this field, like highlighting in any text editor; the selected span
  highlights and a small inline control confirms it as the cloze, wrapping
  it as `{{c1::...}}` under the hood. No separate dialog — the selection
  gesture *is* the cloze action, since OUTLINE §2.3 is explicit that this
  should feel like ordinary text-editor highlighting, not a special tool.
  Clearing/reselecting is a single click on the highlighted span.
- **Audio controls** — loop-play the item's clip, and a mini waveform
  (zoomed to just this clip's range) with draggable start/end handles so
  boundary tweaks don't require jumping back to the main waveform.
- **Live card preview** (Phase 5/6) — shows the rendered front/back exactly
  as the configured note template (§7 template editor) will produce it,
  cloze blanked on the front, revealed on the back — so the user sees the
  actual flashcard, not just the raw field data, before it's ever exported.
  Now its own panel — see the superseded note above.

## 8. Note type / template editor

A separate panel (opened via the toolbar's "Template" button), modeled
conceptually on Anki's own note-type editor per OUTLINE §2.3, but scoped to
this app's needs:

- Field list (defaults: Text, Audio, roughly matching genanki's cloze
  model) — add/rename/remove fields.
- Template editor for front/back HTML, with the cloze field's
  `{{cloze:Text}}`-equivalent placeholder pre-inserted and explained inline
  rather than left for the user to remember Anki's template syntax.
- Live preview pane, sharing the same rendering used in the item editor
  (§6) — one preview implementation, not two that can drift apart.
- Changes here apply to the whole deck's export, not per-item — this is
  configuration, not content, so it's deliberately separated from the
  per-item flow in §6.

## 9. Export flow

A single dialog, since export is a terminal action with no ongoing state:

1. Deck name (text field, defaults to the source audio's filename).
2. Output path (file picker, defaults to a sensible last-used location).
3. Summary: item count, how many are missing text/cloze (blocking issues
   surfaced *before* the user commits to exporting, not discovered after
   opening the file in Anki).
4. Confirm → produces the `.apkg` with embedded audio (OUTLINE §2.3);
   success state shows the output path with a "reveal in file manager"
   action.

Items missing required data (no text, or cloze required but unset) are
listed and block export by default, with an explicit "export anyway,
skipping N incomplete items" override — never a silent partial export.

## 10. Settings

Small, since OUTLINE explicitly avoids most configuration (§6: no
install-time language pack, one inference-time dropdown):

- Forced-alignment language: `ja` / `ko` dropdown.
- Theme: light/dark (dark favored for long low-light review sessions, but
  both should be full first-class palettes, not a dimmed light theme).
- Session/autosave status is informational only (status bar, §2) — no
  save/open UI, consistent with the "one continuous session" model already
  implemented in Phase 7.

## 11. Visual language

Functional, not branded — this is a personal tool, not a product with a
brand identity. A neutral, low-chroma base so the provenance colors (§4),
which carry real information, stay the most saturated things on screen and
don't compete with decorative color elsewhere.

- **Base palette** — neutral gray-blue scale for chrome/panels, near-white
  in light mode / near-black (not pure black, to keep waveform contrast
  comfortable) in dark mode.
- **Accent** — one accent hue for primary actions and the "manual"
  provenance color (§4), e.g. a mid blue (`#3B82F6`-ish).
- **Provenance triad** — blue (manual) / amber (VAD) / green (aligned),
  chosen for mutual distinguishability including for common color-vision
  deficiencies — verify before final mockup rather than assuming.
- **Typography** — a UI sans-serif for chrome/labels, paired with a
  separate font stack for content text that guarantees full CJK glyph
  coverage (e.g. Noto Sans JP/KR as fallback) with generous line-height,
  since Japanese/Korean text sits in the transcript pane, item text field,
  and card preview constantly — it must never fall back to tofu boxes or
  cramped line spacing.
- **Density** — compact row heights and tight but legible spacing in the
  deck and transcript lists (per §1); more breathing room only in the
  editor drawer and dialogs, where the user is focused on one item rather
  than scanning many.

## 12. Keyboard model

Waveform breakpoint placement is inherently mouse-driven, but everything
downstream of it should not require reaching for the mouse:

| Key | Action |
|---|---|
| Space | Play/pause at playhead (or loop-selected clip if one's focused) |
| ←/→ | Seek; with a modifier, nudge a selected breakpoint |
| ↑/↓ | Move selection between item deck rows |
| Enter | Open selected item's editor |
| Delete/Backspace | Delete selected item(s) |
| Esc | Close editor drawer / cancel current drag |
| Ctrl/Cmd+E | Open export dialog |

## 13. Explicitly out of scope for this pass

- **In-app recording UI** — stays a stubbed, visibly-disabled toolbar entry
  (§3) until Phase 11; not designed in detail here.
- **AnkiConnect / any live-push UI** — out of scope per OUTLINE §7.
- **Automated difficulty filtering UI** — curation stays a manual judgment
  call throughout (§1, §6); no "suggested for deletion" affordance.
