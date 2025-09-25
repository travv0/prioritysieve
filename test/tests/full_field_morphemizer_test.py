from ankimorphs import ankimorphs_globals
from ankimorphs.morphemizers.morphemizer_utils import get_morphemizer_by_description


def test_none_morphemizer_returns_full_field() -> None:
    morphemizer = get_morphemizer_by_description(ankimorphs_globals.NONE_OPTION)
    assert morphemizer is not None

    text = "こんにちは 世界"
    morphs = next(morphemizer.get_morphemes([text]))
    assert len(morphs) == 1
    assert morphs[0].lemma == text
    assert morphs[0].inflection == text

    empty_morphs = next(morphemizer.get_morphemes([""]))
    assert empty_morphs == []
