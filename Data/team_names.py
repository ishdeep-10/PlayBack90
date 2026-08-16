"""Fuzzy team-name matching shared by provider discovery and ingestion validation.

Club names vary between official schedule providers and WhoScored (e.g. "Real
Racing Club de Santander" vs "Racing Santander"), so exact/substring matching
is too strict. Generic club-name filler words are stripped before comparing.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata

CLUB_TOKENS = {
    "afc",
    "cf",
    "fc",
    "football",
    "club",
    "sc",
    "real",
    "de",
    "cd",
    "rc",
    "rcd",
    "ud",
    "cp",
    "sd",
}


def normalized_team_name(value: object) -> str:
    ascii_text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", ascii_text.lower().replace("&", " and "))
    meaningful = [token for token in tokens if token not in CLUB_TOKENS]
    return " ".join(meaningful or tokens)


def team_name_similarity(left: object, right: object) -> float:
    left_text = normalized_team_name(left)
    right_text = normalized_team_name(right)
    if not left_text or not right_text:
        return 0.0
    direct = SequenceMatcher(None, left_text, right_text).ratio()
    token_sorted = SequenceMatcher(
        None,
        " ".join(sorted(left_text.split())),
        " ".join(sorted(right_text.split())),
    ).ratio()
    return max(direct, token_sorted)


def team_names_match(expected: object, actual: object, *, minimum_score: float = 0.72) -> bool:
    left_text = normalized_team_name(expected)
    right_text = normalized_team_name(actual)
    if not left_text or not right_text:
        return False
    if left_text == right_text or left_text in right_text or right_text in left_text:
        return True
    return team_name_similarity(expected, actual) >= minimum_score
