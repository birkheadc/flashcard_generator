from __future__ import annotations

from dataclasses import dataclass, field

from .clips import Clip


@dataclass
class ClozeSpan:
    """A single marked cloze span: character offsets (Python slice indices)
    into an Item's `text`. An Item can carry several — ROADMAP.md Phase
    5.5 — each becomes its own `{{cN::...}}` in `template.cloze_wrapped_text`,
    numbered by reading order (leftmost span first), not creation order.
    """

    start: int
    end: int


@dataclass
class Item:
    """A flashcard-in-progress: an audio clip paired with free-typed text.

    `cloze_spans` mark the spans within `text` the user has selected as
    cloze deletions — kept as offsets into the plain text rather than
    storing `{{c1::...}}` inline, so the text field always shows/edits the
    raw phrase and the cloze wrapping (`template.cloze_wrapped_text`) is
    only ever computed, not hand-maintained.

    `extra_fields` holds free-typed content for any note-type field beyond
    the cloze-text field and "Audio" (both of which are always derived —
    from `text`/`cloze_spans` and `clip` respectively, never stored here).
    Keyed by field name, so a rename in the template editor orphans the
    old key's value rather than migrating it — same leniency already
    applied to a stale cloze span.
    """

    clip: Clip
    text: str = ""
    cloze_spans: list[ClozeSpan] = field(default_factory=list)
    extra_fields: dict[str, str] = field(default_factory=dict)

    @property
    def has_cloze(self) -> bool:
        return len(self.valid_cloze_spans()) > 0

    def valid_cloze_spans(self) -> list[ClozeSpan]:
        """Marked spans still valid against the current text — dropping any
        left stale by a later text edit, rather than raising — sorted in
        reading order (left to right), the order cloze indices (c1, c2,
        ...) get assigned in."""
        valid = [s for s in self.cloze_spans if 0 <= s.start < s.end <= len(self.text)]
        return sorted(valid, key=lambda s: s.start)

    def overlaps_existing_cloze(self, start: int, end: int) -> bool:
        """Whether [start, end) overlaps any already-marked valid span —
        used to reject a new cloze selection that would collide with one
        already marked, since overlapping `{{cN::...}}` spans don't make
        sense."""
        return any(s.start < end and start < s.end for s in self.valid_cloze_spans())


class ItemList:
    """Ordered, in-memory collection of Items (add/reorder/remove)."""

    def __init__(self) -> None:
        self._items: list[Item] = []

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, index: int) -> Item:
        return self._items[index]

    def add(self, item: Item) -> int:
        self._items.append(item)
        return len(self._items) - 1

    def remove(self, index: int) -> None:
        del self._items[index]

    def replace(self, index: int, item: Item) -> None:
        self._items[index] = item

    def move(self, from_index: int, to_index: int) -> None:
        item = self._items.pop(from_index)
        self._items.insert(to_index, item)

    def clear(self) -> None:
        self._items.clear()

    def regions(self) -> list[tuple[float, float]]:
        return [(i.clip.start_seconds, i.clip.end_seconds) for i in self._items]
