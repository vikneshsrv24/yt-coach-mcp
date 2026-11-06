"""FastMCP server exposing the coach tools over stdio."""
from __future__ import annotations

import functools
import logging
import sys

from mcp.server.fastmcp import FastMCP

from .cache import Cache
from .config import Config
from .errors import CoachError
from .tools import Coach
from .youtube import YouTubeClient

logging.basicConfig(level=logging.INFO, stream=sys.stderr)  # never log to stdout (stdio transport)
log = logging.getLogger("yt_coach")

mcp = FastMCP("yt-coach")
_coach: Coach | None = None


def get_coach() -> Coach:
    global _coach
    if _coach is None:
        cfg = Config.from_env()
        cache = Cache(cfg.db_path, cfg.ttl_seconds)
        _coach = Coach(cfg, YouTubeClient(cfg.api_key, cache))
    return _coach


def safe(fn):
    """Turn our errors into a readable {"error": ...} result instead of a stack trace."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except CoachError as e:
            return {"error": str(e), "type": type(e).__name__}
        except Exception as e:  # last resort; keep the server alive
            log.exception("unexpected error in %s", fn.__name__)
            return {"error": f"Unexpected error: {type(e).__name__}: {e}", "type": "InternalError"}
    return wrapper


@mcp.tool()
@safe
def channel_overview(channel: str = "", n: int = 20) -> dict:
    """Overview of a YouTube channel: subs, views, last N videos with views/likes/comments/
    duration/date/views-per-day/Short-vs-long/engagement, plus median views, upload cadence
    per week and average duration. Leave `channel` empty for your own (MY_CHANNEL)."""
    return get_coach().channel_overview(channel or None, n)


@mcp.tool()
@safe
def find_outliers(channel: str = "", n: int = 10, threshold: float = 2.0) -> dict:
    """Videos whose views are >= `threshold` x the channel's median views, with the multiple,
    title, length, publish date and a title-pattern note (number/question/power words/length)."""
    return get_coach().find_outliers(channel or None, n, threshold)


@mcp.tool()
@safe
def compare_channels(my_channel: str = "", competitors: list[str] | None = None, n: int = 30) -> dict:
    """Side-by-side metrics for your channel vs competitors (defaults: MY_CHANNEL, COMPETITORS),
    including outlier rate and title patterns, plus a `gaps` summary (me vs competitor average)."""
    return get_coach().compare_channels(my_channel or None, competitors, n)


@mcp.tool()
@safe
def get_transcript(video_id: str) -> dict:
    """Transcript of a video (ID or URL) split into hook (first ~30s), body and ending/CTA with
    word counts, words-per-minute and CTA phrases found. Fails clearly if captions are unavailable."""
    return get_coach().get_transcript(video_id)


@mcp.tool()
@safe
def keyword_ideas(seed: str, max_keywords: int = 5) -> dict:
    """YouTube autocomplete suggestions for `seed` plus top results per keyword with views and an
    ESTIMATED demand/competition/opportunity score (not real search volume). Costs ~100 API
    quota units per keyword analysed (cached 24h)."""
    return get_coach().keyword_ideas(seed, max_keywords)


@mcp.tool()
@safe
def next_script_brief(topic: str = "") -> dict:
    """Gather everything needed to pick and write the next script: your top/bottom videos,
    competitor outliers, winning title patterns and hook structures from transcripts, plus
    instructions for you (Claude) on how to turn it into a recommendation and script."""
    return get_coach().next_script_brief(topic or None)


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
