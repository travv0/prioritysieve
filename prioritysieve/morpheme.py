from __future__ import annotations

import functools

from . import prioritysieve_globals


class Morpheme:
    __slots__ = (
        "lemma",
        "inflection",
        "reading",
        "part_of_speech",
        "sub_part_of_speech",
        "highest_lemma_learning_interval",
        "highest_inflection_learning_interval",
    )

    def __init__(  # pylint:disable=too-many-arguments
        self,
        lemma: str,
        inflection: str,
        reading: str | None = None,
        part_of_speech: str = "",
        sub_part_of_speech: str = "",
        highest_lemma_learning_interval: int | None = None,
        highest_inflection_learning_interval: int | None = None,
    ):
        """
        Lemma: dictionary form, e.g.: break
        Inflection: surface lemma, e.g.: broke, broken, etc.
        Part of speech: grammatical category, e.g.: nouns, verb.
        Sub Part of speech: no idea, probably more fine-grained categories. Used by Mecab.
        Highest Learning Interval: used to determine the 'known' status of the morph.
        """
        # mecab uses pos and sub_pos to determine proper nouns.

        self.lemma: str = lemma  # dictionary form
        self.inflection: str = inflection  # surface lemma
        self.reading: str | None = reading
        self.part_of_speech = part_of_speech  # determined by mecab tool. for example: u'動詞' or u'助動詞', u'形容詞'
        self.sub_part_of_speech = sub_part_of_speech
        self.highest_lemma_learning_interval: int | None = (
            highest_lemma_learning_interval
        )
        self.highest_inflection_learning_interval: int | None = (
            highest_inflection_learning_interval
        )

    def __eq__(self, other: object) -> bool:
        assert isinstance(other, Morpheme)
        return all(
            [
                self.lemma == other.lemma,
                self.inflection == other.inflection,
                self._normalized_reading() == other._normalized_reading(),
            ]
        )

    def __hash__(self) -> int:
        return hash((self.lemma, self.inflection, self._normalized_reading()))

    def _normalized_reading(self) -> str:
        return self.reading or ""

    def is_proper_noun(self) -> bool:
        return self.sub_part_of_speech == "固有名詞" or self.part_of_speech == "PROPN"

    # the cache needs to have a max size to maintain garbage collection
    @functools.lru_cache(maxsize=131072)
    def get_learning_status(
        self,
        interval_for_known_morphs: int,
    ) -> str:
        learning_interval = self.highest_lemma_learning_interval or 0

        if learning_interval == 0:
            return prioritysieve_globals.STATUS_UNKNOWN
        if learning_interval < interval_for_known_morphs:
            return prioritysieve_globals.STATUS_LEARNING
        return prioritysieve_globals.STATUS_KNOWN


class MorphOccurrence:
    __slots__ = (
        "morph",
        "occurrence",
    )

    def __init__(self, morph: Morpheme, occurrence: int = 1) -> None:
        self.morph: Morpheme = morph
        self.occurrence: int = occurrence

    def __add__(self, other: MorphOccurrence) -> MorphOccurrence:
        self.occurrence += other.occurrence
        return self


# mypy crashes if the files don't run something...
pass  # pylint:disable=unnecessary-pass
