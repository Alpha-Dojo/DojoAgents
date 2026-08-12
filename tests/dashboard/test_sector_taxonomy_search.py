"""Regression tests for sector taxonomy lexical search + repair contract."""

from __future__ import annotations

from dojoagents.dashboard.services.sector_search_policy import (
    expand_sector_search_queries,
    expand_sector_search_terms,
    match_label_score,
    pick_best_match,
    term_appears_in,
)
from dojoagents.harnesses.built_in.financial.policies.sector_context import (
    repair_sector_tool_arguments,
)


def test_tokenize_keeps_cjk_and_ascii_words() -> None:
    terms = expand_sector_search_terms("航空 airlines 航空运输")
    texts = [term.text for term in terms]
    assert "航空" in texts
    assert "airlines" in texts
    assert "航空运输" in texts
    assert all(term.source == "user" for term in terms)


def test_airlines_does_not_expand_to_ai() -> None:
    expanded = expand_sector_search_queries("航空 airlines 航空运输")
    assert "ai" not in {item.lower() for item in expanded}
    assert "人工智能" not in expanded


def test_standalone_ai_still_expands() -> None:
    texts = {term.text for term in expand_sector_search_terms("ai")}
    assert "人工智能" in texts
    assert any(term.source == "synonym" for term in expand_sector_search_terms("ai"))


def test_ascii_whole_word_match_not_substring() -> None:
    assert term_appears_in("ai", "airlines") is False
    assert match_label_score("ai", "Air Transport") == 0
    assert match_label_score("ai", "AI Foundation Models") >= 85
    assert match_label_score("航空运输", "航空运输") == 100
    assert match_label_score("航空", "航空运输") == 90


def test_synonym_score_capped_below_user_exact() -> None:
    user = match_label_score("航空运输", "航空运输", source="user")
    syn = match_label_score("航空运输", "航空运输", source="synonym")
    assert user == 100
    assert syn == 75
    assert syn < user


def test_pick_best_match_requires_confidence() -> None:
    strong = {
        "sector_path_id": "109/115/116",
        "match_score": 100,
        "matched_level": "L3",
    }
    weak = {
        "sector_path_id": "1/23/28",
        "match_score": 70,
        "matched_level": "L3",
    }
    assert pick_best_match([strong, weak]) == strong
    assert pick_best_match([weak]) == weak  # sole weak L3 hit is unambiguous
    assert pick_best_match(
        [
            {"sector_path_id": "a", "match_score": 60, "matched_level": "L3"},
        ]
    ) is None
    tied = [
        {"sector_path_id": "a", "match_score": 90, "matched_level": "L3"},
        {"sector_path_id": "b", "match_score": 85, "matched_level": "L3"},
    ]
    assert pick_best_match(tied) is None


def test_repair_keeps_air_transport_hit_over_wrong_best_match() -> None:
    invocation = {
        "_dojo_sector_best_match": {
            "sector_path_id": "1/23/28",
            "level1_id": "1",
            "level2_id": "23",
            "level3_id": "28",
        },
        "_dojo_sector_search_hit_paths": ("1/23/28", "109/115/116"),
    }
    args = {
        "sector_path_id": "109/115/116",
        "level1_id": "109",
        "level2_id": "115",
        "level3_id": "116",
        "market": "us",
    }
    assert repair_sector_tool_arguments("filter_sector_constituents", args, invocation) == args
