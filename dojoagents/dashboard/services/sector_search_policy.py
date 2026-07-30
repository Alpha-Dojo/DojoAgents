"""Sector taxonomy keyword search policy (synonym expansion).

This is search-ranking policy, not core domain path semantics.
Keep concept synonym tables here so resolve/path validation stays free of
agent/playbook vocabulary and stock-picking dictionaries.
"""

from __future__ import annotations

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


def expand_sector_search_queries(query: str) -> list[str]:
    """Expand a taxonomy keyword with configured concept synonyms."""
    needle = str(query or "").strip()
    if not needle:
        return []
    lowered = needle.lower()
    expanded: list[str] = [needle]
    for key, synonyms in SECTOR_CONCEPT_SYNONYMS.items():
        key_lower = key.lower()
        if key_lower == lowered or key_lower in lowered or lowered in key_lower:
            for term in synonyms:
                if term not in expanded:
                    expanded.append(term)
            if key not in expanded:
                expanded.append(key)
            continue
        for term in synonyms:
            term_lower = term.lower()
            if term_lower == lowered or term_lower in lowered or lowered in term_lower:
                if key not in expanded:
                    expanded.append(key)
                for related in synonyms:
                    if related not in expanded:
                        expanded.append(related)
                break
    return expanded
