#!/usr/bin/env python3
"""Deterministic JANUS guestbook respect filter.

Narrow policy:
    JANUS_MENTION && PROFANITY_OR_DIRECT_INSULT => REJECT

The filter intentionally does NOT reject ordinary criticism such as
"JANUS is wrong", "I disagree with JANUS", or "JANUS failed this test".
It is lexical and conservative, not a sentiment model.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class FilterResult:
    accepted: bool
    reason: str
    janus_mentioned: bool
    prohibited_language_found: bool
    matched_term: str | None = None


# Basic leetspeak / confusable cleanup used only for matching.
_CHAR_MAP = str.maketrans(
    {
        "@": "a",
        "$": "s",
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        # Cyrillic lookalikes commonly mixed into Latin text.
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "к": "k",
        "м": "m",
        "т": "t",
        "в": "b",
    }
)

# Direct profanity / insult roots. These are only actionable when JANUS is
# mentioned in the same message. Ordinary disagreement words are excluded.
_PROHIBITED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fuck", re.compile(r"f+u+c+k+", re.I)),
    ("shit", re.compile(r"s+h+i+t+", re.I)),
    ("bitch", re.compile(r"b+i+t+c+h+", re.I)),
    ("cunt", re.compile(r"c+u+n+t+", re.I)),
    ("asshole", re.compile(r"a+s+s+h+o+l+e+", re.I)),
    ("idiot", re.compile(r"i+d+i+o+t+", re.I)),
    ("moron", re.compile(r"m+o+r+o+n+", re.I)),
    ("stupid", re.compile(r"s+t+u+p+i+d+", re.I)),
    ("dumbass", re.compile(r"d+u+m+b+a+s+s+", re.I)),
    ("бляд", re.compile(r"б+л+[яа]+[дт]+", re.I)),
    ("сука", re.compile(r"с+у+к+[аои]+", re.I)),
    ("хуй", re.compile(r"х+[уy]+[йияеё]+", re.I)),
    ("пизд", re.compile(r"п+и+з+д+", re.I)),
    ("еб", re.compile(r"[её]+б+(?:а|у|л|н|т|ё|е|и|ы)", re.I)),
    ("йоб", re.compile(r"й+о+б+", re.I)),
    ("мудак", re.compile(r"м+у+д+[ао]+к+", re.I)),
    ("мраз", re.compile(r"м+р+[ао]+з+", re.I)),
    ("дебил", re.compile(r"д+е+б+и+л+", re.I)),
    ("идиот", re.compile(r"и+д+и+о+т+", re.I)),
    ("урод", re.compile(r"у+р+о+д+", re.I)),
    ("твар", re.compile(r"т+в+[ао]+р+", re.I)),
    ("ублюд", re.compile(r"у+б+л+[юу]+д+", re.I)),
    ("говн", re.compile(r"г+о+в+н+", re.I)),
    ("дерьм", re.compile(r"д+е+р+[ьъ]*м+", re.I)),
    ("тупой", re.compile(r"т+у+п+(?:о+й+|а+я+|о+е+|и+ц+а+)", re.I)),
    ("ничтож", re.compile(r"н+и+ч+т+о+ж+", re.I)),
    ("довбойоб", re.compile(r"д+о+в+б+о+й+о+б+", re.I)),
)


def _nfkc_lower(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower().replace("ё", "е")


def _compact(text: str) -> str:
    """Remove separators so simple punctuation/spacing evasion is still matched."""
    normalized = _nfkc_lower(text).translate(_CHAR_MAP)
    return "".join(ch for ch in normalized if ch.isalnum())


def _compact_cyrillic(text: str) -> str:
    """Compact without Latin-confusable conversion so Янус remains detectable."""
    normalized = _nfkc_lower(text)
    return "".join(ch for ch in normalized if ch.isalnum())


def contains_janus_mention(text: str) -> bool:
    cyr = _compact_cyrillic(text)
    lat = _compact(text)

    if "янус" in cyr:
        return True

    # JANUS, IANUS (historical Latin spelling), and a simple Я/J mixed form.
    if any(token in lat for token in ("janus", "ianus", "yanus")):
        return True

    # Explicit mixed-script normalization for the Cyrillic spelling.
    translit = _nfkc_lower(text)
    translit = translit.translate(
        str.maketrans({"я": "ya", "н": "n", "у": "u", "с": "s", "а": "a"})
    )
    translit = "".join(ch for ch in translit if ch.isalnum())
    return "yanus" in translit


def find_prohibited_language(text: str) -> str | None:
    # Evaluate both a readable normalized stream and a separator-free stream.
    readable = _nfkc_lower(text)
    compact = _compact_cyrillic(text)
    latin_compact = _compact(text)

    candidates = (readable, compact, latin_compact)
    for label, pattern in _PROHIBITED_PATTERNS:
        if any(pattern.search(candidate) for candidate in candidates):
            return label
    return None


def evaluate_message(text: str) -> FilterResult:
    janus = contains_janus_mention(text)
    matched = find_prohibited_language(text)
    prohibited = matched is not None

    if janus and prohibited:
        return FilterResult(
            accepted=False,
            reason="JANUS_MENTION_WITH_PROFANITY_OR_DIRECT_INSULT",
            janus_mentioned=True,
            prohibited_language_found=True,
            matched_term=matched,
        )

    return FilterResult(
        accepted=True,
        reason="PASS_NARROW_RESPECT_FILTER",
        janus_mentioned=janus,
        prohibited_language_found=prohibited,
        matched_term=matched,
    )


def _selftest() -> None:
    reject = [
        "Janus is an idiot",
        "JANUS fuck you",
        "J A N U S — f.u.c.k",
        "Янус блять",
        "Я.Н.У.С — б л я т ь",
        "Янус тупой",
        "Jаnus idiot",  # Cyrillic а in otherwise Latin JANUS.
        "IANUS is shit",
    ]
    allow = [
        "JANUS is wrong about this result.",
        "I disagree with JANUS.",
        "JANUS failed this test and should preserve the negative result.",
        "Я не согласен с Янусом.",
        "Янус, здесь ошибка в статистике.",
        "This test is shit, but I am not talking about the project name.",
        "Negative results are evidence.",
    ]

    for message in reject:
        result = evaluate_message(message)
        assert not result.accepted, (message, result)

    for message in allow:
        result = evaluate_message(message)
        assert result.accepted, (message, result)

    print("JANUS_GUESTBOOK_RESPECT_FILTER_SELFTEST=PASS")
    print(f"REJECT_CASES={len(reject)}")
    print(f"ALLOW_CASES={len(allow)}")
    print("CRITICISM_ALLOWED=TRUE")
    print("JANUS_PLUS_PROFANITY_REJECTED=TRUE")


if __name__ == "__main__":
    _selftest()
