"""Keyword ideas: autocomplete + top results + an *estimated* demand/competition score."""
from __future__ import annotations

import math
from datetime import datetime

from . import metrics
from .youtube import YouTubeClient

DISCLAIMER = (
    "ESTIMATE ONLY - this is NOT real YouTube search volume. 'Demand' is inferred from how fast "
    "the current top-ranking videos are gaining views (views/day); 'competition' from the size of "
    "the channels ranking. Autocomplete shows what people type, not how often."
)


def score(vpd_median: float, sub_median: float | None) -> dict:
    """demand: 20*log10(1+median views/day) capped at 100 (1k/day ~ 60, 100k/day = 100).
    competition: 15*log10(1+median channel subs) capped at 100 (10k subs ~ 60, 1M ~ 90).
    opportunity = demand - 0.5*competition (clamped 0-100)."""
    demand = min(100.0, 20 * math.log10(1 + max(vpd_median, 0)))
    comp = min(100.0, 15 * math.log10(1 + sub_median)) if sub_median is not None else None
    opp = max(0.0, min(100.0, demand - 0.5 * (comp if comp is not None else 50)))
    return {
        "demand_score": round(demand),
        "competition_score": None if comp is None else round(comp),
        "opportunity_score": round(opp),
    }


def keyword_ideas(
    yt: YouTubeClient,
    seed: str,
    max_keywords: int = 5,
    results_per_keyword: int = 5,
    now: datetime | None = None,
) -> dict:
    suggestions = yt.autocomplete(seed)
    keywords = [seed] + [s for s in suggestions if s.lower() != seed.lower()]
    keywords = keywords[:max_keywords]
    rows = []
    for kw in keywords:
        ids = yt.search_videos(kw, results_per_keyword)
        vids = metrics.enrich(yt.get_videos(ids), now) if ids else []
        subs = yt.get_channels_by_ids([v["channel_id"] for v in vids if v["channel_id"]])
        sub_vals = [subs[v["channel_id"]]["subscribers"] for v in vids
                    if v["channel_id"] in subs and subs[v["channel_id"]]["subscribers"] is not None]
        vpd = metrics.median([v["views_per_day"] for v in vids])
        sub_med = metrics.median(sub_vals) if sub_vals else None
        small_winners = [
            v["id"] for v in vids
            if v["channel_id"] in subs and (subs[v["channel_id"]]["subscribers"] or 0) > 0
            and v["views"] > 10 * subs[v["channel_id"]]["subscribers"]
        ]
        rows.append({
            "keyword": kw,
            **score(vpd, sub_med),
            "median_views_per_day": round(vpd, 1),
            "median_channel_subs": None if sub_med is None else int(sub_med),
            "small_channel_breakouts": len(small_winners),
            "top_results": [
                {"id": v["id"], "title": v["title"], "channel": v["channel_title"],
                 "channel_subs": subs.get(v["channel_id"], {}).get("subscribers"),
                 "views": v["views"], "views_per_day": v["views_per_day"], "age_days": v["age_days"]}
                for v in vids
            ],
        })
    rows.sort(key=lambda r: r["opportunity_score"], reverse=True)
    return {
        "seed": seed,
        "disclaimer": DISCLAIMER,
        "autocomplete_suggestions": suggestions,
        "quota_note": f"Each keyword costs ~100 API units (search.list); analysed {len(keywords)}. Cached 24h.",
        "keywords": rows,
    }
