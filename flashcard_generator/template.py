from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# Mirrors genanki's own cloze model defaults closely enough that Phase 6
# can build a genanki.Model directly from a NoteTemplate: fields map 1:1
# onto Model fields, front/back templates map onto qfmt/afmt.
DEFAULT_TEMPLATE_NAME = "Default"
DEFAULT_FIELDS = ["Text", "Audio"]
DEFAULT_FRONT_TEMPLATE = "{{cloze:Text}}"
DEFAULT_BACK_TEMPLATE = "{{cloze:Text}}<br>{{Audio}}"

_CLOZE_FIELD_RE = re.compile(r"\{\{cloze:(\w+)\}\}")
_FIELD_RE = re.compile(r"\{\{(\w+)\}\}")
_CLOZE_SPAN_RE = re.compile(r"\{\{c(\d+)::(.*?)\}\}", re.DOTALL)


@dataclass
class NoteTemplate:
    """A configurable note type: a name plus fields and front/back
    templates.

    Basic Anki-style note type editor per OUTLINE.md §2.3/ROADMAP.md
    Phase 5 — not a hardcoded single template, and shaped so it maps
    directly onto genanki's cloze `Model` (fields, qfmt, afmt) when
    Phase 6 wires up export. `name` identifies it within a saved
    `template_library` (ROADMAP.md Phase 5.5) — a session's currently
    active template need not be saved to the library at all.
    """

    name: str = DEFAULT_TEMPLATE_NAME
    fields: list[str] = field(default_factory=lambda: list(DEFAULT_FIELDS))
    front_template: str = DEFAULT_FRONT_TEMPLATE
    back_template: str = DEFAULT_BACK_TEMPLATE


def cloze_wrapped_text(text: str, spans: Iterable) -> str:
    """Wrap each marked span of `text` in Anki cloze syntax, numbered by
    reading order (`{{c1::...}}`, `{{c2::...}}`, ...) — ROADMAP.md Phase
    5.5's multi-cloze support. `spans` is any sequence of objects with
    `.start`/`.end` int attributes (e.g. `items.ClozeSpan`); spans invalid
    for `text`, or that overlap an earlier one once sorted, are skipped
    rather than raising, matching Item.has_cloze's own leniency.
    """
    ordered = sorted(
        (s for s in spans if 0 <= s.start < s.end <= len(text)), key=lambda s: s.start
    )
    parts = []
    cursor = 0
    index = 0
    for span in ordered:
        if span.start < cursor:
            continue
        index += 1
        parts.append(text[cursor : span.start])
        parts.append(f"{{{{c{index}::{text[span.start : span.end]}}}}}")
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts)


def render_cloze_field(value: str, *, active_index: int = 1, reveal: bool) -> str:
    """Render a field's raw value (which may contain `{{c1::...}}`,
    `{{c2::...}}`, ...) the way Anki renders one specific card of a cloze
    note: only `active_index`'s own span is ever blanked (to `[...]`, on
    the front, when not `reveal`ed) — every *other* cloze number is
    another card's target and is always shown as-is, matching real Anki
    (card 1's front reveals c2, c3, ... — it only hides c1). `reveal`
    shows `active_index`'s span too, i.e. that card's back.
    """

    def _replace(match: re.Match[str]) -> str:
        index, content = int(match.group(1)), match.group(2)
        if index == active_index and not reveal:
            return "[...]"
        return content

    return _CLOZE_SPAN_RE.sub(_replace, value)


def cloze_index_count(field_values: dict[str, str]) -> int:
    """How many distinct cloze numbers (`{{c1::...}}`, `{{c2::...}}`, ...)
    appear across `field_values` — i.e. how many separate cards Anki would
    generate from this content. Used to warn when a preview (which only
    ever shows one card, per `render_card`'s `active_index`) is hiding
    other cards that exist."""
    indices = {
        int(match.group(1))
        for value in field_values.values()
        for match in _CLOZE_SPAN_RE.finditer(value)
    }
    return len(indices)


def render_card(
    template: str, field_values: dict[str, str], *, active_index: int = 1, reveal: bool
) -> str:
    """Render a front/back template string against field values, as Anki
    would render the card for cloze number `active_index` (default: the
    first/`c1` card).

    Supports both Anki's `{{cloze:Field}}` placeholder and plain
    `{{Field}}` substitution. A field referenced but not present in
    `field_values` renders as empty, matching Anki's own template
    behavior rather than raising. A note with more than one distinct
    cloze number produces one card per number in real Anki — this
    renders only `active_index`'s card; see `cloze_index_count` to detect
    when others exist.
    """
    rendered = _CLOZE_FIELD_RE.sub(
        lambda m: render_cloze_field(
            field_values.get(m.group(1), ""), active_index=active_index, reveal=reveal
        ),
        template,
    )
    return _FIELD_RE.sub(lambda m: field_values.get(m.group(1), ""), rendered)
