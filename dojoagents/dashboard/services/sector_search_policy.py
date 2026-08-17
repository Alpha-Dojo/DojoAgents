"""Sector taxonomy keyword search policy (tokenize + controlled synonym expansion).

Search-ranking policy only — not core domain path semantics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Concept → alternate search terms used only by taxonomy keyword search.
SECTOR_CONCEPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "具身智能": ("机器人", "robotics", "robot", "自动化", "automation", "机械", "embodied"),
    "embodied ai": ("机器人", "robotics", "robot", "automation", "具身"),
    "embodied intelligence": ("机器人", "robotics", "robot", "automation"),
    "人工智能": ("ai", "artificial intelligence", "机器学习", "machine learning", "深度学习"),
    "ai": ("人工智能", "artificial intelligence", "机器学习", "machine learning"),
    "半导体": ("芯片", "chip", "semiconductor", "集成电路"),
    "chip": ("半导体", "芯片", "semiconductor"),
    "新能源": ("光伏", "solar", "风电", "wind", "储能", "battery", "electric vehicle", "ev"),
    "高息": ("dividend", "utility", "reit", "银行", "bank"),
    "机器人": ("robotics", "robot", "自动化", "automation", "具身智能"),
}

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+(?:'[a-zA-Z0-9]+)?")

# User-token L3 scores
SCORE_L3_EXACT = 100
SCORE_L3_PREFIX = 90
SCORE_L3_WHOLE_WORD = 85
SCORE_L3_CJK_CONTAINS = 70
# Synonym-capped L3 scores
SCORE_L3_SYN_EXACT = 75
SCORE_L3_SYN_PREFIX = 68
SCORE_L3_SYN_WHOLE_WORD = 65
SCORE_L3_SYN_CJK_CONTAINS = 55
# L2 / L1 scale relative to L3 band
_L2_FACTOR = 0.6
_L1_FACTOR = 0.3

BEST_MATCH_MIN_SCORE = 85
BEST_MATCH_MARGIN = 10


@dataclass(frozen=True)
class SearchTerm:
    text: str
    source: str  # "user" | "synonym"


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def tokenize_sector_search_query(query: str) -> list[str]:
    """Split a mixed zh/en query into CJK runs and ASCII words."""
    text = str(query or "").strip()
    if not text:
        return []
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0).strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def term_appears_in(term: str, text: str) -> bool:
    """CJK substring or ASCII whole-word / phrase containment."""
    needle = str(term or "").strip()
    haystack = str(text or "").strip()
    if not needle or not haystack:
        return False
    if _has_cjk(needle):
        return needle in haystack

    needle_l = needle.lower()
    haystack_l = haystack.lower()
    if needle_l == haystack_l:
        return True
    if " " in needle_l:
        return needle_l in haystack_l
    return re.search(rf"(?<![a-z0-9]){re.escape(needle_l)}(?![a-z0-9])", haystack_l) is not None


def _ascii_whole_word(term: str, label: str) -> bool:
    needle = term.lower().strip()
    haystack = label.lower().strip()
    if not needle or not haystack or _has_cjk(needle):
        return False
    if " " in needle:
        return needle in haystack and needle != haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack)) and needle != haystack


def match_label_score(term: str, label: str, *, source: str = "user") -> int:
    """Score one search term against one label. 0 = no hit."""
    needle = str(term or "").strip()
    normalized = str(label or "").strip()
    if not needle or not normalized:
        return 0

    needle_l = needle.lower()
    label_l = normalized.lower()
    syn = source == "synonym"

    if label_l == needle_l:
        return SCORE_L3_SYN_EXACT if syn else SCORE_L3_EXACT

    if _has_cjk(needle):
        if label_l.startswith(needle_l):
            return SCORE_L3_SYN_PREFIX if syn else SCORE_L3_PREFIX
        if needle_l in label_l:
            return SCORE_L3_SYN_CJK_CONTAINS if syn else SCORE_L3_CJK_CONTAINS
        return 0

    # ASCII: exact already handled; prefix on first word or whole label start
    if label_l.startswith(needle_l) and (
        len(label_l) == len(needle_l) or not label_l[len(needle_l)].isalnum()
    ):
        return SCORE_L3_SYN_PREFIX if syn else SCORE_L3_PREFIX
    if _ascii_whole_word(needle, normalized):
        return SCORE_L3_SYN_WHOLE_WORD if syn else SCORE_L3_WHOLE_WORD
    return 0


def scale_score_for_level(score: int, level: str) -> int:
    if score <= 0:
        return 0
    if level == "L3":
        return score
    if level == "L2":
        return max(1, int(round(score * _L2_FACTOR)))
    if level == "L1":
        return max(1, int(round(score * _L1_FACTOR)))
    return score


def expand_sector_search_terms(query: str) -> list[SearchTerm]:
    """Tokenize query and optionally expand concept synonyms (demoted source)."""
    needle = str(query or "").strip()
    if not needle:
        return []

    tokens = tokenize_sector_search_query(needle)
    terms: list[SearchTerm] = []
    seen: set[str] = set()

    def _add(text: str, source: str) -> None:
        key = text.strip().lower()
        if not text.strip() or key in seen:
            return
        seen.add(key)
        terms.append(SearchTerm(text=text.strip(), source=source))

    _add(needle, "user")
    for token in tokens:
        _add(token, "user")

    triggered_keys: list[str] = []
    for key, synonyms in SECTOR_CONCEPT_SYNONYMS.items():
        hit = False
        for token in tokens or [needle]:
            if term_appears_in(key, token) or term_appears_in(token, key):
                hit = True
                break
            for syn in synonyms:
                if term_appears_in(syn, token) or term_appears_in(token, syn):
                    hit = True
                    break
            if hit:
                break
        if hit:
            triggered_keys.append(key)

    for key in triggered_keys:
        _add(key, "synonym")
        for syn in SECTOR_CONCEPT_SYNONYMS[key]:
            _add(syn, "synonym")

    return terms


def expand_sector_search_queries(query: str) -> list[str]:
    """Back-compat: ordered unique text terms (user tokens first, then synonyms)."""
    return [term.text for term in expand_sector_search_terms(query)]


def pick_best_match(
    items: list[dict],
    *,
    min_score: int = BEST_MATCH_MIN_SCORE,
    margin: int = BEST_MATCH_MARGIN,
) -> dict | None:
    if not items:
        return None
    top = items[0]
    score = int(top.get("match_score") or 0)
    level = str(top.get("matched_level") or "")
    # Sole L3 hit that at least weakly matched a user token is unambiguous.
    if len(items) == 1 and level in {"L3", "path_id"} and score >= SCORE_L3_CJK_CONTAINS:
        return top
    if score < min_score:
        return None
    if len(items) >= 2:
        second = int(items[1].get("match_score") or 0)
        if score - second < margin and score < SCORE_L3_EXACT:
            return None
    if level not in {"L3", "path_id"} and score < SCORE_L3_EXACT:
        return None
    return top
