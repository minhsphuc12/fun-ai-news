"""
Pipeline orchestrator — runs all 3 stages and displays results.

Usage:
    python -m src.pipeline [--count 5] [--tone sarcastic] [--platform twitter]
"""

import asyncio
import json
import os
import sys
from argparse import ArgumentParser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.text import Text

from .deja_vu import find_parallel
from .harvest import harvest
from .llm_client import LLMClient
from .mockery import generate_post
from .models import MockPost, PostTone, PipelineResult

console = Console()


def _display_post(post: MockPost, index: int) -> None:
    """Render a single MockPost to the terminal with Rich formatting."""
    header = Text()
    header.append(f"#{index}  ", style="bold cyan")
    header.append(post.news_item.title, style="bold white")

    meta = (
        f"[dim]Source:[/dim] {post.news_item.source}  "
        f"[dim]Points:[/dim] {post.news_item.points}  "
        f"[dim]Tone:[/dim] {post.tone.value}  "
        f"[dim]Platform:[/dim] {post.platform}"
    )

    parallel_info = (
        f"[yellow]Historical parallel:[/yellow] "
        f"{post.parallel.original_idea} ({post.parallel.original_year}) "
        f"— {post.parallel.novelty_gap_years} years ago\n"
        f"[dim italic]\"{post.parallel.irony_quote}\"[/dim italic]"
    )

    console.print(Rule(style="dim"))
    console.print(Panel(str(header), expand=False, border_style="cyan"))
    console.print(meta)
    console.print()
    console.print(parallel_info)
    console.print()
    console.print(
        Panel(
            post.post_text,
            title=f"[bold green]Generated {post.platform.capitalize()} Post[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


def _save_output(result: PipelineResult) -> Path:
    """Persist results to output/posts_<timestamp>.json."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"posts_{timestamp}.json"

    serialisable = {
        "generated_at": timestamp,
        "posts": [
            {
                "title": p.news_item.title,
                "url": p.news_item.url,
                "summary": p.news_item.summary,
                "parallel": asdict(p.parallel),
                "tone": p.tone.value,
                "platform": p.platform,
                "post_text": p.post_text,
            }
            for p in result.posts
        ],
        "errors": result.errors,
    }
    out_path.write_text(json.dumps(serialisable, indent=2, ensure_ascii=False))
    return out_path


async def run(count: int, tone: PostTone, platform: str, client: LLMClient) -> PipelineResult:
    """Execute the full 3-stage pipeline."""
    result = PipelineResult()

    # ── Stage 1: Harvest ────────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        task = progress.add_task("Stage 1 — Harvesting AI news from HackerNews…", total=None)
        news_items = await harvest(count, client)
        progress.update(task, completed=True)

    console.print(f"[bold]Fetched {len(news_items)} stories.[/bold]\n")
    for i, item in enumerate(news_items, 1):
        console.print(f"  {i}. {item.title} [dim]({item.points} pts)[/dim]")
    console.print()

    # ── Stages 2 + 3: Déjà Vu + Mockery ────────────────────────────────────
    for i, item in enumerate(news_items, 1):
        console.print(f"[cyan]Processing {i}/{len(news_items)}:[/cyan] {item.title}")

        try:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          console=console) as progress:
                t = progress.add_task("  Stage 2 — Finding historical parallel…", total=None)
                parallel = find_parallel(item, client)
                progress.update(t, completed=True)

            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          console=console) as progress:
                t = progress.add_task("  Stage 3 — Generating mock post…", total=None)
                post = generate_post(item, parallel, tone, platform, client)
                progress.update(t, completed=True)

            result.posts.append(post)

        except Exception as exc:  # noqa: BLE001
            error_msg = f"Failed on '{item.title}': {exc}"
            console.print(f"  [red]✗ {error_msg}[/red]")
            result.errors.append(error_msg)

    return result


def main() -> None:
    load_dotenv()

    parser = ArgumentParser(description="AI News Déjà Vu & Mockery Generator")
    parser.add_argument("--count", type=int, default=int(os.getenv("NEWS_COUNT", "5")),
                        help="Number of news stories to process (default: 5)")
    parser.add_argument("--tone", choices=[t.value for t in PostTone],
                        default=os.getenv("POST_TONE", PostTone.SARCASTIC.value),
                        help="Comedic tone for generated posts")
    parser.add_argument("--platform", choices=["twitter", "linkedin"], default="twitter",
                        help="Output format")
    parser.add_argument("--provider", choices=["anthropic", "gemini"],
                        default=os.getenv("LLM_PROVIDER", "anthropic"),
                        help="LLM provider to use (default: anthropic)")
    args = parser.parse_args()

    # Resolve and validate the API key for the chosen provider — never log it
    key_env = "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "GEMINI_API_KEY"
    api_key = os.environ.get(key_env)
    if not api_key:
        console.print(
            f"[red]Error: {key_env} not set. "
            f"Copy .env.example → .env and add your key.[/red]"
        )
        sys.exit(1)

    client = LLMClient(provider=args.provider, api_key=api_key)
    tone = PostTone(args.tone)

    console.print(Rule("[bold magenta]AI News Déjà Vu Generator[/bold magenta]"))
    console.print(
        f"Provider: [cyan]{args.provider}[/cyan]  "
        f"Model: [cyan]{client.model}[/cyan]  "
        f"Count: [cyan]{args.count}[/cyan]  "
        f"Tone: [cyan]{tone.value}[/cyan]  "
        f"Platform: [cyan]{args.platform}[/cyan]\n"
    )

    result = asyncio.run(run(args.count, tone, args.platform, client))

    # ── Display results ──────────────────────────────────────────────────────
    console.print(Rule("[bold green]Generated Posts[/bold green]"))
    for i, post in enumerate(result.posts, 1):
        _display_post(post, i)

    if result.errors:
        console.print(Rule("[bold red]Errors[/bold red]"))
        for err in result.errors:
            console.print(f"  [red]• {err}[/red]")

    out_path = _save_output(result)
    console.print(Rule())
    console.print(f"[bold]Done.[/bold] {len(result.posts)} posts saved to [cyan]{out_path}[/cyan]")


if __name__ == "__main__":
    main()
