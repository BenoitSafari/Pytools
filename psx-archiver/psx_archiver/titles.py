"""Title cleaning and formatting utilities."""

import re

UPPER_WORDS = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "X4", "X5", "X6"}
LOWER_WORDS = {
    "OF",
    "THE",
    "AND",
    "IN",
    "TO",
    "A",
    "AN",
    "AT",
    "BY",
    "FOR",
    "ON",
    "OR",
    "IS",
    "IT",
    "VS",
}


def title_case(s):
    """Convert UPPERCASE title to Title Case, preserving roman numerals."""
    s = s.replace("\u00e9", "e").replace("\u00c9", "E")

    words = s.split()
    result = []
    for i, word in enumerate(words):
        w_upper = word.upper()
        if w_upper in UPPER_WORDS:
            result.append(w_upper)
        elif w_upper in LOWER_WORDS and i > 0:
            result.append(word.lower())
        else:
            parts = word.split("-")
            tc_parts = []
            for p in parts:
                if p.upper() in UPPER_WORDS:
                    tc_parts.append(p.upper())
                elif len(p) <= 1:
                    tc_parts.append(p.upper())
                else:
                    tc_parts.append(p[0].upper() + p[1:].lower())
            result.append("-".join(tc_parts))
    return " ".join(result)


def clean_title(title):
    """Clean a DB title for use as a filename."""
    t = title_case(title)
    t = t.replace(":", " -")
    t = t.replace("/", "-")
    t = t.replace("&amp;", "And").replace(" & ", " And ")
    for c in '?*"<>|':
        t = t.replace(c, "")
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace(" ", "_")
    t = t.replace("\u2019", "'")
    return t
