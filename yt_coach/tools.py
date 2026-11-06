"""The six coach tools as plain functions returning JSON-serializable dicts."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from . import keywords as kw
from . import metrics, titles, transcripts
from .config import Config, normalize_handle
from .errors import CoachError, ConfigError, QuotaExceeded
from .youtube import YouTubeClient

DEFAULT_N = 30


class Coach:
    def __init__(
        self,
        cfg: Config,
        yt: YouTubeClient,
        transcript_fetcher: Callable = transcripts.default_fetcher,
        now: datetime | None = None,
    ):
        self.cfg, self.yt, self.fetcher, self.now = cfg, yt, transcript_fetcher, now

    # ---- helpers ---------------------------------------------------------
    def _resolve(self, channel: str | None) -> str:
        if channel and channel.strip().lower() not in ("me", "my", "mine"):
            return normalize_handle(channel)
        if not self.cfg.my_channel:
            raise ConfigError("No channel given and MY_CHANNEL is not set.")
        return self.cfg.my_channel

    def _load(self, channel: str | None, n: int = DEFAULT_N) -> tuple[dict, list[dict]]:
        ch = self.yt.get_channel(self._resolve(channel))
        vids = self.yt.recent_videos(ch["uploads_playlist"], n) if ch["uploads_playlist"] else []
        return ch, vids

    @staticmethod
    def _slim(v: dict) -> dict:
        keep = ("id", "title", "published_at", "duration_s", "format", "views", "likes",
                "comments", "views_per_day", "engagement_rate", "age_days")
        return {k: v[k] for k in keep if k in v}

    # ---- 1. channel_overview --------------------------------------------
    def channel_overview(self, channel: str | None = None, n: int = 20) -> dict:
        ch, vids = self._load(channel, n)
        enriched = metrics.enrich(vids, self.now)
        return {
            "channel": {k: ch[k] for k in ("id", "handle", "title", "subscribers", "total_views", "video_count")},
            "stats": metrics.channel_stats(enriched, self.now),
            "videos": [self._slim(v) for v in enriched],
            "notes": "Shorts = videos <=180s (heuristic). engagement_rate = (likes+comments)/views. "
                     "uploads_per_week is measured over the analysed window.",
        }

    # ---- 2. find_outliers -----------------------------------------------
    def find_outliers(self, channel: str | None = None, n: int = 10, threshold: float = 2.0) -> dict:
        ch, vids = self._load(channel, DEFAULT_N + 20)
        res = metrics.find_outliers(vids, threshold=threshold, n=n, now=self.now)
        outs = [
            {**self._slim(o), "multiple_of_median": o["multiple_of_median"], "title_pattern": titles.title_note(o["title"])}
            for o in res["outliers"]
        ]
        return {
            "channel": ch["title"],
            "videos_analyzed": len(vids),
            "median_views": res["median_views"],
            "threshold_multiple": threshold,
            "outlier_rate": res.get("outlier_rate", 0.0),
            "outliers": outs,
            "outlier_title_patterns": titles.summarize_patterns([o["title"] for o in outs]),
            "all_title_patterns": titles.summarize_patterns([v["title"] for v in vids]),
        }

    # ---- 3. compare_channels --------------------------------------------
    def compare_channels(self, my_channel: str | None = None, competitors: list[str] | None = None, n: int = 30) -> dict:
        handles = [self._resolve(my_channel)] + [normalize_handle(c) for c in (competitors or self.cfg.competitors)]
        if len(handles) < 2:
            raise ConfigError("No competitors given and COMPETITORS is not set.")
        rows, warnings = [], []
        for i, h in enumerate(handles):
            try:
                ch, vids = self._load(h, n)
            except QuotaExceeded:
                raise
            except CoachError as e:
                if i == 0:
                    raise
                warnings.append(f"{h}: {e}")
                continue
            st = metrics.channel_stats(vids, self.now)
            out = metrics.find_outliers(vids, now=self.now)
            pats = titles.summarize_patterns([v["title"] for v in vids])
            rows.append({
                "role": "me" if i == 0 else "competitor",
                "channel": ch["title"], "handle": h, "subscribers": ch["subscribers"],
                "total_views": ch["total_views"], "video_count": ch["video_count"], **st,
                "outlier_rate": out.get("outlier_rate", 0.0),
                "views_per_sub_median": round(st["median_views"] / ch["subscribers"], 3) if ch["subscribers"] else None,
                "title_patterns": {k: pats[k] for k in ("avg_chars", "avg_words", "pct_with_number", "pct_question", "pct_caps_word", "pct_emoji", "top_first_words", "power_word_hits") if k in pats},
            })
        me, comps = rows[0], rows[1:]
        gaps = {}
        for m in ("median_views", "median_views_per_day", "uploads_per_week", "avg_duration_s", "avg_engagement_rate", "outlier_rate", "shorts_share", "views_per_sub_median"):
            vals = [c[m] for c in comps if c.get(m) is not None]
            if me.get(m) is not None and vals:
                avg = sum(vals) / len(vals)
                gaps[m] = {"me": me[m], "competitor_avg": round(avg, 4), "me_vs_avg": round(me[m] / avg, 2) if avg else None}
        return {"table": rows, "gaps": gaps, "warnings": warnings,
                "notes": "me_vs_avg < 1 means you trail the competitor average on that metric."}

    # ---- 4. get_transcript ----------------------------------------------
    def get_transcript(self, video_id: str) -> dict:
        return transcripts.get_transcript(video_id, fetcher=self.fetcher)

    # ---- 5. keyword_ideas ------------------------------------------------
    def keyword_ideas(self, seed: str, max_keywords: int = 5) -> dict:
        if not seed.strip():
            raise ConfigError("Provide a seed keyword.")
        return kw.keyword_ideas(self.yt, seed.strip(), max_keywords=max_keywords, now=self.now)

    # ---- 6. next_script_brief -------------------------------------------
    def next_script_brief(self, topic: str | None = None) -> dict:
        warnings: list[str] = []
        my_ch, my_vids = self._load(None, 40)
        top, bottom = metrics.top_bottom(my_vids, 5, self.now)
        my_out = metrics.find_outliers(my_vids, now=self.now)

        comp_outliers = []
        for h in self.cfg.competitors:
            try:
                ch, vids = self._load(h, 40)
            except QuotaExceeded:
                raise
            except CoachError as e:
                warnings.append(f"{h}: {e}")
                continue
            for o in metrics.find_outliers(vids, n=3, now=self.now)["outliers"]:
                comp_outliers.append({**self._slim(o), "channel": ch["title"],
                                      "multiple_of_median": o["multiple_of_median"],
                                      "title_pattern": titles.title_note(o["title"])})
        comp_outliers.sort(key=lambda o: o["multiple_of_median"], reverse=True)

        hooks = []
        for label, group in (("my_top", top[:3]), ("competitor_outlier", comp_outliers[:3])):
            for v in group:
                try:
                    t = transcripts.get_transcript(v["id"], fetcher=self.fetcher)
                    hooks.append({"source": label, "video_id": v["id"], "title": v["title"],
                                  "hook": t["hook"], "hook_features": t["hook_features"],
                                  "ending_cta": t["ending"]["cta_phrases_found"],
                                  "body_words": t["body"]["words"], "words_per_minute": t["words_per_minute"]})
                except CoachError as e:
                    warnings.append(f"transcript {v['id']}: {e}")

        winners = [v["title"] for v in top] + [o["title"] for o in comp_outliers]
        return {
            "topic_requested": topic,
            "my_channel": {"title": my_ch["title"], "subscribers": my_ch["subscribers"],
                           "stats": metrics.channel_stats(my_vids, self.now)},
            "my_top_videos": [self._slim(v) for v in top],
            "my_bottom_videos": [self._slim(v) for v in bottom],
            "my_outliers": [self._slim(o) | {"multiple_of_median": o["multiple_of_median"]} for o in my_out["outliers"]],
            "competitor_outliers": comp_outliers[:10],
            "winning_title_patterns": titles.summarize_patterns(winners),
            "losing_title_patterns": titles.summarize_patterns([v["title"] for v in bottom]),
            "hook_structures": hooks,
            "warnings": warnings,
            "instructions_for_claude": (
                "Using ONLY this data: (1) identify what separates my top from bottom videos and what "
                "competitor outliers share (title mechanics, length, hook type); "
                + (f"(2) evaluate the requested topic '{topic}' against those patterns and say if it fits; "
                   if topic else "(2) recommend the single best next topic, with 2 alternates; ")
                + "(3) give 3 title options; (4) write the full script with a hook of <=30s mirroring the "
                  "best hook structures, a body, and an ending/CTA. Match my channel's niche and typical duration. "
                  "Flag where data is thin."
            ),
        }
