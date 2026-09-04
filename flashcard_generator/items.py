from __future__ import annotations

from dataclasses import dataclass

from .clips import Clip


@dataclass
class Item:
    """A flashcard-in-progress: an audio clip paired with free-typed text."""

    clip: Clip
    text: str = ""


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
