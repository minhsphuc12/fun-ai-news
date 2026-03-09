"""
Stage 1 – News Harvest.

Fetches the top AI-related stories from HackerNews (Algolia API, no key needed),
then uses Claude to produce a one-sentence plain-English summary of each story.
"""

import asyncio
import os

import httpx
from anthropic import Anthropic

from .models import NewsItem

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
AI_KEYWORDS = ["AI", "LLM", "GPT", "Claude", "Gemini", "agent", "neural", "machine learning"]


async def _fetch_hn_stories(count: int, client: httpx.AsyncClient) -> list[dict]:
    """Pull top HN stories matching AI keywords."""
    stories: list[dict] = []
    seen: set[int] = set()

    for keyword in AI_KEYWORDS:
        if len(stories) >= count * 2:  # collect extra, then trim
            break
        resp = await client.get(
            HN_SEARCH_URL,
            params={"query": keyword, "tags": "story", "hitsPerPage": 10},
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            story_id = hit.get("objectID")
            if story_id and story_id not in seen and hit.get("title"):
                seen.add(story_id)
                stories.append(hit)

    # sort by HN points descending, take top `count`
    stories.sort(key=lambda h: h.get("points") or 0, reverse=True)
    return stories[:count]


def _summarise_titles(titles: list[str], client: Anthropic) -> list[str]:
    """Ask Claude to summarise each headline in one plain sentence."""
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": (
                    "Below are AI news headlines. For each one, write a single plain-English "
                    "sentence (max 20 words) summarising what the supposed innovation is. "
                    "Return ONLY the numbered list, no extra text.\n\n" + numbered
                ),
            }
        ],
    )
    lines = message.content[0].text.strip().splitlines()
    summaries: list[str] = []
    for line in lines:
        # strip leading "1. " etc.
        parts = line.split(". ", 1)
        summaries.append(parts[1].strip() if len(parts) == 2 else line.strip())
    return summaries


async def harvest(count: int = 5) -> list[NewsItem]:
    """Fetch and summarise the top `count` AI news stories.

    Args:
        count: Number of stories to return.

    Returns:
        List of NewsItem with summaries filled in.
    """
    anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    async with httpx.AsyncClient(timeout=15) as http:
        raw_stories = await _fetch_hn_stories(count, http)

    if not raw_stories:
        return []

    titles = [s["title"] for s in raw_stories]
    summaries = _summarise_titles(titles, anthropic_client)

    items: list[NewsItem] = []
    for story, summary in zip(raw_stories, summaries):
        items.append(
            NewsItem(
                title=story["title"],
                url=story.get("url") or f"https://news.ycombinator.com/item?id={story['objectID']}",
                source="HackerNews",
                points=story.get("points") or 0,
                summary=summary,
            )
        )
    return items


if __name__ == "__main__":
    results = asyncio.run(harvest())
    for item in results:
        print(f"[{item.points}] {item.title}\n  → {item.summary}\n")
