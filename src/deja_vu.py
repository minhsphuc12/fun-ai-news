"""
Stage 2 – Déjà Vu Detector.

For each news item, asks Claude (with optional DuckDuckGo web search as a tool)
to find the oldest, most embarrassing historical parallel.
"""

import json
import os

from anthropic import Anthropic
from duckduckgo_search import DDGS

from .models import HistoricalParallel, NewsItem

_SYSTEM_PROMPT = """\
You are a cynical tech historian. Your job is to find the oldest, most embarrassing
historical parallel for any "new" AI innovation — proving it's not new at all.

You have access to a web_search tool. Use it when you need to verify dates or find
specific prior art. Be precise about years. Be merciless about novelty claims.

Respond ONLY with valid JSON matching this schema:
{
  "original_idea": "<short name of the old thing, e.g. 'Expert Systems'>",
  "original_year": <integer year>,
  "original_context": "<who made it / what it was called back then>",
  "novelty_gap_years": <integer: current_year - original_year>,
  "irony_quote": "<a real or plausible quote from back then hyping the same idea>"
}
"""


def _web_search(query: str, max_results: int = 5) -> str:
    """Run a DuckDuckGo search and return results as a formatted string."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    if not results:
        return "No results found."
    return "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('href', '')}\nSnippet: {r.get('body', '')}"
        for r in results
    )


def find_parallel(item: NewsItem, client: Anthropic | None = None) -> HistoricalParallel:
    """Find the best historical parallel for a given AI news item.

    Uses Claude with tool_use + DuckDuckGo web search as a grounding tool.

    Args:
        item: The news item to analyse.
        client: Optional pre-created Anthropic client.

    Returns:
        A HistoricalParallel describing the prior art.
    """
    if client is None:
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    tools = [
        {
            "name": "web_search",
            "description": "Search the web for information about a topic.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"],
            },
        }
    ]

    user_message = (
        f"Find the oldest historical parallel for this AI 'innovation':\n\n"
        f"Title: {item.title}\n"
        f"Summary: {item.summary}\n\n"
        f"Search the web if needed to find specific prior art with accurate dates."
    )

    messages = [{"role": "user", "content": user_message}]

    # agentic loop: Claude may call web_search multiple times
    for _ in range(5):  # max 5 tool-use rounds
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # collect any text blocks for the final parse
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if response.stop_reason == "end_turn" or not tool_calls:
            # final answer — parse the JSON from the last text block
            raw_json = text_blocks[-1].text.strip() if text_blocks else "{}"
            # strip markdown fences if present
            if raw_json.startswith("```"):
                raw_json = raw_json.split("```")[1]
                if raw_json.startswith("json"):
                    raw_json = raw_json[4:]
            data = json.loads(raw_json)
            return HistoricalParallel(**data)

        # handle tool calls, feed results back
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            search_result = _web_search(tc.input["query"])
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": search_result,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"Déjà vu detection did not converge for: {item.title}")
