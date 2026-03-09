"""
Stage 3 – Mockery Engine.

Takes a NewsItem + HistoricalParallel and produces a funny post via Claude.
"""

from .llm_client import LLMClient
from .models import HistoricalParallel, MockPost, NewsItem, PostTone

_TONE_INSTRUCTIONS: dict[PostTone, str] = {
    PostTone.SARCASTIC: (
        "Write like a tired senior developer who has seen this exact thing hyped three times "
        "before and is barely suppressing their eye-roll. Use dry sarcasm, short punchy lines, "
        "and at least one 'but this time it has [trivial difference] so it's completely different'."
    ),
    PostTone.ABSURDIST: (
        "Write in an absurdist style: take the historical parallel to an extreme logical "
        "conclusion, compare it to something ridiculous (medieval monks, carrier pigeons, "
        "Roman aqueducts), and end with a completely unhinged observation."
    ),
    PostTone.WELL_ACTUALLY: (
        "Write as an insufferable LinkedIn thought-leader who is 'just asking questions' and "
        "'actually' corrects the hype with barely-concealed smugness. Include at least one "
        "'I wrote about this in 20XX' reference and an unsolicited career advice at the end."
    ),
}

_TWITTER_INSTRUCTION = (
    "Format as a Twitter/X thread: start with a hook tweet (max 280 chars), "
    "then 3-4 numbered follow-up tweets (each max 280 chars). "
    "Use line breaks between tweets. No hashtags (they're cringe)."
)

_LINKEDIN_INSTRUCTION = (
    "Format as a LinkedIn post: start with a provocative one-liner, "
    "then 5-7 short paragraphs with lots of line breaks for 'engagement bait'. "
    "End with a humble-brag and a question to drive comments."
)


def generate_post(
    item: NewsItem,
    parallel: HistoricalParallel,
    tone: PostTone = PostTone.SARCASTIC,
    platform: str = "twitter",
    client: LLMClient | None = None,
) -> MockPost:
    """Generate a funny mocking post for a news item and its historical parallel.

    Args:
        item: The AI news story.
        parallel: The historical prior art found in stage 2.
        tone: The comedic tone to use.
        platform: Output format — 'twitter' or 'linkedin'.
        client: Optional pre-created LLMClient.

    Returns:
        A MockPost with the generated text.
    """
    if client is None:
        import os
        client = LLMClient(provider="anthropic", api_key=os.environ["ANTHROPIC_API_KEY"])

    platform_instruction = (
        _TWITTER_INSTRUCTION if platform == "twitter" else _LINKEDIN_INSTRUCTION
    )

    prompt = f"""You are writing a funny, mocking social media post about AI hype.

CURRENT "INNOVATION":
Title: {item.title}
What it claims to do: {item.summary}

EMBARRASSING HISTORICAL PARALLEL:
The old thing: {parallel.original_idea} ({parallel.original_year})
Who made it: {parallel.original_context}
Years of "novelty": {parallel.novelty_gap_years} years ago
A quote from back then: "{parallel.irony_quote}"

TONE INSTRUCTIONS:
{_TONE_INSTRUCTIONS[tone]}

FORMAT INSTRUCTIONS:
{platform_instruction}

Write the post now. Be funny. Be specific. Name the old thing explicitly.
Do not add any preamble — just output the post text directly."""

    response = client.complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )

    post_text = response.content[0].text.strip()
    return MockPost(
        news_item=item,
        parallel=parallel,
        post_text=post_text,
        tone=tone,
        platform=platform,
    )
