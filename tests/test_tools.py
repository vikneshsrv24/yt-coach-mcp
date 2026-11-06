import pytest

from yt_coach.errors import ChannelNotFound, QuotaExceeded, TranscriptUnavailable
from yt_coach.server import safe


def test_overview(make_coach):
    r = make_coach().channel_overview("@me")
    assert r["channel"]["subscribers"] == 1000
    assert len(r["videos"]) == 4
    assert r["stats"]["median_views"] == 400
    assert {v["format"] for v in r["videos"]} == {"short", "long"}
    assert r["videos"][0]["id"] == "m1_________"  # newest first


def test_overview_defaults_to_my_channel(make_coach):
    assert make_coach().channel_overview()["channel"]["title"] == "My Channel"


def test_bad_handle(make_coach):
    with pytest.raises(ChannelNotFound):
        make_coach().channel_overview("@ghost")


def test_outliers_have_pattern_notes(make_coach):
    r = make_coach().find_outliers("@rival", threshold=2)
    assert r["outliers"][0]["id"] == "r1_________"
    assert "question" in r["outliers"][0]["title_pattern"]
    assert r["outliers"][0]["multiple_of_median"] > 5


def test_compare(make_coach):
    r = make_coach().compare_channels()
    assert [row["role"] for row in r["table"]] == ["me", "competitor"]
    assert r["gaps"]["median_views"]["me_vs_avg"] < 1
    assert "title_patterns" in r["table"][1]


def test_compare_skips_bad_competitor(make_coach):
    r = make_coach(competitors=("@rival", "@ghost")).compare_channels()
    assert len(r["table"]) == 2 and "@ghost" in r["warnings"][0]


def test_quota_exceeded_is_readable(make_coach):
    coach = make_coach(quota_error=True)
    with pytest.raises(QuotaExceeded):
        coach.channel_overview("@me")


def test_safe_wrapper_returns_error_dict(make_coach):
    coach = make_coach(quota_error=True)
    out = safe(coach.channel_overview)("@me")
    assert out["type"] == "QuotaExceeded" and "quota" in out["error"].lower()


def test_cache_means_no_second_api_call(make_coach):
    coach = make_coach()
    coach.channel_overview("@me")
    n = len(coach.handler.calls)
    coach.channel_overview("@me")
    assert len(coach.handler.calls) == n
    assert coach.yt.quota_used > 0


def test_transcript_missing(make_coach):
    def fetcher(v, langs):
        raise TranscriptUnavailable("captions disabled")
    with pytest.raises(TranscriptUnavailable):
        make_coach(fetcher=fetcher).get_transcript("dQw4w9WgXcQ")


def test_transcript_ok(make_coach):
    f = lambda v, langs: [{"text": "Hello there", "start": 0.0, "duration": 5.0},
                          {"text": "middle part", "start": 40.0, "duration": 5.0},
                          {"text": "subscribe now", "start": 100.0, "duration": 5.0}]
    r = make_coach(fetcher=f).get_transcript("dQw4w9WgXcQ")
    assert r["hook"]["text"] == "Hello there" and "subscribe" in r["ending"]["cta_phrases_found"]


def test_keyword_ideas(make_coach):
    r = make_coach().keyword_ideas("old cartoon story", max_keywords=2)
    assert "NOT real YouTube search volume" in r["disclaimer"]
    assert len(r["keywords"]) == 2
    assert r["keywords"][0]["top_results"]
    assert 0 <= r["keywords"][0]["opportunity_score"] <= 100


def test_next_script_brief_tolerates_missing_transcripts(make_coach):
    def fetcher(v, langs):
        raise TranscriptUnavailable("no captions")
    r = make_coach(fetcher=fetcher).next_script_brief("money habits")
    assert r["my_top_videos"] and r["competitor_outliers"][0]["id"] == "r1_________"
    assert r["hook_structures"] == [] and r["warnings"]
    assert "money habits" in r["instructions_for_claude"]


def test_next_script_brief_with_hooks(make_coach):
    f = lambda v, langs: [{"text": "What if I told you?", "start": 0.0, "duration": 5.0},
                          {"text": "body", "start": 50.0, "duration": 5.0}]
    r = make_coach(fetcher=f).next_script_brief()
    assert r["hook_structures"] and r["hook_structures"][0]["hook_features"]["opens_with_question"]
