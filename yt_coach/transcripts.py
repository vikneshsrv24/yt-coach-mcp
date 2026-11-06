"""Transcript fetching and hook/body/ending segmentation."""
from __future__ import annotations

import re
from typing import Callable

from .errors import TranscriptUnavailable

HOOK_SECONDS = 30.0
CTA_RE = re.compile(
    r"\b(subscribe|like (?:this|the) video|hit the|comment (?:below|down)|let me know|"
    r"follow|share (?:this|it)|watch (?:next|this)|see you (?:in|next)|turn on notifications|bell icon)\b",
    re.I,
)


def extract_video_id(s: str) -> str:
    s = s.strip()
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    raise TranscriptUnavailable(f"'{s}' doesn't look like a YouTube video ID or URL.")


def default_fetcher(video_id: str, languages: list[str]) -> list[dict]:
    """Fetch via youtube-transcript-api; map its errors to TranscriptUnavailable."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api import _errors as E

    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
    except (E.TranscriptsDisabled, E.NoTranscriptFound):
        raise TranscriptUnavailable(
            f"No transcript available for {video_id} (captions disabled or not in {languages})."
        )
    except E.VideoUnavailable:
        raise TranscriptUnavailable(f"Video {video_id} is unavailable, private or deleted.")
    except (E.RequestBlocked, E.IpBlocked):
        raise TranscriptUnavailable(
            "YouTube blocked the transcript request from this IP (common on cloud/VPN IPs). "
            "Run the server from a home connection or retry later."
        )
    except Exception as e:  # library raises many subclasses of a base error
        raise TranscriptUnavailable(f"Could not fetch transcript for {video_id}: {type(e).__name__}") from e
    return [{"text": s.text, "start": float(s.start), "duration": float(s.duration)} for s in fetched]


def _wc(text: str) -> int:
    return len(text.split())


def split_transcript(snippets: list[dict], hook_seconds: float = HOOK_SECONDS) -> dict:
    """Split into hook (first ~30s), body, ending (last ~10%, 15-45s window)."""
    if not snippets:
        raise TranscriptUnavailable("Transcript is empty.")
    total = max(s["start"] + s["duration"] for s in snippets)
    end_window = min(max(15.0, total * 0.10), 45.0)
    end_start = max(total - end_window, hook_seconds)

    hook, body, ending = [], [], []
    for s in snippets:
        if s["start"] < hook_seconds:
            hook.append(s)
        elif s["start"] >= end_start:
            ending.append(s)
        else:
            body.append(s)

    def join(ss):
        return re.sub(r"\s+", " ", " ".join(x["text"] for x in ss)).strip()

    parts = {"hook": join(hook), "body": join(body), "ending": join(ending)}
    full = join(snippets)
    cta = sorted({m.group(0).lower() for m in CTA_RE.finditer(parts["ending"])})
    return {
        "duration_s": round(total, 1),
        "total_words": _wc(full),
        "words_per_minute": round(_wc(full) / (total / 60), 1) if total else 0,
        "hook": {"text": parts["hook"], "words": _wc(parts["hook"]), "seconds": min(hook_seconds, total)},
        "body": {"text": parts["body"], "words": _wc(parts["body"])},
        "ending": {
            "text": parts["ending"],
            "words": _wc(parts["ending"]),
            "starts_at_s": round(end_start, 1),
            "cta_phrases_found": cta,
        },
        "hook_features": {
            "opens_with_question": parts["hook"].lstrip()[:200].split("?")[0] != parts["hook"].lstrip()[:200] if "?" in parts["hook"][:200] else False,
            "contains_number": bool(re.search(r"\d", parts["hook"])),
            "first_sentence": re.split(r"(?<=[.!?])\s", parts["hook"], maxsplit=1)[0] if parts["hook"] else "",
        },
    }


def get_transcript(
    video_ref: str,
    languages: list[str] | None = None,
    fetcher: Callable[[str, list[str]], list[dict]] = default_fetcher,
) -> dict:
    vid = extract_video_id(video_ref)
    snippets = fetcher(vid, languages or ["en", "en-US", "en-GB"])
    return {"video_id": vid, **split_transcript(snippets)}
