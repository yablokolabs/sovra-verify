"""Normalisation with a mapping back to the original text.

Models describe the same predicate in many words ("Payment term", "Settlement
period", "Net days"). Pairing on raw strings silently misses real conflicts, so
predicates, units and values are normalised into a small controlled vocabulary
while the original wording is always kept on the claim for display.

Normalisation never edits canonical text: it only produces comparable keys.
"""

from __future__ import annotations

import re

#: Ordered. The first matching pattern wins, so put specific patterns first.
PREDICATE_PATTERNS: tuple[tuple[str, str], ...] = (
    # Checked first: a value the application reclassified as a clause reference
    # must keep that key rather than falling through to a numeric predicate.
    ("clause_reference", r"^clause\s*reference$"),
    ("payment_period", r"pay(ment)?\s*(term|period|days|timeline|window|deadline|due|obligation|schedule)|settle?ment\s*(period|term|time)|net\s*(terms|days)|payable\s*within|due\s*(within|date)|days?\s*(of|after|from)\s*(the\s*)?invoice|grace\s*period|payment\s*run"),
    ("payment_method", r"pay(ment)?\s*method|bank\s*transfer|paid\s*by|remittance"),
    ("conversion_rate", r"conversion|exchange\s*rate|reference\s*rate|converted"),
    ("currency", r"currency|denominat|\bchf\b|\beur\b|\busd\b"),
    ("dispute_window", r"disput|withhold|notice\s*period|objection"),
    ("approval_condition", r"approval|three[- ]way\s*match|release(d)?\s*(for\s*payment|condition)?|goods\s*receipt"),
    ("exception", r"exception|carve[- ]?out|excluded|does\s*not\s*apply|unless"),
    ("effective_date", r"effective\s*date|takes?\s*effect|in\s*force|start\s*date|commence"),
    ("term_end", r"term\s*end|expir|end\s*date|until|termination\s*date"),
    ("scope", r"scope|applies\s*to|covers?|governs|appl(?:ies|icable)\s*to"),
    ("amount", r"amount|total|value|price|cost|fee|surcharge|balance"),
    ("rate", r"\brate\b|percent|interest"),
    ("quantity", r"quantity|units|volume|tonnes|pallets"),
    ("governing_law", r"governing\s*law|jurisdiction|venue"),
    ("notice_period", r"notice\s*period|days'?\s*notice|cancel"),
)

#: Separators that appear in machine-style predicate names such as
#: ``payment_period`` or ``payment-release-condition``.
_PREDICATE_SEPARATORS = re.compile(r"[_\-/]+")

UNIT_ALIASES: dict[str, str] = {
    "day": "days",
    "days": "days",
    "calendar day": "days",
    "working day": "working_days",
    "working days": "working_days",
    "business day": "working_days",
    "week": "weeks",
    "weeks": "weeks",
    "month": "months",
    "months": "months",
    "year": "years",
    "years": "years",
    "%": "percent",
    "percent": "percent",
    "percentage": "percent",
    "chf": "CHF",
    "eur": "EUR",
    "usd": "USD",
    "gbp": "GBP",
    "n/a": "unknown",
    "none": "unknown",
    "unspecified": "unknown",
    "": "unknown",
}

_UNIT_UNKNOWN = {"unknown", "not stated", "not specified", "n/a", "na", "none", "-"}

_LEADING_NUMBER = re.compile(r"^\s*(?:approx\.?\s*)?([0-9][0-9 ,\.']*)\s*(.*)$")
_DAYS = re.compile(r"(\d{1,5})\s*(?:calendar\s+|working\s+|business\s+)?days?", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def normalize_predicate(value: str) -> str:
    """Map free-text predicates onto the controlled vocabulary.

    Machine-style names (``payment_period``) and prose ("Settlement period") are
    folded together first, so both the rule extractor and a model land on the
    same key for the same concept.
    """
    text = _PREDICATE_SEPARATORS.sub(" ", (value or "").strip().lower())
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "unknown"
    for key, pattern in PREDICATE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return key
    return f"other:{text[:40]}"


def normalize_unit(value: str) -> str:
    raw = (value or "").strip().lower()
    # "n/a" and "-" are checked before separator folding, otherwise "-" would
    # become whitespace and slip past the unstated-unit test.
    if not raw or raw in _UNIT_UNKNOWN:
        return "unknown"
    text = re.sub(r"\s+", " ", _PREDICATE_SEPARATORS.sub(" ", raw)).strip()
    if not text or text in _UNIT_UNKNOWN:
        return "unknown"
    if text in UNIT_ALIASES:
        return UNIT_ALIASES[text]
    for key, canonical in UNIT_ALIASES.items():
        if key and re.search(rf"\b{re.escape(key)}\b", text):
            return canonical
    return f"other:{text[:20]}"


def normalize_value(value: str, unit: str = "unknown") -> str:
    """A comparable form of a value. The raw text is always kept separately."""
    text = (value or "").strip()
    if not text:
        return "unknown"
    lowered = text.lower()
    if lowered in _UNIT_UNKNOWN:
        return "unknown"

    days = _DAYS.search(text)
    if days:
        return f"{int(days.group(1))} days"

    date = _DATE.search(text)
    if date:
        return date.group(1)

    match = _LEADING_NUMBER.match(text)
    if match:
        raw_number = match.group(1).replace(" ", "").replace("'", "").replace(",", "")
        try:
            number = float(raw_number)
        except ValueError:
            return lowered[:60]
        trailing = match.group(2).strip().lower()
        if trailing.startswith("%") or "percent" in trailing:
            return f"{number:g}%"
        if trailing in ("", "chf", "eur", "usd", "gbp"):
            return f"{number:g}"
        return f"{number:g} {trailing[:20]}"

    return lowered[:60]


def values_differ(left: str, right: str, *, left_unit: str, right_unit: str) -> bool:
    """True when two normalised values are genuinely different."""
    a = normalize_value(left, left_unit)
    b = normalize_value(right, right_unit)
    if a == "unknown" or b == "unknown":
        return False
    return a != b


def normalize_subject(value: str) -> str:
    """Entities are matched leniently; unknown never blocks a comparison."""
    text = (value or "").strip().lower()
    if text in _UNIT_UNKNOWN or text in {"the buyer", "the supplier", "buyer", "supplier"}:
        return "unknown"
    text = re.sub(r"\b(ag|gmbh|ltd|limited|sa|sarl|sàrl|inc|llc|bv|se|plc)\b", "", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:60] or "unknown"


def normalize_date(value: str) -> str:
    match = _DATE.search(value or "")
    return match.group(1) if match else "unknown"


def subjects_compatible(left: str, right: str) -> bool:
    """Unknown entities stay comparable; two different known entities do not."""
    a, b = normalize_subject(left), normalize_subject(right)
    if a == "unknown" or b == "unknown":
        return True
    return a == b or a in b or b in a
