import pytest

from yt_coach import keywords, metrics, titles, transcripts
from yt_coach.cache import Cache
from yt_coach.config import normalize_handle
from yt_coach.errors import TranscriptUnavailable
from yt_coach.youtube import parse_duration
from tests.conftest import NOW, vid_item
from yt_coach.youtube import YouTubeClient


def test_parse_duration():
    assert parse_duration("PT1H2M3S") == 3723
    assert parse_duration("PT45S") == 45
    assert parse_duration("P0D") == 0
    assert parse_duration("") == 0


def test_normalize_handle():
    assert normalize_handle("name") == "@name"
    assert normalize_handle("https://www.youtube.com/@name/") == "@name"
    assert normalize_handle("UCabc") == "UCabc"


def test_cache_ttl(monkeypatch):
    import time
    c = Cache(":memory:")
    c.set("a", {"x": 1}, ttl=10)
    assert c.get("a") == {"x": 1}
    real = time.time()
    monkeypatch.setattr("yt_coach.cache.time.time", lambda: real + 11)
    assert c.get("a") is None


def _vids():
    items = [vid_item("a", "t", 100, 30), vid_item("b", "t", 200, 20), vid_item("c", "t", 900, 10), vid_item("d", "t", 150, 1)]
    return [YouTubeClient._normalize_video(i) for i in items]


def test_channel_stats():
    st = metrics.channel_stats(_vids(), NOW)
    assert st["median_views"] == 175
    assert st["videos_analyzed"] == 4
    assert st["uploads_per_week"] == pytest.approx(3 / (29 / 7), abs=0.01)
    assert st["avg_duration_s"] == 300


def test_outliers_multiple_and_min_age():
    res = metrics.find_outliers(_vids(), threshold=2.0, now=NOW)
    assert [o["id"] for o in res["outliers"]] == ["c"]
    assert res["outliers"][0]["multiple_of_median"] == pytest.approx(900 / 175, abs=0.01)
    # "a" is only 1 day old: never an outlier candidate
    assert all(o["id"] != "a" for o in metrics.find_outliers(_vids(), threshold=0.1, now=NOW)["outliers"])


def test_zero_median_safe():
    v = [YouTubeClient._normalize_video(vid_item("z", "t", 0, 5))]
    assert metrics.find_outliers(v, now=NOW)["outliers"] == []


def test_title_analysis():
    a = titles.analyze_title("7 Secrets Rich People NEVER Tell You?")
    assert a["has_number"] and a["starts_with_number"] and a["is_question"] and a["has_caps_word"]
    assert "secrets" in a["power_words"]
    s = titles.summarize_patterns(["7 Rules", "How to win", "plain"])
    assert s["pct_with_number"] == 0.33


def test_keyword_score_bounds():
    s = keywords.score(1000, 10000)
    assert 0 <= s["opportunity_score"] <= 100
    assert keywords.score(0, None)["demand_score"] == 0
    assert keywords.score(1000, 1_000_000)["competition_score"] > keywords.score(1000, 1000)["competition_score"]


SNIPS = [{"text": f"word{i} " * 5, "start": float(i * 10), "duration": 10.0} for i in range(30)]
SNIPS[-1]["text"] = "Please subscribe and let me know below."


def test_split_transcript():
    r = transcripts.split_transcript(SNIPS)
    assert r["duration_s"] == 300.0
    assert r["hook"]["words"] == 15  # snippets starting at 0,10,20
    assert r["hook"]["words"] + r["body"]["words"] + r["ending"]["words"] == r["total_words"]
    assert "subscribe" in r["ending"]["cta_phrases_found"]


def test_extract_video_id():
    assert transcripts.extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=3") == "dQw4w9WgXcQ"
    assert transcripts.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    with pytest.raises(TranscriptUnavailable):
        transcripts.extract_video_id("nope")
