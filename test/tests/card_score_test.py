from prioritysieve.morpheme import Morpheme
from prioritysieve.prioritysieve_globals import DEFAULT_REVIEW_DUE
from prioritysieve.recalc.card_score import compute_due_from_priorities


def test_compute_due_requires_exact_reading_match() -> None:
    matching_morph = Morpheme(lemma="食べる", inflection="食べる", reading="たべる")
    other_reading_morph = Morpheme(lemma="食べる", inflection="食べる", reading="たべろ")

    priorities = {
        ("食べる", "食べる", "たべる"): 5,
        ("書く", "書く", "かく"): 10,
    }

    assert compute_due_from_priorities([matching_morph], priorities) == 5
    assert (
        compute_due_from_priorities([other_reading_morph], priorities)
        == DEFAULT_REVIEW_DUE
    )
