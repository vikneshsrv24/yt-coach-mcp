"""PHASE 2 (not implemented): YouTube Analytics API via OAuth, own channel only.

Planned scope: https://www.googleapis.com/auth/yt-analytics.readonly
Planned tools:
  - audience_retention(video_id): audienceWatchRatio by elapsedVideoTimeRatio
    (dimension=elapsedVideoTimeRatio, metrics=audienceWatchRatio,relativeRetentionPerformance)
  - traffic_sources(days): insightTrafficSourceType breakdown with views/watch time
  - ctr_and_impressions(days): impressions + impressionClickThroughRate per video
Requires a Google Cloud OAuth client (Desktop app), a one-time browser consent flow,
and a stored refresh token. The Data API key used elsewhere cannot access these reports.
"""
from __future__ import annotations


def not_implemented(*_args, **_kwargs) -> dict:
    return {
        "error": "YouTube Analytics (retention / traffic sources) is Phase 2 and not implemented yet. "
                 "See README 'Phase 2'.",
        "type": "NotImplemented",
    }
