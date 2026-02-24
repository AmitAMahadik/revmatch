"""Build recommendation cards for chat/find-next responses. No LLM calls."""

from __future__ import annotations


def _build_item_reason(scores: dict | None) -> str:
    """Generate a deterministic sentence based on high character scores.

    Scores are on a 0–10 scale. We surface up to two strongest dimensions.
    """
    if not scores or not isinstance(scores, dict):
        return ""

    # Treat >=8.5 as "high" for a concise, meaningful reason.
    high_threshold = 8.5
    labels = {
        "revHappiness": "rev-happiness",
        "dailyCompliance": "daily-compliance",
        "acousticDrama": "acoustic-drama",
        "steeringFeel": "steering-feel",
        "trackReadiness": "track-readiness",
        "depreciationStability": "depreciation-stability",
    }

    keys = (
        "revHappiness",
        "dailyCompliance",
        "acousticDrama",
        "steeringFeel",
        "trackReadiness",
        "depreciationStability",
    )

    scored: list[tuple[str, float]] = []
    for k in keys:
        v = scores.get(k)
        if isinstance(v, (int, float)) and float(v) >= high_threshold:
            scored.append((k, float(v)))

    scored.sort(key=lambda x: -x[1])
    if not scored:
        return ""

    top = scored[:2]
    names = [labels.get(k, k) for k, _ in top]
    if len(names) == 1:
        return f"Strong {names[0]}."
    return f"Strong {names[0]} and {names[1]}."


def _format_subtitle(item: dict) -> str:
    """Build subtitle: drivenWheels • hp hp • redline rpm."""
    parts = []
    if item.get("drivenWheels"):
        parts.append(str(item["drivenWheels"]))
    # Include transmission types when present (e.g., Manual/PDK)
    tx = item.get("transmissions")
    if isinstance(tx, list) and tx:
        types = []
        for t in tx:
            if isinstance(t, dict) and t.get("type"):
                types.append(str(t["type"]))
        if types:
            # De-duplicate while preserving order
            seen = set()
            uniq = []
            for t in types:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)
            parts.append("/".join(uniq))
    if item.get("hp") is not None:
        parts.append(f"{item['hp']} hp")
    if item.get("redline") is not None:
        parts.append(f"{item['redline']} rpm")
    return " • ".join(parts)


def build_recommendation_cards(items: list[dict], parsed_query: dict) -> list[dict]:
    """Build a single recommendation_list card from items and parsed query.

    Returns one card:
      - type: "recommendation_list"
      - title: "Top matches"
      - query: parsed_query
      - items: list of card items with trimId, title, subtitle, scores, reason
    """
    card_items = []
    for item in items:
        trim_name = item.get("trimName") or ""
        year = item.get("year")
        year_str = f" ({year})" if year is not None else ""
        title = f"{trim_name}{year_str}"

        scores = item.get("scores")
        scores_subset = {}
        if scores and isinstance(scores, dict):
            for k in (
                "revHappiness",
                "dailyCompliance",
                "acousticDrama",
                "steeringFeel",
                "trackReadiness",
                "depreciationStability",
            ):
                v = scores.get(k)
                if v is not None:
                    scores_subset[k] = v

        card_items.append(
            {
                "trimId": item.get("trimId"),
                "title": title,
                "subtitle": _format_subtitle(item),
                "scores": scores_subset if scores_subset else None,
                "reason": _build_item_reason(scores),
            }
        )

    return [
        {
            "type": "recommendation_list",
            "title": "Top matches",
            "query": parsed_query,
            "items": card_items,
        }
    ]
