from datetime import date

import pytest

from isn_engagement.terms import sort_terms, term_for, term_sort_key


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2025, 9, 22), "Fall 2025"),
        (date(2025, 12, 31), "Fall 2025"),
        (date(2026, 1, 5), "Winter 2026"),
        (date(2026, 3, 24), "Winter 2026"),
        (date(2026, 3, 30), "Spring 2026"),  # SCU spring quarter starts late March
        (date(2026, 6, 10), "Spring 2026"),
        (date(2026, 7, 4), "Summer 2026"),
        (date(2026, 9, 14), "Summer 2026"),
    ],
)
def test_term_for_boundaries(d: date, expected: str) -> None:
    assert term_for(d) == expected


def test_sort_terms_is_chronological_across_years() -> None:
    terms = ["Spring 2026", "Fall 2025", "Winter 2026", "Summer 2025"]
    assert sort_terms(terms) == ["Summer 2025", "Fall 2025", "Winter 2026", "Spring 2026"]


@pytest.mark.parametrize("bad", ["Fall", "Autumn 2025", "Fall twenty", ""])
def test_term_sort_key_rejects_bad_labels(bad: str) -> None:
    with pytest.raises(ValueError):
        term_sort_key(bad)
