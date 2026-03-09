"""Shared data models for the fun-ai-news pipeline."""

from dataclasses import dataclass, field
from enum import StrEnum


class PostTone(StrEnum):
    SARCASTIC = "sarcastic"
    ABSURDIST = "absurdist"
    WELL_ACTUALLY = "well_actually"


@dataclass
class NewsItem:
    """A single AI news story from the harvest stage."""

    title: str
    url: str
    source: str
    points: int = 0
    summary: str = ""  # filled in by harvest stage via Claude


@dataclass
class HistoricalParallel:
    """A prior-art finding for a given news item."""

    original_idea: str          # short name of the old thing
    original_year: int          # approximate year
    original_context: str       # who made it / what it was called
    novelty_gap_years: int      # how many years ago this was "new"
    irony_quote: str            # a real or representative quote from back then


@dataclass
class MockPost:
    """The final output: a funny post ready to share."""

    news_item: NewsItem
    parallel: HistoricalParallel
    post_text: str
    tone: PostTone
    platform: str = "twitter"   # twitter | linkedin


@dataclass
class PipelineResult:
    """Aggregated output of one full pipeline run."""

    posts: list[MockPost] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
