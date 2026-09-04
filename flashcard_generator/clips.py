from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Clip:
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        if self.end_seconds <= self.start_seconds:
            raise ValueError(
                f"end_seconds ({self.end_seconds}) must be greater than "
                f"start_seconds ({self.start_seconds})"
            )

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds
