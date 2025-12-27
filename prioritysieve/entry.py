from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Entry:
    text: str
    reading: str
    language_name: str
    reviewed: bool

    def key(self) -> tuple[str, str, str]:
        return (self.text, self.reading, self.language_name)
