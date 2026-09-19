"""Shared date-recognition logic for the "date" field type (date_of_birth is
the only consumer today).

One source of truth for pattern matching (previously duplicated between the
extractor and the validator — a real bug, since fixing one without the other
means extraction can accept a phrase validation then rejects). Also the only
place that turns whatever the customer said, in whatever format or language,
into the canonical DD-MM-YYYY string that's actually stored — so downstream
systems always see one consistent format regardless of how it was spoken.

Two real bugs fixed here, found via live testing:

1. A customer said "first January 2026"; the STORED value came out as
   "january 20" — a truncated fragment. Root cause: find_date_span() returned
   on the FIRST regex pattern that matched, in list order, and the (correct
   but generic) "month + a day number" pattern matched "january 20" as a
   *prefix* of "january 2006" (\\d{1,2} is not right-bounded, so it happily
   grabbed just the first two digits of the four-digit year and stopped).
   Fixed two ways: every day/year digit group is now word-boundary-anchored
   (\\b) so it can never match a prefix of a longer digit run, AND
   find_date_span() now evaluates every pattern and keeps the LONGEST match
   instead of the first one — robust against this whole bug class even if
   more patterns are added later.

2. A date missing its year (e.g. "March 14" alone) used to be accepted as
   a complete match. For a date-of-birth field that's wrong — every pattern
   now requires a year.
"""

import re
from datetime import date
from typing import Optional

MONTH_NAMES = [
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
]
MONTH_TO_NUM = {m: i + 1 for i, m in enumerate(MONTH_NAMES)}

ORDINAL_TO_NUM = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty first": 21,
    "twenty-second": 22, "twenty second": 22, "twenty-third": 23, "twenty third": 23,
    "twenty-fourth": 24, "twenty fourth": 24, "twenty-fifth": 25, "twenty fifth": 25,
    "twenty-sixth": 26, "twenty sixth": 26, "twenty-seventh": 27, "twenty seventh": 27,
    "twenty-eighth": 28, "twenty eighth": 28, "twenty-ninth": 29, "twenty ninth": 29,
    "thirtieth": 30, "thirty-first": 31, "thirty first": 31,
}
ORDINAL_WORDS = sorted(ORDINAL_TO_NUM.keys(), key=len, reverse=True)  # longest-first: "twenty-first" before "first"

_MONTH_ALT = "|".join(MONTH_NAMES)
_ORDINAL_ALT = "|".join(re.escape(w) for w in ORDINAL_WORDS)
_YEAR = r"(?<!\d)(?:19|20)\d{2}(?!\d)"
# NOT \b\d{1,2}\b — a digit is a \w character, so \b would reject "14" in
# "14th" (no transition between the "4" and the "t"). Lookarounds instead:
# not preceded or followed by ANOTHER DIGIT specifically, while still
# allowing an immediately-following ordinal suffix letter. This is what
# actually fixes the "20" matched as a prefix of "2006" bug without
# breaking "14th"/"3rd"-style ordinal suffixes.
_DAY_DIGIT = r"(?<!\d)\d{1,2}(?!\d)"

# Every alternative requires a year — a date_of_birth missing its year is
# incomplete, not a valid capture (see bug #2 above).
DATE_PATTERNS = [
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
    r"\d{4}-\d{1,2}-\d{1,2}",
    rf"(?:{_MONTH_ALT})[a-z]*\s+{_DAY_DIGIT}(?:st|nd|rd|th)?,?\s+{_YEAR}",  # "March 14th, 1990"
    rf"{_DAY_DIGIT}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTH_ALT})[a-z]*,?\s+{_YEAR}",  # "14th of March 1990"
    rf"(?:{_ORDINAL_ALT})\s+(?:of\s+)?(?:{_MONTH_ALT})[a-z]*,?\s+{_YEAR}",  # "first of January 2026"
    rf"(?:{_MONTH_ALT})[a-z]*\s+(?:{_ORDINAL_ALT}),?\s+{_YEAR}",  # "January first 2026"
]


def matches_date(text: str) -> bool:
    return find_date_span(text) is not None


def find_date_span(text: str) -> Optional[str]:
    """Evaluates every pattern and returns the LONGEST match — not the first
    one found — so a more specific/complete pattern can never lose to a
    shorter pattern that happens to match a prefix of the same text."""
    lowered = text.lower()
    best: Optional[str] = None
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, lowered)
        if match and (best is None or len(match.group(0)) > len(best)):
            best = match.group(0)
    return best


def normalize_to_ddmmyyyy(raw: str) -> Optional[str]:
    """Converts whatever format/language-adjacent phrasing was captured into
    a canonical DD-MM-YYYY string. Returns None if it can't confidently
    parse (caller should treat that as a failed capture, not guess)."""
    span = find_date_span(raw)
    if span is None:
        return None
    lowered = span.lower().strip()

    # digit/digit/digit — Australian convention: day/month/year.
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", lowered)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        year_int = _expand_2digit_year(year)
        return _format_and_validate(day, month, year_int)

    # ISO: year-month-day
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", lowered)
    if m:
        year_int, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _format_and_validate(day, month, year_int)

    year_match = re.search(_YEAR, lowered)
    if not year_match:
        return None
    year_int = int(year_match.group(0))

    month_num = None
    for name, num in MONTH_TO_NUM.items():
        if re.search(rf"\b{name}[a-z]*\b", lowered):
            month_num = num
            break
    if month_num is None:
        return None

    day_num = None
    for word in ORDINAL_WORDS:  # longest-first, so "twenty-first" matches before "first"
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            day_num = ORDINAL_TO_NUM[word]
            break
    if day_num is None:
        day_match = re.search(_DAY_DIGIT, lowered)
        if day_match:
            day_num = int(day_match.group(0))
    if day_num is None:
        return None

    return _format_and_validate(day_num, month_num, year_int)


def _expand_2digit_year(year_str: str) -> int:
    if len(year_str) == 4:
        return int(year_str)
    two_digit = int(year_str)
    # DOB-appropriate cutoff, not a general-purpose one: 00-30 -> 2000s (a
    # 20-something born after 2000), 31-99 -> 1900s.
    return 2000 + two_digit if two_digit <= 30 else 1900 + two_digit


def _format_and_validate(day: int, month: int, year: int) -> Optional[str]:
    try:
        date(year, month, day)  # raises ValueError for e.g. day=31 in February
    except ValueError:
        return None
    return f"{day:02d}-{month:02d}-{year:04d}"


_DIGIT_DAY_RE = re.compile(_DAY_DIGIT)


def extract_date_components(text: str) -> dict:
    """Pulls out whichever of day/month/year are present in this utterance,
    independently — unlike find_date_span(), this doesn't require all three
    in the SAME utterance. This is what makes "20 September" this turn plus
    a bare "2005" the next turn combine into one complete date instead of
    each half being evaluated (and failing) on its own — see
    ConversationOrchestrator._handle_date_field_failure, which merges this
    against whatever was already captured for the field across turns."""
    lowered = text.lower()
    components: dict = {}

    year_match = re.search(_YEAR, lowered)
    if year_match:
        components["year"] = int(year_match.group(0))

    for name, num in MONTH_TO_NUM.items():
        if re.search(rf"\b{name}[a-z]*\b", lowered):
            components["month"] = num
            break

    for word in ORDINAL_WORDS:  # longest-first, so "twenty-first" matches before "first"
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            components["day"] = ORDINAL_TO_NUM[word]
            break

    if "day" not in components:
        for day_match in re.finditer(_DAY_DIGIT, lowered):
            # Skip a digit run that's actually (part of) the year match —
            # otherwise "2005" alone would misread as day=20.
            if year_match and day_match.start() >= year_match.start() and day_match.end() <= year_match.end():
                continue
            value = int(day_match.group(0))
            if 1 <= value <= 31:
                components["day"] = value
                break

    return components


def merge_date_components(existing: dict, new: dict) -> dict:
    """New values win on conflict — a later turn correcting/completing an
    earlier one is the common case, never the reverse."""
    return {**existing, **new}


def components_to_ddmmyyyy(components: dict) -> Optional[str]:
    if not all(k in components for k in ("day", "month", "year")):
        return None
    return _format_and_validate(components["day"], components["month"], components["year"])


def hint_for_missing_components(components: dict) -> str:
    missing = []
    if "day" not in components:
        missing.append("the day")
    if "month" not in components:
        missing.append("the month")
    if "year" not in components:
        missing.append("the year")
    return "Got it — could you also give me " + " and ".join(missing) + "?"


def partial_date_hint(text: str) -> Optional[str]:
    """If the utterance clearly contains SOME but not all of day/month/year
    (and a full date pattern didn't already match), name specifically what's
    still needed instead of a generic retry prompt."""
    if matches_date(text):
        return None
    lowered = text.lower()
    has_month = any(re.search(rf"\b{m}[a-z]*\b", lowered) for m in MONTH_NAMES)
    has_year = bool(re.search(_YEAR, lowered))
    has_day = bool(_DIGIT_DAY_RE.search(lowered)) or any(
        re.search(rf"\b{re.escape(w)}\b", lowered) for w in ORDINAL_WORDS
    )

    present = sum([has_month, has_year, has_day])
    if present == 0:
        return None  # nothing date-shaped at all — a normal clarification is more appropriate

    missing = []
    if not has_day:
        missing.append("the day")
    if not has_month:
        missing.append("the month")
    if not has_year:
        missing.append("the year")
    if not missing:
        return None
    return "Got it — could you also give me " + " and ".join(missing) + "?"
