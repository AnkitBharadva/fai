"""CLI entrypoint for YouTube Video Scraper."""

from typing import List, Optional, Tuple
import click
from rich.console import Console
from rich.table import Table

from src.config_loader import load_config, merge_config_with_cli
from src.db import ManifestDB
from src.orchestrator import ScrapingOrchestrator
from src.community import CommunityExtractor

console = Console()


@click.group()
def cli():
    """Production-grade YouTube Video Scraper CLI."""
    pass


@cli.command()
@click.option("--url", "-u", multiple=True, help="YouTube video URL or video ID (can specify multiple).")
@click.option("--channel", "-c", help="YouTube channel URL.")
@click.option("--playlist", "-p", help="YouTube playlist URL.")
@click.option("--file", "-f", help="Path to text file containing YouTube URLs/IDs (one per line).")
@click.option("--quality", "-q", "--resolution", help="Target video resolution/quality (e.g. 144p, 360p, 480p, 720p, 1080p, 4k, best, worst).")
@click.option("--extract-frames", is_flag=True, default=False, help="Extract video frames using ffmpeg.")
@click.option("--frame-skip", type=int, help="Number of frames to skip during frame extraction (e.g., 10 = extract 1 frame every 10 frames).")
@click.option("--extract-audio/--skip-audio", default=True, help="Extract high-quality audio track into separate audio folder (default: True).")
@click.option("--audio-format", default="mp3", help="Target audio format (mp3, m4a, wav, flac). Default: mp3.")
@click.option("--cookies-dir", help="Path to cookies directory or file (default: ./cookies).")
@click.option("--max-videos", type=int, help="Maximum number of videos to process.")
@click.option("--workers", "-w", type=int, help="Number of parallel worker threads.")
@click.option("--force", is_flag=True, default=False, help="Force re-scraping even if marked completed in manifest.")
@click.option("--skip-download", is_flag=True, default=False, help="Skip downloading video stream.")
@click.option("--max-comments", type=int, help="Maximum comments to extract per video (default: unlimited).")
@click.option("--config", help="Path to custom config.yaml file.")
def scrape(
    url: Tuple[str, ...],
    channel: Optional[str],
    playlist: Optional[str],
    file: Optional[str],
    quality: Optional[str],
    extract_frames: bool,
    frame_skip: Optional[int],
    extract_audio: bool,
    audio_format: str,
    cookies_dir: Optional[str],
    max_videos: Optional[int],
    workers: Optional[int],
    force: bool,
    skip_download: bool,
    max_comments: Optional[int],
    config: Optional[str],
):
    """Scrape videos, metadata, descriptions, transcripts, comments, audio, and extract frames."""
    cfg = load_config(config or "config.yaml")

    cli_overrides = {}
    if workers is not None:
        cli_overrides["workers"] = workers
    if skip_download:
        cli_overrides["download_video"] = False
    if max_comments is not None:
        cli_overrides["max_comments"] = max_comments
    if quality is not None:
        cli_overrides["quality_ceiling"] = quality
    if extract_frames:
        cli_overrides["extract_frames"] = True
    if frame_skip is not None:
        cli_overrides["extract_frames"] = True
        cli_overrides["frame_skip"] = frame_skip
    if extract_audio is not None:
        cli_overrides["extract_audio"] = extract_audio
    if audio_format:
        cli_overrides["audio_format"] = audio_format
    if cookies_dir:
        cli_overrides["cookies_dir"] = cookies_dir

    final_cfg = merge_config_with_cli(cfg, **cli_overrides)
    orchestrator = ScrapingOrchestrator(final_cfg)

    url_list = list(url) if url else None
    orchestrator.run(
        urls=url_list,
        file_path=file,
        channel_url=channel,
        playlist_url=playlist,
        max_videos=max_videos,
        workers=workers,
        force=force,
    )


@cli.command()
@click.option("--channel", "-c", help="YouTube channel URL.")
@click.option("--playlist", "-p", help="YouTube playlist URL.")
@click.option("--url", "-u", multiple=True, help="YouTube video URL or video ID.")
@click.option("--file", "-f", help="Path to text file containing YouTube URLs/IDs.")
@click.option("--max-videos", type=int, help="Maximum number of videos to enqueue.")
@click.option("--config", help="Path to custom config.yaml file.")
def produce(
    channel: Optional[str],
    playlist: Optional[str],
    url: Tuple[str, ...],
    file: Optional[str],
    max_videos: Optional[int],
    config: Optional[str],
):
    """Producer Agent: Enumerate channel/playlist videos and enqueue tasks into atomic database queue."""
    cfg = load_config(config or "config.yaml")
    orchestrator = ScrapingOrchestrator(cfg)
    url_list = list(url) if url else None
    count = orchestrator.produce_channel_tasks(
        channel_url=channel,
        playlist_url=playlist,
        urls=url_list,
        file_path=file,
        max_videos=max_videos,
    )
    console.print(f"[bold green]Producer successfully enqueued {count} pending task(s) into queue.[/bold green]")


@cli.command()
@click.option("--workers", "-w", type=int, help="Number of parallel worker consumer agents.")
@click.option("--cookies-dir", help="Path to cookies directory (default: ./cookies).")
@click.option("--config", help="Path to custom config.yaml file.")
def consume(workers: Optional[int], cookies_dir: Optional[str], config: Optional[str]):
    """Consumer Agent: Run parallel worker agents pulling and processing tasks from queue."""
    cfg = load_config(config or "config.yaml")
    if workers is not None:
        cfg["workers"] = workers
    if cookies_dir:
        cfg["cookies_dir"] = cookies_dir
    orchestrator = ScrapingOrchestrator(cfg)
    orchestrator.consume_queue(workers=workers)


@cli.command()
@click.option("--config", help="Path to custom config.yaml file.")
def status(config: Optional[str]):
    """Show manifest database status summary."""
    cfg = load_config(config or "config.yaml")
    db = ManifestDB(cfg.get("db_path", "manifest.db"))
    records = db.get_all()

    table = Table(title="YouTube Scraper Manifest Status Summary")
    table.add_column("Status", style="bold cyan")
    table.add_column("Count", style="bold green")

    status_counts = {"pending": 0, "in_progress": 0, "done": 0, "failed": 0}
    for r in records:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    for st, count in status_counts.items():
        table.add_row(st.capitalize(), str(count))

    console.print(table)
    console.print(f"\n[bold]Total Tracked Videos:[/bold] {len(records)}")


@cli.command()
@click.option("--workers", "-w", type=int, help="Number of parallel worker threads.")
@click.option("--config", help="Path to custom config.yaml file.")
def retry_failed(workers: Optional[int], config: Optional[str]):
    """Retry all videos marked as failed in the manifest."""
    cfg = load_config(config or "config.yaml")
    db = ManifestDB(cfg.get("db_path", "manifest.db"))
    failed_records = db.get_failed()

    if not failed_records:
        console.print("[bold green]No failed videos to retry![/bold green]")
        return

    failed_ids = [r.video_id for r in failed_records]
    console.print(f"[bold yellow]Retrying {len(failed_ids)} failed video(s)...[/bold yellow]")

    orchestrator = ScrapingOrchestrator(cfg)
    orchestrator.run(urls=failed_ids, workers=workers, force=True)


@cli.command()
@click.option("--channel", "-c", required=True, help="YouTube channel URL or Community URL.")
@click.option("--max-posts", type=int, help="Maximum number of community posts to scrape (default: all).")
@click.option("--extract-comments/--skip-comments", default=True, help="Extract comments and threaded replies for each post.")
@click.option("--max-comments", type=int, help="Maximum comments to extract per post (default: all).")
@click.option("--cookies-file", help="Path to cookies file (e.g., ./cookies/jaman.txt).")
@click.option("--config", help="Path to custom config.yaml file.")
def community(
    channel: str,
    max_posts: Optional[int],
    extract_comments: bool,
    max_comments: Optional[int],
    cookies_file: Optional[str],
    config: Optional[str],
):
    """Scrape channel Community Tab posts, polls, images, likes, and threaded comments."""
    cfg = load_config(config or "config.yaml")
    data_dir = cfg.get("data_dir", "./data")
    cookie = cookies_file or cfg.get("cookies_file")

    console.print(f"[bold cyan]Starting YouTube Community Tab Scraper for:[/bold cyan] {channel}\n")

    extractor = CommunityExtractor(output_dir=data_dir, cookies_file=cookie)
    posts, summary = extractor.scrape_channel_community(
        channel_url=channel,
        max_posts=max_posts,
        extract_comments=extract_comments,
        max_comments_per_post=max_comments,
    )

    table = Table(title=f"Community Scrape Summary: {summary.channel_name}")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Channel Name", summary.channel_name)
    table.add_row("Total Posts Found", str(summary.total_posts_found))
    table.add_row("Successfully Scraped", str(summary.posts_scraped_success))
    table.add_row("Failed Posts", str(summary.posts_scraped_failed))
    table.add_row("Total Comments Scraped", str(summary.total_comments_extracted))
    table.add_row("Total Polls Found", str(summary.total_polls_extracted))
    table.add_row("Total Images Found", str(summary.total_images_extracted))
    table.add_row("Output Directory", summary.output_dir)

    console.print("\n")
    console.print(table)

    if summary.errors:
        console.print(f"\n[bold red]Encountered {len(summary.errors)} issue(s):[/bold red]")
        for err in summary.errors[:5]:
            console.print(f" - {err}")


if __name__ == "__main__":
    cli()

