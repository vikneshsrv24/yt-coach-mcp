from datetime import datetime, timezone

import httpx
import pytest

from yt_coach.cache import Cache
from yt_coach.config import Config
from yt_coach.tools import Coach
from yt_coach.youtube import YouTubeClient

NOW = datetime(2026, 1, 31, tzinfo=timezone.utc)


def vid_item(vid, title, views, day, dur="PT5M", likes=None, comments=None, channel="UC_me"):
    return {
        "id": vid,
        "snippet": {"title": title, "channelId": channel, "channelTitle": channel,
                    "publishedAt": f"2026-01-{day:02d}T00:00:00Z", "tags": []},
        "statistics": {"viewCount": str(views), "likeCount": str(likes if likes is not None else views // 20),
                       "commentCount": str(comments if comments is not None else views // 200)},
        "contentDetails": {"duration": dur},
    }


# channel handle -> (channel json, [video items newest first])
CHANNELS = {
    "@me": ("UC_me", "My Channel", 1000, [
        vid_item("m1_________", "Why Rich People Never Do This", 500, 28),
        vid_item("m2_________", "A Small Story About Life", 300, 21, "PT0M45S"),
        vid_item("m3_________", "7 Lessons From An Old Cartoon", 5000, 14),
        vid_item("m4_________", "Motivation Story", 100, 7),
    ]),
    "@rival": ("UC_rival", "Rival", 50000, [
        vid_item("r1_________", "How He Lost EVERYTHING?", 90000, 25, channel="UC_rival"),
        vid_item("r2_________", "Money Story", 10000, 18, channel="UC_rival"),
        vid_item("r3_________", "Old Cartoon Wisdom", 12000, 11, channel="UC_rival"),
        vid_item("r4_________", "Another One", 9000, 4, channel="UC_rival"),
    ]),
}


def make_handler(quota_error=False):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        p = request.url.params
        path = request.url.path
        if "suggestqueries" in str(request.url):
            return httpx.Response(200, json=[p["q"], [p["q"] + " story", p["q"] + " ideas"]])
        if quota_error:
            return httpx.Response(403, json={"error": {"code": 403, "message": "quota",
                                                       "errors": [{"reason": "quotaExceeded"}]}})
        if path.endswith("/channels"):
            if "forHandle" in p:
                h = p["forHandle"]
                if h not in CHANNELS:
                    return httpx.Response(200, json={"pageInfo": {"totalResults": 0}})
                cid, title, subs, _ = CHANNELS[h]
                ids = [cid]
            else:
                ids = p["id"].split(",")
            items = []
            for h, (cid, title, subs, _) in CHANNELS.items():
                if cid in ids:
                    items.append({"id": cid, "snippet": {"title": title, "customUrl": h},
                                  "statistics": {"subscriberCount": str(subs), "viewCount": "999999", "videoCount": "4"},
                                  "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}}})
            return httpx.Response(200, json={"items": items})
        if path.endswith("/playlistItems"):
            pl = p["playlistId"]
            for _, (cid, _, _, vids) in CHANNELS.items():
                if "UU" + cid[2:] == pl:
                    return httpx.Response(200, json={"items": [{"contentDetails": {"videoId": v["id"]}} for v in vids]})
        if path.endswith("/videos"):
            want = p["id"].split(",")
            allv = [v for (_, (_, _, _, vids)) in CHANNELS.items() for v in vids]
            return httpx.Response(200, json={"items": [v for v in allv if v["id"] in want]})
        if path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "r1_________"}}, {"id": {"videoId": "m3_________"}}]})
        return httpx.Response(404, json={"error": {"message": "nope"}})

    handler.calls = calls
    return handler


@pytest.fixture
def make_coach():
    def _make(quota_error=False, competitors=("@rival",), fetcher=None):
        handler = make_handler(quota_error)
        http = httpx.Client(transport=httpx.MockTransport(handler))
        cache = Cache(":memory:")
        yt = YouTubeClient("k", cache, http)
        cfg = Config(api_key="k", my_channel="@me", competitors=list(competitors))
        kw = {"transcript_fetcher": fetcher} if fetcher else {}
        coach = Coach(cfg, yt, now=NOW, **kw)
        coach.handler = handler
        return coach
    return _make
