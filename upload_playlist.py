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


def record_failed_url(index: int, url: str, failed_file: Path):
    """Record failed URL to file with index number."""
    with open(failed_file, 'a', encoding='utf-8') as f:
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


def load_failed_urls(failed_file: Path) -> list[str]:
    """Load failed URLs from failed file (for retry). Format: index url"""
    if not failed_file.exists():
        return []
    urls = []
    with open(failed_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                # Format: "index url" - extract url (2nd field)
                parts = line.split()
                if len(parts) >= 2:
                    urls.append(parts[1])
    return urls


def clear_failed_file(failed_file: Path):
    """Clear failed file (before retry)."""
    if failed_file.exists():
        failed_file.unlink()


def remove_from_failed_file(index: int, failed_file: Path):
    """Remove a specific entry (by index) from failed file."""
    if not failed_file.exists():
        return

    lines_to_keep = []
    with open(failed_file, 'r', encoding='utf-8') as f:
        for line in f:
            line_stripped = line.strip()
            if line_stripped:
                parts = line_stripped.split(maxsplit=1)
                if parts and parts[0] != str(index):
                    lines_to_keep.append(line)

    if lines_to_keep:
        with open(failed_file, 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
    else:
        # No lines left, remove the file
        failed_file.unlink()


def rename_source(source_id: str, new_title: str) -> bool:
    """Rename a source."""
    success, _ = run_command(["notebooklm", "source", "rename", source_id, new_title])
    return success


def convert_to_traditional(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese."""
    converter = opencc.OpenCC('s2t')
    return converter.convert(text)


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
  python3 upload_playlist.py -s "https://..."         # Stubborn: retry until success
  python3 upload_playlist.py -r -s                    # Resume + stubborn mode
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
        "-s", "--stubborn",
        action="store_true",
        help="Stubborn mode: retry failed URLs until success (頑固模式)"
    )
    return parser.parse_args()


def main():
    print()  # Empty line prefix for readability

    args = parse_args()
    url = args.url
    delay_seconds = args.interval
    resume_mode = args.resume
    stubborn_mode = args.stubborn

    # File paths (in current directory)
    index_file = Path("index.list")
    ok_file = Path("add_source_ok.txt")
    failed_file = Path("add_source_failed.txt")

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
    print(f"Stubborn mode: {'ON' if stubborn_mode else 'OFF'}")

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

    # 4. Load completed URLs from ok file
    completed_urls = load_ok_urls(ok_file)

    # 5. Determine pending entries (index, url)
    pending_entries = [(idx, u) for idx, u in video_entries if u not in completed_urls]

    # 6. In resume mode, also retry failed URLs
    if resume_mode:
        failed_urls = load_failed_urls(failed_file)
        # Only retry those not already completed
        retry_urls = [u for u in failed_urls if u not in completed_urls]
        if retry_urls:
            print(f"Will retry {len(retry_urls)} previously failed URLs")
            # Clear failed file since we're retrying
            clear_failed_file(failed_file)
            # Add retry URLs to pending (avoid duplicates)
            pending_urls_set = set(u for _, u in pending_entries)
            for u in retry_urls:
                if u not in pending_urls_set and u in url_to_index:
                    pending_entries.append((url_to_index[u], u))

    if len(completed_urls) > 0:
        print(f"Progress: {len(completed_urls)} completed, {len(pending_entries)} remaining")

    if not pending_entries:
        print("\nAll videos already processed!")
        print()  # Empty line suffix
        sys.exit(0)

    # 7. Process each video
    success_count = 0
    fail_count = 0

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
                if stubborn_mode:
                    retry_count += 1
                    retry_delay = delay_seconds + (retry_count - 1)  # Incremental delay
                    print(f"  STUBBORN: Retry #{retry_count}, waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue  # Retry the same URL
                else:
                    print(f"  WARNING: Failed to add source!")
                    record_failed_url(entry_idx, video_url, failed_file)
                    print(f"  WARNING: Recorded to {failed_file}")
                    fail_count += 1
                    time.sleep(delay_seconds)
                    break  # Move to next URL
            print(f"OK (id: {source_id[:8]}...)")
            print(f"  Title: {title}")

            # Wait and verify source status
            print("  Waiting for processing...", end=" ", flush=True)
            status_ok, status = wait_for_source_with_status(source_id)
            if not status_ok or status == "error":
                print(f"ERROR (status: {status})")
                print(f"  WARNING: Source failed processing! Removing...")
                if delete_source(source_id):
                    print(f"  WARNING: Source {source_id[:8]}... deleted")
                else:
                    print(f"  WARNING: Could not delete source {source_id[:8]}...")

                if stubborn_mode:
                    retry_count += 1
                    retry_delay = delay_seconds + (retry_count - 1)  # Incremental delay
                    print(f"  STUBBORN: Retry #{retry_count}, waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue  # Retry the same URL
                else:
                    record_failed_url(entry_idx, video_url, failed_file)
                    print(f"  WARNING: Recorded to {failed_file}")
                    fail_count += 1
                    time.sleep(delay_seconds)
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

            # Remove from failed file if it was there (from previous run)
            remove_from_failed_file(entry_idx, failed_file)

            # Success - exit retry loop
            break

        # Delay before next
        if i < len(pending_entries):
            print(f"  Waiting {delay_seconds}s before next...")
            time.sleep(delay_seconds)

    # 8. Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total in playlist: {len(video_entries)}")
    print(f"Previously done:   {len(completed_urls)}")
    print(f"Newly succeeded:   {success_count}")
    print(f"Newly failed:      {fail_count}")

    print(f"\nFiles:")
    print(f"  Playlist:  {index_file.absolute()}")
    print(f"  Succeeded: {ok_file.absolute()}")
    if fail_count > 0:
        print(f"  Failed:    {failed_file.absolute()}")
        print(f"\nTo retry failed URLs, run with --resume / -r")

    print()  # Empty line suffix for readability


if __name__ == "__main__":
    main()
