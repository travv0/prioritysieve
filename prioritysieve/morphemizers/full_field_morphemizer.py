from collections.abc import Iterator

from ..morpheme import Morpheme
from .morphemizer import Morphemizer


class FullFieldMorphemizer(Morphemizer):
    def init_successful(self) -> bool:  # pragma: no cover - trivial
        return True

    def get_morphemes(self, sentences: list[str]) -> Iterator[list[Morpheme]]:
        for sentence in sentences:
            text = sentence.strip()
            if not text:
                yield []
                continue
            yield [Morpheme(text, text)]

    def get_description(self) -> str:  # pragma: no cover - not exposed in UI
        return "Full Field"
