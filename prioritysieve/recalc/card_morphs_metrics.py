from __future__ import annotations

from ..prioritysieve_config import PrioritySieveConfig
from ..morpheme import Morpheme
from ..reading_utils import normalize_reading


class CardMorphsMetrics:
    """Minimal morph metrics for tag updates and extra fields."""

    __slots__ = ("all_morphs", "unknown_morphs", "has_learning_morphs")

    def __init__(
        self,
        am_config: PrioritySieveConfig,
        card_id: int,
        card_morph_map_cache: dict[int, list[Morpheme]],
    ) -> None:
        self.all_morphs: list[Morpheme] = card_morph_map_cache.get(card_id, [])
        self.unknown_morphs: list[Morpheme] = []
        self.has_learning_morphs: bool = False

        if not self.all_morphs:
            return

        self._process(am_config)

    def _process(self, am_config: PrioritySieveConfig) -> None:
        learning_threshold = am_config.interval_for_known_morphs

        for morph in self.all_morphs:
            interval = morph.highest_lemma_learning_interval
            if interval is None:
                continue

            if interval == 0:
                self.unknown_morphs.append(morph)
            elif interval < learning_threshold:
                self.has_learning_morphs = True

    @staticmethod
    def get_unknown_morph_keys(
        card_morph_map_cache: dict[int, list[Morpheme]],
        card_id: int,
    ) -> set[tuple[str, str, str]]:
        unknown_keys: set[tuple[str, str, str]] = set()
        morphs = card_morph_map_cache.get(card_id)
        if not morphs:
            return unknown_keys

        for morph in morphs:
            interval = morph.highest_lemma_learning_interval
            if interval is None:
                continue

            if interval == 0:
                reading = normalize_reading(morph.reading)
                unknown_keys.add((morph.lemma, morph.lemma, reading))
                if len(unknown_keys) > 1:
                    break

        return unknown_keys
