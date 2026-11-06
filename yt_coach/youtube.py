"""Thin YouTube Data API v3 client: cached, quota-aware, typed errors.

Quota costs (units): channels.list=1, playlistItems.list=1, videos.list=1,
search.list=100. Everything is cached in SQLite so repeats are free.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from .cache import Cache
from .errors import ApiError, ChannelNotFound, ConfigError, QuotaExceeded

API = "https://www.googleapis.com/youtube/v3"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
SHORT_MAX_SECONDS = 180  # Shorts can be up to 3 min; this is a heuristic.

_DUR = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_duration(iso: str) -> int:
    """ISO-8601 duration (PT1H2M3S) -> seconds."""
    m = _DUR.match(iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _int(x: Any) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


class YouTubeClient:
    def __init__(self, api_key: str, cache: Cache, http: httpx.Client | None = None):
        self.api_key = api_key
        self.cache = cache
        self.http = http or httpx.Client(timeout=20)
        self.quota_used = 0  # units spent this process (cache hits cost 0)

    # ---- low level -------------------------------------------------------
    def _get(self, endpoint: str, params: dict, cost: int = 1, ttl: int | None = None) -> dict:
        key = f"{endpoint}?{json.dumps(params, sort_keys=True)}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        try:
            r = self.http.get(f"{API}/{endpoint}", params={**params, "key": self.api_key})
        except httpx.HTTPError as e:
            raise ApiError(f"Network error calling YouTube API: {e}") from e
        if r.status_code != 200:
            self._raise(r)
        data = r.json()
        self.quota_used += cost
        self.cache.set(key, data, ttl)
        return data

    @staticmethod
    def _raise(r: httpx.Response) -> None:
        try:
            err = r.json().get("error", {})
        except ValueError:
            err = {}
        reasons = {e.get("reason") for e in err.get("errors", [])}
        msg = err.get("message") or r.text[:200]
        if reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
            raise QuotaExceeded(
                "YouTube API quota exceeded (default 10,000 units/day, resets midnight "
                "Pacific). Cached results still work; try again later."
            )
        if reasons & {"keyInvalid", "API_KEY_INVALID"} or "API key not valid" in msg:
            raise ConfigError("YOUTUBE_API_KEY is invalid. Check your key and that YouTube Data API v3 is enabled.")
        if r.status_code == 403:
            raise ApiError(f"YouTube API refused the request (403): {msg}")
        raise ApiError(f"YouTube API error {r.status_code}: {msg}")

    # ---- channels --------------------------------------------------------
    def get_channel(self, handle_or_id: str) -> dict:
        h = handle_or_id.strip()
        if not h:
            raise ChannelNotFound("No channel given. Pass a handle like @name or set MY_CHANNEL.")
        params = {"part": "snippet,statistics,contentDetails"}
        if h.startswith("UC") and not h.startswith("@"):
            params["id"] = h
        else:
            params["forHandle"] = h if h.startswith("@") else "@" + h
        data = self._get("channels", params, ttl=24 * 3600)
        items = data.get("items") or []
        if not items:
            raise ChannelNotFound(
                f"Channel '{h}' not found. Check the handle (e.g. @name) - it must match the channel's @handle exactly."
            )
        c = items[0]
        st = c.get("statistics", {})
        return {
            "id": c["id"],
            "handle": c.get("snippet", {}).get("customUrl", h),
            "title": c.get("snippet", {}).get("title", ""),
            "created": c.get("snippet", {}).get("publishedAt"),
            "subscribers": None if st.get("hiddenSubscriberCount") else _int(st.get("subscriberCount")),
            "total_views": _int(st.get("viewCount")),
            "video_count": _int(st.get("videoCount")),
            "uploads_playlist": c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
        }

    def get_channels_by_ids(self, ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        ids = sorted(set(ids))
        for i in range(0, len(ids), 50):
            data = self._get(
                "channels",
                {"part": "snippet,statistics", "id": ",".join(ids[i : i + 50])},
                ttl=24 * 3600,
            )
            for c in data.get("items", []):
                st = c.get("statistics", {})
                out[c["id"]] = {
                    "title": c.get("snippet", {}).get("title", ""),
                    "subscribers": None if st.get("hiddenSubscriberCount") else _int(st.get("subscriberCount")),
                }
        return out

    # ---- videos ----------------------------------------------------------
    def get_videos(self, ids: list[str]) -> list[dict]:
        vids: list[dict] = []
        for i in range(0, len(ids), 50):
            data = self._get(
                "videos",
                {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i : i + 50])},
                ttl=6 * 3600,
            )
            for v in data.get("items", []):
                vids.append(self._normalize_video(v))
        return vids

    @staticmethod
    def _normalize_video(v: dict) -> dict:
        sn, st, cd = v.get("snippet", {}), v.get("statistics", {}), v.get("contentDetails", {})
        dur = parse_duration(cd.get("duration", ""))
        return {
            "id": v["id"],
            "title": sn.get("title", ""),
            "channel_id": sn.get("channelId"),
            "channel_title": sn.get("channelTitle"),
            "published_at": sn.get("publishedAt"),
            "duration_s": dur,
            "is_short": 0 < dur <= SHORT_MAX_SECONDS,
            "views": _int(st.get("viewCount")),
            "likes": _int(st.get("likeCount")),
            "comments": _int(st.get("commentCount")),
            "tags": sn.get("tags", [])[:15],
        }

    def recent_videos(self, uploads_playlist: str, n: int = 30) -> list[dict]:
        """Latest n uploads (newest first) via playlistItems + videos.list."""
        ids: list[str] = []
        token = None
        while len(ids) < n:
            params = {
                "part": "contentDetails",
                "playlistId": uploads_playlist,
                "maxResults": min(50, n - len(ids)),
            }
            if token:
                params["pageToken"] = token
            data = self._get("playlistItems", params, ttl=3 * 3600)
            ids += [it["contentDetails"]["videoId"] for it in data.get("items", [])]
            token = data.get("nextPageToken")
            if not token:
                break
        vids = self.get_videos(ids[:n])
        vids.sort(key=lambda v: v["published_at"] or "", reverse=True)
        return vids

    # ---- search / keywords ----------------------------------------------
    def search_videos(self, query: str, max_results: int = 5) -> list[str]:
        """search.list costs 100 units - only used by the keyword tool."""
        data = self._get(
            "search",
            {"part": "id", "q": query, "type": "video", "maxResults": max_results, "order": "relevance"},
            cost=100,
            ttl=24 * 3600,
        )
        return [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]

    def autocomplete(self, seed: str) -> list[str]:
        """YouTube autocomplete (no API quota). Returns [] on failure."""
        key = f"suggest:{seed}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        try:
            r = self.http.get(SUGGEST_URL, params={"client": "firefox", "ds": "yt", "q": seed})
            r.raise_for_status()
            sugg = [s for s in r.json()[1] if isinstance(s, str)]
        except (httpx.HTTPError, ValueError, IndexError, KeyError):
            return []
        self.cache.set(key, sugg, 24 * 3600)
        return sugg
