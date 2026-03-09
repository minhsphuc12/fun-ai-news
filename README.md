# AI Déjà Vu Generator

A local Python CLI that finds the top AI "innovations" in the news, exposes their embarrassing historical parallels, and generates funny mocking social media posts about them — because nothing in AI is actually new.

---

## How It Works

Three-stage linear pipeline:

```
Harvest  ──►  Déjà Vu Detector  ──►  Mockery Engine
(Stage 1)       (Stage 2)              (Stage 3)
```

### Stage 1 — Harvest (`src/harvest.py`)
- Queries the **HackerNews Algolia API** (free, no auth) across 8 AI keywords
- Deduplicates by story ID, sorts by HN points, takes the top N
- Calls **Claude** to compress each headline into a one-sentence plain-English summary

### Stage 2 — Déjà Vu Detector (`src/deja_vu.py`)
- Runs an **agentic tool-use loop**: Claude acts as a cynical tech historian
- Claude can call a `web_search` tool (backed by **DuckDuckGo**, no API key needed) up to 5 times to verify dates and find specific prior art
- Returns structured JSON: the old idea, the year it existed, who made it, the novelty gap in years, and an irony quote from back then

### Stage 3 — Mockery Engine (`src/mockery.py`)
- Takes the news item + historical parallel and asks **Claude** to write a funny post
- Three comedic tones and two output formats (see below)

### Orchestrator (`src/pipeline.py`)
- Rich terminal UI with spinners and panels
- Saves all results to `output/posts_<timestamp>.json`
- Catches per-story errors so one failure doesn't abort the run

---

## Data Models (`src/models.py`)

```
NewsItem          ← title, url, source, points, summary
    │
    ▼
HistoricalParallel ← original_idea, original_year, original_context,
    │                  novelty_gap_years, irony_quote
    ▼
MockPost          ← news_item, parallel, post_text, tone, platform
    │
    ▼
PipelineResult    ← posts[], errors[]
```

---

## Comedic Tones

| Tone | Character |
|---|---|
| `sarcastic` | Tired senior dev, dry eye-roll, "but this time it has [trivial difference]" |
| `absurdist` | Compares AI to medieval monks or Roman aqueducts, ends in something unhinged |
| `well_actually` | Insufferable LinkedIn thought-leader, "I wrote about this in 20XX" |

## Output Formats

| Platform | Format |
|---|---|
| `twitter` | Hook tweet (≤280 chars) + 3–4 numbered follow-up tweets (each ≤280 chars), no hashtags |
| `linkedin` | Provocative opener, 5–7 short paragraphs, humble-brag + engagement question |

---

## Setup

**Requirements:** Python 3.11+

```bash
# Install dependencies
pip install -e .

# Configure secrets
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

`.env` variables:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `NEWS_COUNT` | `5` | Number of stories to fetch and process |
| `POST_TONE` | `sarcastic` | Default comedic tone |

---

## Usage

```bash
# Run with defaults (5 stories, sarcastic, twitter)
python -m src.pipeline

# Custom options
python -m src.pipeline --count 3 --tone absurdist --platform linkedin
python -m src.pipeline --count 10 --tone well_actually --platform twitter

# Or use the installed script entry point
fun-ai-news --count 5 --tone sarcastic --platform linkedin
```

**CLI flags:**

| Flag | Choices | Default |
|---|---|---|
| `--count` | any int | `5` (or `NEWS_COUNT` env var) |
| `--tone` | `sarcastic`, `absurdist`, `well_actually` | `sarcastic` (or `POST_TONE` env var) |
| `--platform` | `twitter`, `linkedin` | `twitter` |

---

## Output

Results are saved to `output/posts_<timestamp>.json`:

```json
{
  "generated_at": "20260309_142537",
  "posts": [
    {
      "title": "...",
      "url": "...",
      "summary": "...",
      "parallel": {
        "original_idea": "Expert Systems",
        "original_year": 1980,
        "original_context": "Developed at Carnegie Mellon...",
        "novelty_gap_years": 46,
        "irony_quote": "This will replace human experts within a decade."
      },
      "tone": "sarcastic",
      "platform": "twitter",
      "post_text": "..."
    }
  ],
  "errors": []
}
```

---

## Project Structure

```
fun-ai-news/
├── src/
│   ├── __init__.py
│   ├── models.py      # Shared dataclass contracts: NewsItem, HistoricalParallel, MockPost
│   ├── harvest.py     # Stage 1: HN Algolia API + Claude summarisation
│   ├── deja_vu.py     # Stage 2: Claude + DuckDuckGo agentic tool-use loop
│   ├── mockery.py     # Stage 3: Claude generates funny post per tone/platform
│   └── pipeline.py    # CLI orchestrator with Rich UI, saves to output/
├── output/            # Generated JSON results (gitignored)
├── .env.example       # Environment variable template
├── .gitignore
└── pyproject.toml     # Dependencies and project metadata
```

---

## Tech Stack

| Library | Purpose |
|---|---|
| `anthropic` | Claude SDK — stages 1, 2, 3 |
| `httpx` | Async HTTP client for HN API |
| `duckduckgo-search` | Free web search for stage 2 (no API key needed) |
| `rich` | Terminal UI: spinners, panels, coloured output |
| `python-dotenv` | Load `.env` secrets |
| `pydantic` | Listed as dep; dataclasses used for models |

---

## Roadmap

### Phase 2 — Scheduled + Multi-Source
- Add more news sources: Arxiv, ProductHunt, TechCrunch RSS, X/Twitter search
- Weekly cron job to run automatically
- De-duplicate across runs (don't mock the same story twice) via local SQLite

### Phase 3 — Output Distribution
- Auto-post to Twitter/X and LinkedIn via their APIs
- Push results to a Notion database for review before publishing
- Email digest mode

### Phase 4 — Quality & Variety
- Rotating tone per post (not the same tone for all stories)
- Meme caption mode (text overlay on stock image)
- "Novelty score" threshold — skip stories where the parallel is weak
- Human review/edit step before finalising

### Phase 5 — Web UI (optional)
- Simple FastAPI + HTMX interface to browse and approve posts
- One-click publish buttons per post
