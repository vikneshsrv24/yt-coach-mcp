"""Environment-based configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")  # works regardless of the launch directory
load_dotenv()


def normalize_handle(h: str) -> str:
    h = h.strip()
    if not h:
        return h
    # Accept full URLs like https://www.youtube.com/@name
    if "youtube.com/" in h:
        h = h.rstrip("/").split("/")[-1]
    return h if h.startswith("@") or h.startswith("UC") else "@" + h


@dataclass
class Config:
    api_key: str
    my_channel: str = ""
    competitors: list[str] = field(default_factory=list)
    db_path: Path = _ROOT / ".cache" / "yt_coach.sqlite3"
    ttl_seconds: int = 12 * 3600

    @classmethod
    def from_env(cls) -> "Config":
        key = os.environ.get("YOUTUBE_API_KEY", "").strip()
        if not key:
            raise ConfigError(
                "YOUTUBE_API_KEY is not set. Add it to your .env or the MCP server env."
            )
        comps = [
            normalize_handle(c)
            for c in os.environ.get("COMPETITORS", "").split(",")
            if c.strip()
        ]
        return cls(
            api_key=key,
            my_channel=normalize_handle(os.environ.get("MY_CHANNEL", "")),
            competitors=comps,
            db_path=Path(os.environ.get("YT_COACH_DB", str(_ROOT / ".cache" / "yt_coach.sqlite3"))),
            ttl_seconds=int(float(os.environ.get("YT_COACH_TTL_HOURS", "12")) * 3600),
        )
