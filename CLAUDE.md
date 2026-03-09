# CLAUDE.md — fun-ai-news

## Project Overview
Local Python CLI called **AI Déjà Vu Generator**. Three-stage pipeline:
```
Harvest (HN API) → Déjà Vu Detector (Claude + DuckDuckGo) → Mockery Engine (Claude)
```
Fetches top AI news, finds embarrassing historical parallels, generates funny social posts.

## Architecture

### Module responsibilities
| File | Stage | What it does |
|---|---|---|
| `src/models.py` | — | Shared dataclasses: `NewsItem`, `HistoricalParallel`, `MockPost`, `PipelineResult`, `PostTone` |
| `src/harvest.py` | 1 | HN Algolia API (async httpx) + Claude headline summarisation |
| `src/deja_vu.py` | 2 | Claude agentic tool-use loop + DuckDuckGo `web_search` tool |
| `src/mockery.py` | 3 | Claude generates funny post for given tone + platform |
| `src/pipeline.py` | — | Rich CLI orchestrator; saves `output/posts_<timestamp>.json` |

### Data flow (typed contracts)
```
NewsItem → find_parallel() → HistoricalParallel
NewsItem + HistoricalParallel → generate_post() → MockPost
MockPost[] + errors[] → PipelineResult → JSON file
```

### Stage 2 agentic loop
- Claude calls `web_search` (DuckDuckGo) up to **5 iterations**
- Returns structured JSON; pipeline strips markdown fences before `json.loads()`
- Raises `RuntimeError` if loop doesn't converge

## Tech Stack
- **Python 3.13** (minimum 3.11)
- **anthropic SDK** — all Claude calls use `claude-sonnet-4-6`
- **httpx async** — HN Algolia API (`https://hn.algolia.com/api/v1/search`)
- **duckduckgo-search** — free, no API key needed
- **rich** — terminal UI (spinners, panels)
- **python-dotenv** — `.env` loading

## Code Conventions
- Dataclasses (stdlib), not Pydantic models, for inter-stage contracts
- `async`/`await` only in Stage 1 (`harvest.py`); Stages 2+3 are sync
- One `Anthropic` client created in `pipeline.run()` and passed down — don't create fresh clients in loops
- All Claude calls use `model="claude-sonnet-4-6"` — don't downgrade
- Errors per story are caught and appended to `result.errors`; never abort the whole run for one story
- Output saved to `output/` (gitignored); filename pattern `posts_<YYYYMMDD_HHMMSS>.json`

## Environment Variables
| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key |
| `NEWS_COUNT` | no | `5` | Stories to fetch |
| `POST_TONE` | no | `sarcastic` | Default tone: `sarcastic` \| `absurdist` \| `well_actually` |

Never read or commit `.env`. Use `.env.example` as the template.

## Running the Project
```bash
pip install -e .
cp .env.example .env   # add ANTHROPIC_API_KEY
python -m src.pipeline                                          # defaults
python -m src.pipeline --count 3 --tone absurdist --platform linkedin
```

## Key Constraints
- **No external scheduler in Phase 1** — manual CLI only
- **No server** — local script, no FastAPI/web layer yet
- **DuckDuckGo search has no API key** — keep it that way; don't add SerpAPI or similar
- **Max 5 tool-use rounds** in Stage 2 — do not increase without good reason
- **No hashtags** in Twitter posts — they're explicitly banned in the prompt
