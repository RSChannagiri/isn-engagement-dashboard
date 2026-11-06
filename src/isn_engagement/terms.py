"""Academic term helpers.

Santa Clara University runs on the quarter system, so the three terms ISN is
active in each year are Fall, Winter, and Spring. Term boundaries are approximate
calendar cutoffs that match the SCU academic calendar closely enough for
bucketing club events.
"""

from __future__ import annotations

from datetime import date

TERM_ORDER = ["Winter", "Spring", "Summer", "Fall"]

# (month, day) on which each season starts within a calendar year.
_SPRING_START = (3, 25)
_SUMMER_START = (6, 21)
_FALL_START = (9, 15)


def term_for(d: date) -> str:
    """Map a date to its academic term label, e.g. ``'Fall 2025'``."""
    md = (d.month, d.day)
    if md < _SPRING_START:
        season = "Winter"
    elif md < _SUMMER_START:
        season = "Spring"
    elif md < _FALL_START:
        season = "Summer"
    else:
        season = "Fall"
    return f"{season} {d.year}"


def term_sort_key(term: str) -> tuple[int, int]:
    """Sortable key for a term label so terms order chronologically.

    Raises ``ValueError`` for labels that are not ``'<Season> <Year>'``.
    """
    parts = term.split()
    if len(parts) != 2 or parts[0] not in TERM_ORDER or not parts[1].isdigit():
        raise ValueError(f"Not a term label: {term!r}")
    return int(parts[1]), TERM_ORDER.index(parts[0])


def sort_terms(terms: list[str] | set[str]) -> list[str]:
    """Return term labels in chronological order."""
    return sorted(terms, key=term_sort_key)
