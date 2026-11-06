"""Pure maths over normalized video dicts (see youtube.YouTubeClient)."""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from .youtube import parse_dt


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def age_days(published_at: str, now: datetime | None = None) -> float:
    return max((_now(now) - parse_dt(published_at)).total_seconds() / 86400, 0.0)


def enrich(videos: list[dict], now: datetime | None = None) -> list[dict]:
    """Add age_days, views_per_day, engagement_rate (likes+comments / views)."""
    out = []
    for v in videos:
        a = age_days(v["published_at"], now)
        views = v["views"]
        out.append(
            {
                **v,
                "age_days": round(a, 1),
                "views_per_day": round(views / max(a, 1.0), 1),
                "engagement_rate": round((v["likes"] + v["comments"]) / views, 4) if views else 0.0,
                "format": "short" if v["is_short"] else "long",
            }
        )
    return out


def median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def channel_stats(videos: list[dict], now: datetime | None = None) -> dict:
    """Summary metrics for a list of (enriched or raw) videos, newest first or any order."""
    if not videos:
        return {"videos_analyzed": 0}
    vids = enrich(videos, now) if "views_per_day" not in videos[0] else videos
    views = [v["views"] for v in vids]
    dates = sorted(parse_dt(v["published_at"]) for v in vids)
    span_days = (dates[-1] - dates[0]).total_seconds() / 86400
    # n videos span n-1 gaps; cadence = videos per week over the observed window.
    per_week = round((len(vids) - 1) / (span_days / 7), 2) if len(vids) > 1 and span_days > 0 else None
    shorts = sum(1 for v in vids if v["is_short"])
    return {
        "videos_analyzed": len(vids),
        "median_views": int(median(views)),
        "mean_views": int(sum(views) / len(views)),
        "median_views_per_day": round(median([v["views_per_day"] for v in vids]), 1),
        "avg_duration_s": int(sum(v["duration_s"] for v in vids) / len(vids)),
        "uploads_per_week": per_week,
        "shorts_share": round(shorts / len(vids), 2),
        "avg_engagement_rate": round(sum(v["engagement_rate"] for v in vids) / len(vids), 4),
        "window_days": round(span_days, 1),
    }


def find_outliers(
    videos: list[dict],
    threshold: float = 2.0,
    n: int = 10,
    min_age_days: float = 2.0,
    now: datetime | None = None,
) -> dict:
    """Videos whose views >= threshold x the channel's median views.

    Videos younger than min_age_days are excluded from outlier candidates (they
    haven't had time to accumulate views) but still count toward the median.
    """
    vids = enrich(videos, now)
    med = median([v["views"] for v in vids])
    if med <= 0:
        return {"median_views": 0, "outliers": [], "outlier_rate": 0.0}
    cands = [v for v in vids if v["age_days"] >= min_age_days]
    outs = []
    for v in cands:
        mult = v["views"] / med
        if mult >= threshold:
            outs.append({**v, "multiple_of_median": round(mult, 2)})
    outs.sort(key=lambda v: v["multiple_of_median"], reverse=True)
    return {
        "median_views": int(med),
        "threshold": threshold,
        "outlier_rate": round(len(outs) / len(cands), 3) if cands else 0.0,
        "outliers": outs[:n],
    }


def top_bottom(videos: list[dict], k: int = 5, now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Top and bottom k by views/day among videos >= 2 days old (fairer than raw views)."""
    vids = [v for v in enrich(videos, now) if v["age_days"] >= 2] or enrich(videos, now)
    ranked = sorted(vids, key=lambda v: v["views_per_day"], reverse=True)
    return ranked[:k], ranked[-k:][::-1] if len(ranked) > k else []
