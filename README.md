# yt-coach-mcp

A personal, vidIQ-style YouTube coach as an **MCP server**. The server only **fetches data and does the maths**;
Claude does the analysis and writing. Built for an animated short-story channel, but works for any channel.

## Tools

| Tool | What it returns |
|---|---|
| `channel_overview(channel, n)` | Subs, total views, video count; last N videos with views, likes, comments, duration, date, views/day, Short vs long, engagement; median views, uploads/week, avg duration |
| `find_outliers(channel, n, threshold)` | Videos >= `threshold` x the channel median (default 2x) with the multiple, title, length, date and a title-pattern note |
| `compare_channels(my_channel, competitors, n)` | Side-by-side table (incl. outlier rate, title patterns) and a `gaps` summary: you vs competitor average |
| `get_transcript(video_id)` | Transcript split into hook (first ~30s), body, ending/CTA with word counts, words/min, CTA phrases |
| `keyword_ideas(seed, max_keywords)` | YouTube autocomplete + top results per keyword with an **estimated** demand / competition / opportunity score |
| `next_script_brief(topic)` | Your top/bottom videos, competitor outliers, winning title patterns, hook structures + instructions for Claude to recommend and write the next script |

Leave `channel` empty (or pass `me`) to use `MY_CHANNEL`. `compare_channels` defaults to `MY_CHANNEL` vs `COMPETITORS`.

> **Keyword scores are estimates, not search volume.** Demand is inferred from the views/day of the videos
> currently ranking; competition from the size of the channels ranking. YouTube does not publish search volume.
> The formulas are in `yt_coach/keywords.py`.

## Setup

1. **Get a YouTube Data API v3 key**: Google Cloud Console -> create project -> enable *YouTube Data API v3* -> Credentials -> API key.
2. Install:
   ```bash
   git clone https://github.com/vikneshsrv24/yt-coach-mcp && cd yt-coach-mcp
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   cp .env.example .env   # then edit: YOUTUBE_API_KEY, MY_CHANNEL, COMPETITORS
   ```
3. Test it starts (it waits for MCP messages on stdin; Ctrl+C to quit):
   ```bash
   .venv/bin/python -m yt_coach
   ```

`.env` is read from the project folder regardless of where Claude launches the server. You can instead pass
the variables via `claude mcp add -e` / the Desktop config `env` block.

## Add to Claude Code

Use absolute paths (replace `/ABS/PATH`):

```bash
claude mcp add yt-coach \
  -e YOUTUBE_API_KEY=your_key -e MY_CHANNEL=@yourchannel -e COMPETITORS=@rival1,@rival2 \
  -- /ABS/PATH/yt-coach-mcp/.venv/bin/python -m yt_coach
```

If you rely on `.env` instead, drop the `-e` flags. Check with `claude mcp list`, then ask e.g.
*"Run next_script_brief and recommend my next video."*

## Add to Claude Desktop

Edit `claude_desktop_config.json` (Settings -> Developer -> Edit Config), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "yt-coach": {
      "command": "/ABS/PATH/yt-coach-mcp/.venv/bin/python",
      "args": ["-m", "yt_coach"],
      "env": {
        "YOUTUBE_API_KEY": "your_key",
        "MY_CHANNEL": "@yourchannel",
        "COMPETITORS": "@rival1,@rival2"
      }
    }
  }
}
```
On Windows use `...\.venv\Scripts\python.exe`.

## Quota & caching

Default quota is 10,000 units/day. Costs: `channels.list`, `playlistItems.list`, `videos.list` = **1 unit** each;
`search.list` = **100 units** (used only by `keyword_ideas`, ~100 per keyword analysed; default 5 keywords = ~500).
Videos are read through each channel's uploads playlist, not search. Every response is cached in SQLite
(`.cache/yt_coach.sqlite3`; TTLs: channels 24h, videos 6h, playlists 3h, search 24h), so repeated calls cost nothing.
Delete the file to force fresh data. Autocomplete uses no quota.

## Errors

Tools return `{"error": "...", "type": "..."}` instead of crashing: bad/unknown handle (`ChannelNotFound`),
quota exhausted (`QuotaExceeded`; cached data still works), invalid key (`ConfigError`), and
`TranscriptUnavailable` for captions disabled, private/deleted videos, or YouTube blocking the request
(common from cloud/VPN IPs; run locally). `next_script_brief` and `compare_channels` skip a failing competitor or
transcript and report it under `warnings`.

## Notes / limitations

- "Short" = duration <= 180s (heuristic; the API doesn't flag Shorts).
- Outliers exclude videos under 2 days old (not enough time to accumulate views) and compare against the channel's median views over the analysed window.
- Subscriber counts can be hidden by a channel (shown as `null`).

## Phase 2 (not implemented): YouTube Analytics via OAuth

For retention curves, traffic sources and CTR **of your own channel** only. This needs OAuth (scope
`yt-analytics.readonly`), not an API key. Stub and plan: `yt_coach/analytics_stub.py`. Steps when you build it:
create an OAuth Desktop client, run a one-time consent flow, store the refresh token, then add tools
`audience_retention`, `traffic_sources`, `ctr_and_impressions`.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```
Tests use `httpx.MockTransport`; no network or API key needed.

Layout: `yt_coach/{config,errors,cache,youtube,metrics,titles,transcripts,keywords,tools,server}.py`.
