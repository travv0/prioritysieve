from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Entry:
    text: str
    reading: str
    reviewed: bool

    def key(self) -> tuple[str, str]:
        return (self.text, self.reading)
