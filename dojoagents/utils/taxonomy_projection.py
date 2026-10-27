"""Framework-neutral taxonomy response projections."""

from __future__ import annotations

from typing import Any, Mapping


def _locale_text(value: Any, locale: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return str(value.get(locale) or value.get("en" if locale == "zh" else "zh") or "").strip()
    primary = getattr(value, locale, None)
    fallback = getattr(value, "en" if locale == "zh" else "zh", None)
    return str(primary or fallback or value).strip()


def project_taxonomy_l3_catalog(payload: Mapping[str, Any] | None, *, locale: str = "zh") -> dict[str, Any]:
    resolved_locale = "en" if str(locale).strip().lower() == "en" else "zh"
    raw = payload if isinstance(payload, Mapping) else {}
    items: list[dict[str, str]] = []
    roots = raw.get("tree") if isinstance(raw.get("tree"), list) and raw.get("tree") else raw.get("level_1") or []
    for l1 in roots:
        if not isinstance(l1, Mapping):
            continue
        l1_id = str(l1.get("level1_id") or l1.get("id") or "").strip()
        for l2 in l1.get("children") or l1.get("level_2") or []:
            if not isinstance(l2, Mapping):
                continue
            l2_id = str(l2.get("level2_id") or l2.get("id") or "").strip()
            for l3 in l2.get("children") or l2.get("level_3") or []:
                if not isinstance(l3, Mapping):
                    continue
                l3_id = str(l3.get("level3_id") or l3.get("id") or "").strip()
                if not (l1_id and l2_id and l3_id):
                    continue
                items.append({
                    "sector_path_id": f"{l1_id}/{l2_id}/{l3_id}",
                    "name": _locale_text(l3.get("name"), resolved_locale),
                    "description": _locale_text(l3.get("definition", l3.get("description")), resolved_locale),
                })
    return {"locale": resolved_locale, "count": len(items), "items": items}


__all__ = ["project_taxonomy_l3_catalog"]
