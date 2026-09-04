from __future__ import annotations

import pytest

from flashcard_generator.clips import Clip
from flashcard_generator.items import Item, ItemList


def test_item_defaults_to_empty_text():
    item = Item(clip=Clip(0.0, 1.0))
    assert item.text == ""


def test_add_appends_and_returns_index():
    items = ItemList()
    first = items.add(Item(clip=Clip(0.0, 1.0)))
    second = items.add(Item(clip=Clip(1.0, 2.0), text="second"))

    assert first == 0
    assert second == 1
    assert len(items) == 2
    assert items[0].clip.start_seconds == 0.0
    assert items[1].text == "second"


def test_remove_deletes_by_index():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0)))
    items.add(Item(clip=Clip(1.0, 2.0)))

    items.remove(0)

    assert len(items) == 1
    assert items[0].clip.start_seconds == 1.0


def test_replace_swaps_item_at_index():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text="old"))

    items.replace(0, Item(clip=Clip(0.0, 1.0), text="new"))

    assert items[0].text == "new"


def test_move_reorders_items():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0)))
    items.add(Item(clip=Clip(1.0, 2.0)))
    items.add(Item(clip=Clip(2.0, 3.0)))

    items.move(2, 0)

    assert [i.clip.start_seconds for i in items] == [2.0, 0.0, 1.0]


def test_clear_empties_the_list():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0)))

    items.clear()

    assert len(items) == 0


def test_regions_returns_start_end_tuples_from_clips():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.5), text="a"))
    items.add(Item(clip=Clip(2.0, 3.0), text="b"))

    assert items.regions() == [(0.0, 1.5), (2.0, 3.0)]


def test_iteration_and_len():
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0)))
    items.add(Item(clip=Clip(1.0, 2.0)))

    assert len(items) == 2
    assert [i.clip.end_seconds for i in items] == [1.0, 2.0]
