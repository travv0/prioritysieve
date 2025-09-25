from collections.abc import Iterator

from ..morpheme import Morpheme
from ..morphemizers.morphemizer import Morphemizer
from . import sudachi_wrapper


class SudachiMorphemizer(Morphemizer):
    def __init__(self, dict_variant: str | None, split_mode: str) -> None:
        super().__init__()
        variant = (dict_variant or "").strip().lower()
        if variant == "auto":
            variant = ""
        self.dict_variant = variant
        self.split_mode = split_mode.upper()
        self._description = self._build_description()

    def init_successful(self) -> bool:
        return sudachi_wrapper.ensure_tokenizer(self.dict_variant, self.split_mode)

    def get_morphemes(self, sentences: list[str]) -> Iterator[list[Morpheme]]:
        for sentence in sentences:
            yield sudachi_wrapper.get_morphemes_sudachi(
                sentence,
                self.dict_variant,
                self.split_mode,
            )

    def get_description(self) -> str:
        return self._description

    def _build_description(self) -> str:
        base = "SudachiPy: Japanese"
        if self.dict_variant:
            return f"{base} ({self.dict_variant}, mode {self.split_mode})"
        return f"{base} (mode {self.split_mode})"
