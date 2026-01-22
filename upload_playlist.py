#!/usr/bin/env python3
"""
Upload YouTube playlist to NotebookLM with Simplified → Traditional Chinese conversion.

Usage:
    python3 upload_playlist.py "https://www.youtube.com/playlist?list=PLxxx"
    python3 upload_playlist.py "https://www.youtube.com/watch?v=xxx&list=PLyyy&index=1"
    python3 upload_playlist.py -i 25 "https://..."   # Custom interval (25 seconds)
"""

import sys
import json
import subprocess
import time
import argparse
from urllib.parse import urlparse, parse_qs
from pathlib import Path

import opencc

# Constants
DEFAULT_DELAY_SECONDS = 20


def extract_playlist_id(url: str) -> str | None:
    """Extract playlist ID from various YouTube URL formats."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # Check for 'list' parameter in query string
    if 'list' in query_params:
        return query_params['list'][0]

    return None


def build_playlist_url(playlist_id: str) -> str:
    """Build a canonical playlist URL from playlist ID."""
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def run_command(cmd: list[str], capture_json: bool = False) -> tuple[bool, str | dict]:
    """Run a command and return (success, output/parsed_json)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return False, result.stderr or result.stdout

        output = result.stdout.strip()
        if capture_json:
            try:
                return True, json.loads(output)
            except json.JSONDecodeError:
                return False, f"Failed to parse JSON: {output}"
        return True, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def check_notebook_selected() -> tuple[bool, str, str]:
    """Check if a notebook is selected. Returns (is_selected, notebook_id, notebook_title)."""
    success, output = run_command(["notebooklm", "status", "--json"], capture_json=True)

    if not success:
        return False, "", ""

    # Handle nested structure: {"notebook": {"id": "...", "title": "..."}}
    notebook = output.get("notebook", {})
    notebook_id = notebook.get("id", "") or output.get("notebook_id", "")
    title = notebook.get("title", "") or output.get("title", "")

    if not notebook_id:
        return False, "", ""

    return True, notebook_id, title


def get_playlist_videos(playlist_url: str) -> list[str]:
    """Extract all video URLs from a playlist using yt-dlp."""
    success, output = run_command([
        "yt-dlp",
        "--flat-playlist",
        "--print", "url",
        playlist_url
    ])

    if not success:
        print(f"Error extracting playlist: {output}", file=sys.stderr)
        return []

    return [line.strip() for line in output.split('\n') if line.strip()]


def add_source(url: str) -> tuple[bool, str, str]:
    """Add a YouTube URL as source. Returns (success, source_id, title)."""
    success, output = run_command(
        ["notebooklm", "source", "add", "--json", url],
        capture_json=True
    )

    if not success:
        return False, str(output), ""

    # Check for error in response
    if output.get("error"):
        return False, output.get("message", "Unknown error"), ""

    # Handle nested structure: {"source": {"id": "...", "title": "..."}}
    source = output.get("source", {})
    source_id = source.get("id", "") or output.get("source_id", "")
    title = source.get("title", "") or output.get("title", "")

    if not source_id:
        return False, f"No source_id in response: {output}", ""

    return True, source_id, title


def delete_source(source_id: str) -> bool:
    """Delete a source by ID."""
    success, _ = run_command(["notebooklm", "source", "delete", source_id, "--yes"])
    return success


def cleanup_error_sources(silent: bool = False) -> int:
    """Delete all sources with error status. Returns count of deleted sources."""
    success, output = run_command(
        ["notebooklm", "source", "list", "--json"],
        capture_json=True
    )

    if not success:
        return 0

    sources = output.get("sources", [])
    deleted = 0

    for s in sources:
        if s.get("status") == "error":
            source_id = s.get("id")
            title = s.get("title", "unknown")[:40]
            if not silent:
                print(f"  Deleting error source: {title}... ", end="", flush=True)
            if delete_source(source_id):
                if not silent:
                    print("OK")
                deleted += 1
            else:
                if not silent:
                    print("FAILED")

    return deleted


def wait_for_source_with_status(source_id: str) -> tuple[bool, str]:
    """Wait for source and check final status. Returns (success, status)."""
    # Wait for processing to complete
    run_command(["notebooklm", "source", "wait", source_id])

    # Check the final status via source list --json
    success, output = run_command(
        ["notebooklm", "source", "list", "--json"],
        capture_json=True
    )

    if not success:
        return False, "unknown"

    # Find this source in the list
    sources = output.get("sources", [])
    for s in sources:
        if s.get("id") == source_id:
            status = s.get("status", "unknown")
            if status == "error":
                return False, "error"
            elif status == "ready":
                return True, "ready"
            else:
                return False, status

    return False, "not_found"


def record_video2txt_url(index: int, url: str, elapsed_seconds: int, video2txt_file: Path):
    """Record whisper-converted URL to file with index number and elapsed time."""
    with open(video2txt_file, 'a', encoding='utf-8') as f:
        f.write(f"{index} {url} {elapsed_seconds}\n")


def record_skip_url(index: int, url: str, skip_file: Path):
    """Record skipped URL to file with index number."""
    with open(skip_file, 'a', encoding='utf-8') as f:
        f.write(f"{index} {url}\n")


def record_success_url(index: int, url: str, elapsed_seconds: int, ok_file: Path):
    """Record successful URL to file with index number and elapsed time."""
    with open(ok_file, 'a', encoding='utf-8') as f:
        f.write(f"{index} {url} {elapsed_seconds}\n")


def write_index_list(video_urls: list[str], playlist_url: str, index_file: Path):
    """Write playlist URLs to index.list file with playlist URL on first line."""
    with open(index_file, 'w', encoding='utf-8') as f:
        # First line: playlist URL marker
        f.write(f"# playlist: {playlist_url}\n")
        for i, url in enumerate(video_urls, 1):
            f.write(f"{i} {url}\n")


def read_playlist_url_from_index(index_file: Path) -> str | None:
    """Read playlist URL from first line of index.list."""
    if not index_file.exists():
        return None
    with open(index_file, 'r', encoding='utf-8') as f:
        first_line = f.readline().strip()
        if first_line.startswith("# playlist:"):
            return first_line.split("# playlist:", 1)[1].strip()
    return None


def load_ok_urls(ok_file: Path) -> set[str]:
    """Load successful URLs from ok file. Format: index url [elapsed]"""
    if not ok_file.exists():
        return set()
    urls = set()
    with open(ok_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                # Format: "index url elapsed" - extract url (2nd field)
                parts = line.split()
                if len(parts) >= 2:
                    urls.add(parts[1])
    return urls


def load_video2txt_urls(video2txt_file: Path) -> set[str]:
    """Load whisper-converted URLs from video2txt file. Format: index url elapsed"""
    if not video2txt_file.exists():
        return set()
    urls = set()
    with open(video2txt_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                # Format: "index url elapsed" - extract url (2nd field)
                parts = line.split()
                if len(parts) >= 2:
                    urls.add(parts[1])
    return urls


def rename_source(source_id: str, new_title: str) -> bool:
    """Rename a source."""
    success, _ = run_command(["notebooklm", "source", "rename", source_id, new_title])
    return success


def convert_to_traditional(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese."""
    converter = opencc.OpenCC('s2t')
    return converter.convert(text)


def whisper_fallback(video_url: str, video_title: str, transcripts_dir: Path) -> tuple[bool, str]:
    """
    Download audio from YouTube, transcribe with whisper, save both mp3 and txt.
    Shows real-time progress during transcription.
    Returns (success, txt_file_path).
    """
    import subprocess as sp
    import shutil

    # Create transcripts directory if needed
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # Convert title to Traditional Chinese and clean for filename
    traditional_title = convert_to_traditional(video_title)
    safe_title = "".join(c if c.isalnum() or c in ' -_' else '_' for c in traditional_title)[:100]
    mp3_file = transcripts_dir / f"{safe_title}.mp3"
    txt_file = transcripts_dir / f"{safe_title}.txt"

    print(f"  WHISPER: Downloading audio to {mp3_file.name}...")

    # Download audio directly to transcripts folder
    result = sp.run([
        "yt-dlp",
        "-x",  # Extract audio
        "--audio-format", "mp3",
        "-o", str(mp3_file),
        video_url
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  WHISPER: Failed to download audio")
        return False, ""

    # Find the actual audio file (yt-dlp may add extension)
    audio_files = list(transcripts_dir.glob(f"{safe_title}.*"))
    audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
    if not audio_files:
        print(f"  WHISPER: No audio file found")
        return False, ""
    actual_mp3 = audio_files[0]

    # Rename to .mp3 if different extension
    if actual_mp3.suffix != '.mp3':
        new_mp3 = actual_mp3.with_suffix('.mp3')
        shutil.move(str(actual_mp3), str(new_mp3))
        actual_mp3 = new_mp3

    print(f"  WHISPER: Transcribing {actual_mp3.name}...")

    # Transcribe with whisper - let output flow directly to terminal
    result = sp.run(
        [
            "whisper",
            str(actual_mp3),
            "--language", "Chinese",
            "--output_format", "txt",
            "--output_dir", str(transcripts_dir),
            "--verbose", "True",
            "--initial_prompt", "繁體中文"
        ]
    )  # No capture - output goes directly to terminal

    if result.returncode != 0:
        print(f"  WHISPER: Transcription failed")
        return False, ""

    # Whisper creates file with same name as audio but .txt extension
    whisper_txt = actual_mp3.with_suffix('.txt')
    if not whisper_txt.exists():
        print(f"  WHISPER: No transcript file found")
        return False, ""

    # Read and convert to Traditional Chinese
    with open(whisper_txt, 'r', encoding='utf-8') as f:
        transcript = f.read()

    traditional_transcript = convert_to_traditional(transcript)

    # Overwrite with Traditional Chinese version
    with open(whisper_txt, 'w', encoding='utf-8') as f:
        f.write(traditional_transcript)

    print(f"  WHISPER: Saved mp3: {actual_mp3}")
    print(f"  WHISPER: Saved txt: {whisper_txt}")

    return True, str(whisper_txt)


def get_video_title(video_url: str) -> str:
    """Get video title using yt-dlp."""
    success, output = run_command([
        "yt-dlp",
        "--print", "title",
        "--no-download",
        video_url
    ])
    if success and output:
        return output.strip()
    return f"Video"


def add_text_source(txt_file: str, title: str) -> tuple[bool, str]:
    """Add a text file as source to NotebookLM. Returns (success, source_id)."""
    success, output = run_command(
        ["notebooklm", "source", "add", "--json", "--type", "text", "--title", title, txt_file],
        capture_json=True
    )

    if not success:
        return False, str(output)

    if output.get("error"):
        return False, output.get("message", "Unknown error")

    source = output.get("source", {})
    source_id = source.get("id", "") or output.get("source_id", "")

    if not source_id:
        return False, f"No source_id in response"

    return True, source_id


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Upload YouTube playlist to NotebookLM with Simplified → Traditional Chinese conversion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 upload_playlist.py "https://www.youtube.com/playlist?list=PLxxx"
  python3 upload_playlist.py "https://www.youtube.com/watch?v=abc&list=PLxxx"
  python3 upload_playlist.py -i 25 "https://..."      # 25 second interval
  python3 upload_playlist.py -r                       # Resume (URL from index.list)
  python3 upload_playlist.py -r "https://..."         # Resume with explicit URL
  python3 upload_playlist.py --retry 3 "https://..."  # Max 3 retries before whisper
        """
    )
    parser.add_argument(
        "url",
        nargs="?",  # Optional when using -r
        default=None,
        help="YouTube playlist URL (optional with -r if index.list exists)"
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=DEFAULT_DELAY_SECONDS,
        metavar="SECONDS",
        help=f"Delay between uploads in seconds (default: {DEFAULT_DELAY_SECONDS})"
    )
    parser.add_argument(
        "-r", "--resume",
        action="store_true",
        help="Resume from last successful URL in index.list, also retry failed URLs"
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=2,
        metavar="N",
        help="Max retry attempts before whisper fallback (default: 2)"
    )
    parser.add_argument(
        "--without-whisper",
        action="store_true",
        help="Disable whisper fallback (just skip failed videos)"
    )
    return parser.parse_args()


def main():
    print()  # Empty line prefix for readability

    args = parse_args()
    url = args.url
    delay_seconds = args.interval
    resume_mode = args.resume
    max_retries = args.retry
    use_whisper = not args.without_whisper

    # File paths (in current directory)
    index_file = Path("index.list")
    ok_file = Path("add_source_ok.txt")
    video2txt_file = Path("add_source_video2txt.txt")  # For whisper fallback successes
    skip_file = Path("add_source_skip.txt")  # For skipped videos (when whisper disabled)
    transcripts_dir = Path("transcripts")  # For whisper transcripts

    # 1. Get playlist URL (from arg or index.list)
    if url is None:
        if not resume_mode:
            print("Error: URL is required (or use -r to resume from index.list)", file=sys.stderr)
            sys.exit(1)
        # Try to read from index.list
        url = read_playlist_url_from_index(index_file)
        if url is None:
            print("Error: No URL provided and no index.list found.", file=sys.stderr)
            print("Run without -r first to create index.list, or provide a URL.", file=sys.stderr)
            sys.exit(1)
        print(f"Resuming from index.list...")
    elif resume_mode and index_file.exists():
        # -r with explicit URL: verify it matches index.list
        stored_url = read_playlist_url_from_index(index_file)
        if stored_url:
            stored_playlist_id = extract_playlist_id(stored_url)
            given_playlist_id = extract_playlist_id(url)
            if stored_playlist_id and given_playlist_id and stored_playlist_id != given_playlist_id:
                print("Error: Playlist mismatch!", file=sys.stderr)
                print(f"  Given URL playlist:  {given_playlist_id}", file=sys.stderr)
                print(f"  index.list playlist: {stored_playlist_id}", file=sys.stderr)
                print("Remove index.list to start fresh, or omit URL to resume existing.", file=sys.stderr)
                sys.exit(1)

    # 2. Parse URL and extract playlist ID
    playlist_id = extract_playlist_id(url)
    if not playlist_id:
        print("Error: URL is not a playlist. Provide a YouTube playlist URL.", file=sys.stderr)
        print("The URL must contain a 'list=' parameter.", file=sys.stderr)
        sys.exit(1)

    playlist_url = build_playlist_url(playlist_id)
    print(f"Playlist ID: {playlist_id}")

    # 2. Check if notebook is selected
    is_selected, notebook_id, notebook_title = check_notebook_selected()
    if not is_selected:
        print("Error: No notebook selected.", file=sys.stderr)
        print("Run 'notebooklm use <notebook_id>' first.", file=sys.stderr)
        print("Use 'notebooklm list' to see available notebooks.", file=sys.stderr)
        sys.exit(1)

    print(f"Target notebook: {notebook_title} ({notebook_id[:8]}...)")
    print(f"Delay interval: {delay_seconds}s")
    print(f"Resume mode: {'ON' if resume_mode else 'OFF'}")
    print(f"Max retries: {max_retries}")
    print(f"Whisper fallback: {'ON' if use_whisper else 'OFF'}")

    # 2b. Cleanup any existing error sources
    print(f"\nChecking for error sources to clean up...")
    deleted_count = cleanup_error_sources()
    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} error source(s)")
    else:
        print("No error sources found")

    # 3. Get video URLs (from YouTube or index.list)
    # video_entries: list of (index, url) tuples
    video_entries = []
    url_to_index = {}  # Map URL to its index number

    if resume_mode and index_file.exists():
        # Resume: load from index.list
        print(f"\nLoading videos from {index_file}...")
        with open(index_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Format: "index url"
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2 and parts[1].startswith("http"):
                        idx = int(parts[0])
                        video_url = parts[1]
                        video_entries.append((idx, video_url))
                        url_to_index[video_url] = idx
        print(f"Loaded {len(video_entries)} videos from index.list")
    else:
        # Fresh: extract from YouTube
        print(f"\nExtracting videos from playlist...")
        video_urls = get_playlist_videos(playlist_url)

        if not video_urls:
            print("Error: No videos found in playlist.", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(video_urls)} videos")

        # Build entries with index
        for i, video_url in enumerate(video_urls, 1):
            video_entries.append((i, video_url))
            url_to_index[video_url] = i

        # Write to index.list (with playlist URL on first line)
        write_index_list(video_urls, playlist_url, index_file)
        print(f"Written to {index_file}")

    # 4. Load completed URLs from ok file and video2txt file
    completed_urls = load_ok_urls(ok_file)
    video2txt_urls = load_video2txt_urls(video2txt_file)
    all_completed = completed_urls | video2txt_urls


    # 5. Determine pending entries (index, url)
    pending_entries = [(idx, u) for idx, u in video_entries if u not in all_completed]

    if len(all_completed) > 0:
        print(f"Progress: {len(completed_urls)} direct + {len(video2txt_urls)} video2txt = {len(all_completed)} completed, {len(pending_entries)} remaining")

    if not pending_entries:
        print("\nAll videos already processed!")
        print()  # Empty line suffix
        sys.exit(0)

    # 7. Process each video
    success_count = 0

    for i, (entry_idx, video_url) in enumerate(pending_entries, 1):
        print(f"\n[{i}/{len(pending_entries)}] #{entry_idx}: {video_url}")

        # Track start time for elapsed calculation
        start_time = time.time()
        retry_count = 0

        while True:
            # Add source (returns id and title)
            print("  Adding source...", end=" ", flush=True)
            ok, source_id, title = add_source(video_url)
            if not ok:
                print(f"FAILED: {source_id}")
                # Check and clean up any error sources in the cloud
                deleted = cleanup_error_sources(silent=True)
                if deleted > 0:
                    print(f"  Cleaned up {deleted} error source(s) from cloud")
                if retry_count < max_retries:
                    retry_count += 1
                    retry_delay = delay_seconds + (retry_count - 1)  # Incremental delay
                    print(f"  RETRY [#{entry_idx}]: #{retry_count}/{max_retries}, waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue  # Retry the same URL
                else:
                    # All retries exhausted
                    print(f"  All {max_retries} retries exhausted.")
                    if use_whisper:
                        # Try whisper fallback
                        print(f"  Trying whisper fallback...")
                        video_title = get_video_title(video_url)
                        traditional_title = convert_to_traditional(video_title)
                        whisper_ok, txt_file = whisper_fallback(video_url, traditional_title, transcripts_dir)
                        if whisper_ok:
                            print(f"  Adding transcript as text source...")
                            text_ok, text_source_id = add_text_source(txt_file, traditional_title)
                            if text_ok:
                                elapsed_seconds = int(time.time() - start_time)
                                record_video2txt_url(entry_idx, video_url, elapsed_seconds, video2txt_file)
                                success_count += 1
                                print(f"  SUCCESS (via whisper): Recorded to {video2txt_file}")
                            else:
                                print(f"\n  FATAL [#{entry_idx}]: Add text source failed: {text_source_id}")
                                print()
                                sys.exit(1)
                        else:
                            print(f"\n  FATAL [#{entry_idx}]: Whisper fallback failed!")
                            print()
                            sys.exit(1)
                    else:
                        # Whisper disabled - skip this video
                        print(f"  SKIP [#{entry_idx}]: Whisper disabled, skipping...")
                        record_skip_url(entry_idx, video_url, skip_file)
                    break  # Move to next URL
            print(f"OK (id: {source_id[:8]}...)")
            print(f"  Title: {title}")

            # Wait and verify source status
            print("  Waiting for processing...", end=" ", flush=True)
            status_ok, status = wait_for_source_with_status(source_id)
            if not status_ok or status == "error":
                print(f"ERROR (status: {status})")
                # Clean up all error sources (including this one)
                deleted = cleanup_error_sources(silent=True)
                if deleted > 0:
                    print(f"  Cleaned up {deleted} error source(s) from cloud")
                else:
                    # Fallback: try to delete the specific source
                    print(f"  Deleting source {source_id[:8]}...", end=" ", flush=True)
                    if delete_source(source_id):
                        print("OK")
                    else:
                        print("FAILED")

                if retry_count < max_retries:
                    retry_count += 1
                    retry_delay = delay_seconds + (retry_count - 1)  # Incremental delay
                    print(f"  RETRY [#{entry_idx}]: #{retry_count}/{max_retries}, waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue  # Retry the same URL
                else:
                    # All retries exhausted
                    print(f"  All {max_retries} retries exhausted.")
                    if use_whisper:
                        # Try whisper fallback
                        print(f"  Trying whisper fallback...")
                        traditional_title = convert_to_traditional(title)
                        whisper_ok, txt_file = whisper_fallback(video_url, traditional_title, transcripts_dir)
                        if whisper_ok:
                            print(f"  Adding transcript as text source...")
                            text_ok, text_source_id = add_text_source(txt_file, traditional_title)
                            if text_ok:
                                elapsed_seconds = int(time.time() - start_time)
                                record_video2txt_url(entry_idx, video_url, elapsed_seconds, video2txt_file)
                                success_count += 1
                                print(f"  SUCCESS (via whisper): Recorded to {video2txt_file}")
                            else:
                                print(f"\n  FATAL [#{entry_idx}]: Add text source failed: {text_source_id}")
                                print()
                                sys.exit(1)
                        else:
                            print(f"\n  FATAL [#{entry_idx}]: Whisper fallback failed!")
                            print()
                            sys.exit(1)
                    else:
                        # Whisper disabled - skip this video
                        print(f"  SKIP [#{entry_idx}]: Whisper disabled, skipping...")
                        record_skip_url(entry_idx, video_url, skip_file)
                    break  # Move to next URL
            print(f"OK (status: {status})")

            # Convert to Traditional Chinese
            traditional_title = convert_to_traditional(title)
            if traditional_title != title:
                print(f"  Converting: {title} → {traditional_title}")

                # Rename source
                print("  Renaming...", end=" ", flush=True)
                if rename_source(source_id, traditional_title):
                    print("OK")
                else:
                    print("FAILED (source still added)")
            else:
                print("  No conversion needed (already Traditional or no Chinese)")

            # Calculate elapsed time
            elapsed_seconds = int(time.time() - start_time)

            # Mark as completed - record to ok file with index and elapsed time
            record_success_url(entry_idx, video_url, elapsed_seconds, ok_file)
            success_count += 1
            print(f"  SUCCESS: Recorded to {ok_file} (elapsed: {elapsed_seconds}s)")

            # Success - exit retry loop
            break

        # Delay before next
        if i < len(pending_entries):
            print(f"  Waiting {delay_seconds}s before next...")
            time.sleep(delay_seconds)

    # 8. Summary
    # Reload counts (may have been updated during this run)
    final_video2txt_urls = load_video2txt_urls(video2txt_file)
    skip_count = 0
    if skip_file.exists():
        with open(skip_file, 'r') as f:
            skip_count = sum(1 for line in f if line.strip())

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total in playlist: {len(video_entries)}")
    print(f"Previously done:   {len(all_completed)}")
    print(f"Newly succeeded:   {success_count}")
    if skip_count > 0:
        print(f"Skipped:           {skip_count}")

    print(f"\nFiles:")
    print(f"  Playlist:   {index_file.absolute()}")
    print(f"  Direct OK:  {ok_file.absolute()}")
    if final_video2txt_urls:
        print(f"  Video2txt:  {video2txt_file.absolute()} ({len(final_video2txt_urls)} entries)")
    if skip_count > 0:
        print(f"  Skipped:    {skip_file.absolute()} ({skip_count} entries)")
    if transcripts_dir.exists():
        print(f"  Transcripts: {transcripts_dir.absolute()}/")

    print()  # Empty line suffix for readability


if __name__ == "__main__":
    main()
