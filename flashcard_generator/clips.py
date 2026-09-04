from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Clip:
    start_seconds: float
    end_seconds: float
    label: str = ""

    def __post_init__(self) -> None:
        if self.end_seconds <= self.start_seconds:
            raise ValueError(
                f"end_seconds ({self.end_seconds}) must be greater than "
                f"start_seconds ({self.start_seconds})"
            )

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


class ClipList:
    """Ordered, in-memory collection of Clips (add/reorder/remove)."""

    def __init__(self) -> None:
        self._clips: list[Clip] = []

    def __len__(self) -> int:
        return len(self._clips)

    def __iter__(self):
        return iter(self._clips)

    def __getitem__(self, index: int) -> Clip:
        return self._clips[index]

    def add(self, clip: Clip) -> int:
        self._clips.append(clip)
        return len(self._clips) - 1

    def remove(self, index: int) -> None:
        del self._clips[index]

    def replace(self, index: int, clip: Clip) -> None:
        self._clips[index] = clip

    def move(self, from_index: int, to_index: int) -> None:
        clip = self._clips.pop(from_index)
        self._clips.insert(to_index, clip)

    def clear(self) -> None:
        self._clips.clear()

    def regions(self) -> list[tuple[float, float]]:
        return [(c.start_seconds, c.end_seconds) for c in self._clips]
