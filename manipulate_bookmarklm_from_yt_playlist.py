#!/usr/bin/env python3
"""
Upload YouTube playlist to NotebookLM with Simplified → Traditional Chinese conversion.

Prerequisites:
    pip install notebooklm-py opencc-python-reimplemented yt-dlp openai-whisper gradio_client

Setup (first time):
    notebooklm auth                   # Authenticate with Google (opens browser)
    notebooklm list                   # List available notebooks
    notebooklm use <notebook_id>      # Select target notebook
    notebooklm status                 # Verify notebook is selected

Usage:
    python3 manipulate_bookmarklm_from_yt_playlist.py "https://www.youtube.com/playlist?list=PLxxx"
    python3 manipulate_bookmarklm_from_yt_playlist.py "https://www.youtube.com/watch?v=xxx&list=PLyyy&index=1"
    python3 manipulate_bookmarklm_from_yt_playlist.py -i 25 "https://..."   # Custom interval (25 seconds)
    python3 manipulate_bookmarklm_from_yt_playlist.py -r                    # Resume from index.list
    python3 manipulate_bookmarklm_from_yt_playlist.py --remote-sshfs user@host "https://..."  # Use remote GPU
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
DEBUG = False  # Set via --debug flag


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


def get_playlist_videos(playlist_url: str) -> list[tuple[str, str]]:
    """Extract all video URLs and titles from a playlist using yt-dlp.
    Returns list of (url, title) tuples."""
    success, output = run_command([
        "yt-dlp",
        "--flat-playlist",
        "--print", "%(url)s\t%(title)s",
        playlist_url
    ])

    if not success:
        print(f"Error extracting playlist: {output}", file=sys.stderr)
        return []

    results = []
    for line in output.split('\n'):
        line = line.strip()
        if line:
            parts = line.split('\t', 1)
            if len(parts) == 2:
                url, title = parts
                # Convert title to Traditional Chinese
                traditional_title = convert_to_traditional(title)
                results.append((url, traditional_title))
            elif len(parts) == 1:
                results.append((parts[0], ""))
    return results


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


def load_working_indices(lock_file: Path) -> set[int]:
    """Load indices currently being processed by other sessions."""
    if not lock_file.exists():
        return set()
    indices = set()
    with open(lock_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                parts = line.split()
                if len(parts) >= 1:
                    indices.add(int(parts[0]))
    return indices


def claim_index(idx: int, lock_file: Path) -> bool:
    """Atomically claim an index for processing. Returns True if claimed."""
    import fcntl
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.touch(exist_ok=True)

    with open(lock_file, 'r+', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            lines = f.readlines()
            # Check if already claimed
            for line in lines:
                parts = line.strip().split()
                if parts and int(parts[0]) == idx:
                    return False  # Already claimed by another session
            # Claim it
            f.write(f"{idx} {int(time.time())}\n")
            f.flush()
            return True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def release_index(idx: int, lock_file: Path):
    """Release a claimed index after processing (success or failure)."""
    import fcntl
    if not lock_file.exists():
        return

    with open(lock_file, 'r+', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            lines = f.readlines()
            f.seek(0)
            f.truncate()
            for line in lines:
                parts = line.strip().split()
                if parts and int(parts[0]) != idx:
                    f.write(line)
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def cleanup_stale_locks(lock_file: Path, max_age_hours: int = 4):
    """Remove lock entries older than max_age_hours (crashed sessions)."""
    import fcntl
    if not lock_file.exists():
        return 0

    now = int(time.time())
    max_age_seconds = max_age_hours * 3600
    removed = 0

    with open(lock_file, 'r+', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            lines = f.readlines()
            f.seek(0)
            f.truncate()
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    timestamp = int(parts[1])
                    if now - timestamp < max_age_seconds:
                        f.write(line)
                    else:
                        removed += 1
                elif parts:
                    # No timestamp, remove as stale
                    removed += 1
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    return removed


def write_index_list(video_entries: list[tuple[str, str]], playlist_url: str, index_file: Path):
    """Write playlist URLs and titles to index.list file.
    video_entries: list of (url, title) tuples."""
    with open(index_file, 'w', encoding='utf-8') as f:
        # First line: playlist URL marker
        f.write(f"# playlist: {playlist_url}\n")
        for i, (url, title) in enumerate(video_entries, 1):
            f.write(f'{i}\t{url}\t"{title}"\n')


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


def format_title_with_index(index: int, title: str) -> str:
    """Format title with zero-padded index prefix like [001] 標題."""
    return f"[{index:03d}] {title}"


def whisper_fallback(video_url: str, video_title: str, transcripts_dir: Path) -> tuple[bool, str]:
    """
    Download audio from YouTube, transcribe with whisper, save both mp3 and txt.
    Shows real-time progress during transcription.

    Resume support:
    - If txt file exists: reuse it directly (skip download & whisper)
    - If mp3 exists but no txt: run whisper on existing mp3 (skip download)
    - If neither exists: download then whisper

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

    # Check if transcript already exists - reuse it
    if txt_file.exists():
        print(f"  WHISPER: Found existing transcript: {txt_file.name}")
        print(f"  WHISPER: Reusing existing txt file (skipping download & transcription)")
        return True, str(txt_file)

    # Check if mp3 already exists - skip download, just run whisper
    actual_mp3 = None
    if mp3_file.exists():
        actual_mp3 = mp3_file
        print(f"  WHISPER: Found existing audio: {mp3_file.name}")
        print(f"  WHISPER: Reusing existing mp3 (skipping download)")
    else:
        # Also check for other audio formats that might exist
        audio_files = list(transcripts_dir.glob(f"{safe_title}.*"))
        audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
        if audio_files:
            actual_mp3 = audio_files[0]
            print(f"  WHISPER: Found existing audio: {actual_mp3.name}")
            print(f"  WHISPER: Reusing existing audio (skipping download)")

    # Download if no audio file found (with retry)
    if actual_mp3 is None:
        max_download_retries = 2
        for dl_attempt in range(1, max_download_retries + 1):
            print(f"  WHISPER: Downloading audio to {mp3_file.name}..." + (f" (attempt {dl_attempt})" if dl_attempt > 1 else ""))

            # Download audio directly to transcripts folder
            result = sp.run([
                "yt-dlp",
                "--cookies-from-browser", "chrome",
                "-x",  # Extract audio
                "--audio-format", "mp3",
                "-o", str(mp3_file),
                video_url
            ], capture_output=True, text=True)

            if result.returncode == 0:
                break  # Download succeeded
            elif dl_attempt < max_download_retries:
                print(f"  WHISPER: Download failed, retrying in 3s...")
                if result.stderr:
                    # Show last line of error for debugging
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  WHISPER: {err_lines[-1]}")
                time.sleep(3)
            else:
                print(f"  WHISPER: Failed to download audio after {max_download_retries} attempts")
                if result.stderr:
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  WHISPER: {err_lines[-1]}")
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
    whisper_start = time.time()

    # Transcribe with whisper - let output flow directly to terminal
    result = sp.run(
        [
            "whisper",
            str(actual_mp3),
            "--language", "Chinese",
            "--output_format", "txt",
            "--output_dir", str(transcripts_dir),
            "--verbose", "True",
            "--initial_prompt", "繁體中文",
            "--condition_on_previous_text", "False"
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

    whisper_elapsed = int(time.time() - whisper_start)
    whisper_mins, whisper_secs = divmod(whisper_elapsed, 60)
    print(f"  WHISPER: Done in {whisper_mins}m{whisper_secs:02d}s (local)")
    print(f"  WHISPER: Saved mp3: {actual_mp3}")
    print(f"  WHISPER: Saved txt: {whisper_txt}")

    return True, str(whisper_txt)


def whisper_via_colab(
    video_url: str,
    video_title: str,
    transcripts_dir: Path,
    colab_url: str,
    timeout_seconds: int = 600
) -> tuple[bool, str]:
    """
    Download audio from YouTube, send to Colab Gradio API for transcription.

    Resume support:
    - If txt file exists: reuse it directly (skip download & Colab)
    - If mp3 exists but no txt: send existing mp3 to Colab (skip download)
    - If neither exists: download then send to Colab

    Args:
        video_url: YouTube video URL
        video_title: Video title for filename
        transcripts_dir: Directory for transcripts
        colab_url: Gradio API URL (e.g., https://xxxxx.gradio.live)
        timeout_seconds: API timeout (default 600s for long videos)

    Returns:
        (success, txt_file_path or error_message)
    """
    import subprocess as sp
    import shutil

    try:
        from gradio_client import Client, handle_file
        import httpx
    except ImportError:
        return False, "gradio_client not installed. Run: pip install gradio_client"

    # Create transcripts directory if needed
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # Convert title to Traditional Chinese and clean for filename
    traditional_title = convert_to_traditional(video_title)
    safe_title = "".join(c if c.isalnum() or c in ' -_' else '_' for c in traditional_title)[:100]
    mp3_file = transcripts_dir / f"{safe_title}.mp3"
    txt_file = transcripts_dir / f"{safe_title}.txt"

    # Check if transcript already exists - reuse it
    if txt_file.exists():
        print(f"  COLAB: Found existing transcript: {txt_file.name}")
        print(f"  COLAB: Reusing existing txt file (skipping download & transcription)")
        return True, str(txt_file)

    # Check if mp3 already exists - skip download, just send to Colab
    actual_mp3 = None
    if mp3_file.exists():
        actual_mp3 = mp3_file
        print(f"  COLAB: Found existing audio: {mp3_file.name}")
        print(f"  COLAB: Reusing existing mp3 (skipping download)")
    else:
        # Also check for other audio formats that might exist
        audio_files = list(transcripts_dir.glob(f"{safe_title}.*"))
        audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
        if audio_files:
            actual_mp3 = audio_files[0]
            print(f"  COLAB: Found existing audio: {actual_mp3.name}")
            print(f"  COLAB: Reusing existing audio (skipping download)")

    # Download if no audio file found (with retry)
    if actual_mp3 is None:
        max_download_retries = 2
        for dl_attempt in range(1, max_download_retries + 1):
            print(f"  COLAB: Downloading audio to {mp3_file.name}..." + (f" (attempt {dl_attempt})" if dl_attempt > 1 else ""))

            # Download audio directly to transcripts folder
            result = sp.run([
                "yt-dlp",
                "--cookies-from-browser", "chrome",
                "-x",  # Extract audio
                "--audio-format", "mp3",
                "-o", str(mp3_file),
                video_url
            ], capture_output=True, text=True)

            if result.returncode == 0:
                break  # Download succeeded
            elif dl_attempt < max_download_retries:
                print(f"  COLAB: Download failed, retrying in 3s...")
                if result.stderr:
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  COLAB: {err_lines[-1]}")
                time.sleep(3)
            else:
                print(f"  COLAB: Failed to download audio after {max_download_retries} attempts")
                if result.stderr:
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  COLAB: {err_lines[-1]}")
                return False, "Failed to download audio"

        # Find the actual audio file (yt-dlp may add extension)
        audio_files = list(transcripts_dir.glob(f"{safe_title}.*"))
        audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
        if not audio_files:
            print(f"  COLAB: No audio file found")
            return False, "No audio file found after download"
        actual_mp3 = audio_files[0]

        # Rename to .mp3 if different extension
        if actual_mp3.suffix != '.mp3':
            new_mp3 = actual_mp3.with_suffix('.mp3')
            shutil.move(str(actual_mp3), str(new_mp3))
            actual_mp3 = new_mp3

    # Send to Colab Gradio API
    colab_start = time.time()
    file_size_mb = actual_mp3.stat().st_size / 1024 / 1024

    # Retry connection up to 3 times (handles transient SSL errors)
    client = None
    max_connect_retries = 3

    # Debug: test basic connectivity before gradio_client
    if DEBUG:
        print(f"  COLAB: DEBUG - Testing basic httpx connection...")
        try:
            import httpx as httpx_debug
            with httpx_debug.Client(timeout=10.0) as debug_client:
                resp = debug_client.get(f"{colab_url}/config")
                print(f"  COLAB: DEBUG - Basic test OK (status {resp.status_code})")
        except Exception as debug_e:
            print(f"  COLAB: DEBUG - Basic test FAILED: {debug_e}")

    for attempt in range(1, max_connect_retries + 1):
        print(f"  COLAB: Connecting to {colab_url}..." + (f" (attempt {attempt})" if attempt > 1 else ""))
        try:
            # timeout_seconds=0 means "no timeout" → use None for httpx
            # timeout_seconds>0 means custom timeout in seconds
            effective_timeout = None if timeout_seconds == 0 else timeout_seconds
            client = Client(
                colab_url,
                verbose=False,
                httpx_kwargs={
                    "timeout": httpx.Timeout(effective_timeout, connect=30.0)
                }
            )
            break  # Connection successful
        except Exception as e:
            if attempt < max_connect_retries:
                print(f"  COLAB: Connection failed: {e}")
                print(f"  COLAB: Retrying in 3s...")
                time.sleep(3)
            else:
                print(f"  COLAB: API error: {e}")
                return False, f"API error: {e}"

    try:

        print(f"  COLAB: Uploading {actual_mp3.name} ({file_size_mb:.1f} MB)...")
        print(f"  COLAB: Transcribing (timeout: {timeout_seconds}s)...", end="", flush=True)

        # Use submit() for async job with progress indicator
        job = client.submit(
            handle_file(str(actual_mp3)),
            fn_index=0
        )

        # Show progress while waiting (with health checks)
        elapsed = 0
        pending_time = 0
        max_pending_time = 60  # Max time to stay in PENDING before assuming Colab is dead
        last_status = None

        while not job.done():
            time.sleep(5)
            elapsed += 5
            mins, secs = divmod(elapsed, 60)

            # Check job status
            try:
                status = job.status()
                status_code = status.code.name if hasattr(status, 'code') else str(status)

                # Track status changes
                if status_code != last_status:
                    if last_status is not None:
                        print()  # Newline before status change
                    print(f"  COLAB: Status: {status_code}")
                    last_status = status_code
                    pending_time = 0  # Reset pending timer on status change

                # Check for stuck in PENDING (Colab may have died)
                if status_code == "PENDING":
                    pending_time += 5
                    if pending_time >= max_pending_time:
                        print()
                        job.cancel()
                        raise RuntimeError(f"Stuck in PENDING for {pending_time}s - Colab may have disconnected")

                print(f"\r  COLAB: Transcribing... {mins}m{secs:02d}s elapsed", end="", flush=True)

            except Exception as e:
                # If we can't get status, just show elapsed time
                print(f"\r  COLAB: Transcribing... {mins}m{secs:02d}s elapsed", end="", flush=True)

            # Check timeout (0 = no timeout)
            if timeout_seconds > 0 and elapsed >= timeout_seconds:
                print()
                job.cancel()
                raise TimeoutError(f"Timeout after {mins}m{secs:02d}s")

        print()  # Newline after progress

        transcript = job.result()
        client.close()

    except httpx.ReadTimeout:
        print(f"  COLAB: Timeout - Colab may have disconnected")
        return False, "Timeout - check if Colab is still running"
    except TimeoutError as e:
        print(f"  COLAB: {e}")
        return False, str(e)
    except Exception as e:
        print(f"  COLAB: API error: {e}")
        return False, f"API error: {e}"

    # Check for empty transcript
    if not transcript or not transcript.strip():
        print(f"  COLAB: Empty transcript returned")
        return False, "Empty transcript"

    # Convert to Traditional Chinese (Colab may return Simplified)
    traditional_transcript = convert_to_traditional(transcript)

    # Save to txt file
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(traditional_transcript)

    colab_elapsed = int(time.time() - colab_start)
    colab_mins, colab_secs = divmod(colab_elapsed, 60)
    print(f"  COLAB: Done in {colab_mins}m{colab_secs:02d}s (Colab)")
    print(f"  COLAB: Saved mp3: {actual_mp3}")
    print(f"  COLAB: Saved txt: {txt_file}")

    return True, str(txt_file)


def whisper_via_sshfs(
    video_url: str,
    video_title: str,
    transcripts_dir: Path,
    sshfs_mount: Path,
    ssh_user: str,
    ssh_host: str,
    remote_path: str
) -> tuple[bool, str]:
    """
    Download audio locally, transcribe via SSH on remote GPU.

    Resume support:
    - If txt file exists in transcripts_dir: reuse it directly
    - If mp3 exists but no txt: run remote whisper on existing mp3
    - If neither exists: download then run remote whisper

    Args:
        video_url: YouTube video URL
        video_title: Video title for filename
        transcripts_dir: Local directory for final transcripts
        sshfs_mount: Local mount point for remote filesystem
        ssh_user: SSH username
        ssh_host: SSH hostname
        remote_path: Remote path (mounted via sshfs)

    Returns:
        (success, txt_file_path or error_message)
    """
    import subprocess as sp
    import shutil

    # Convert title to Traditional Chinese and clean for filename
    traditional_title = convert_to_traditional(video_title)
    safe_title = "".join(c if c.isalnum() or c in ' -_' else '_' for c in traditional_title)[:100]

    # Local paths (final destination)
    local_txt = transcripts_dir / f"{safe_title}.txt"

    # Remote paths (via sshfs mount)
    remote_mp3 = sshfs_mount / f"{safe_title}.mp3"
    remote_txt = sshfs_mount / f"{safe_title}.txt"

    # Check if transcript already exists locally - reuse it
    if local_txt.exists():
        print(f"  SSHFS: Found existing transcript: {local_txt.name}")
        print(f"  SSHFS: Reusing existing txt file (skipping download & transcription)")
        return True, str(local_txt)

    # Check if transcript exists on remote mount
    if remote_txt.exists():
        print(f"  SSHFS: Found existing transcript on remote: {remote_txt.name}")
        print(f"  SSHFS: Copying to local transcripts...")
        # Convert to Traditional Chinese and save locally
        with open(remote_txt, 'r', encoding='utf-8') as f:
            transcript = f.read()
        traditional_transcript = convert_to_traditional(transcript)
        with open(local_txt, 'w', encoding='utf-8') as f:
            f.write(traditional_transcript)
        return True, str(local_txt)

    # Check if mp3 already exists on remote - skip download
    actual_mp3 = None
    if remote_mp3.exists():
        actual_mp3 = remote_mp3
        print(f"  SSHFS: Found existing audio on remote: {remote_mp3.name}")
        print(f"  SSHFS: Reusing existing mp3 (skipping download)")
    else:
        # Also check for other audio formats on remote
        audio_files = list(sshfs_mount.glob(f"{safe_title}.*"))
        audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
        if audio_files:
            actual_mp3 = audio_files[0]
            print(f"  SSHFS: Found existing audio on remote: {actual_mp3.name}")
            print(f"  SSHFS: Reusing existing audio (skipping download)")

    # Download if no audio file found (with retry)
    if actual_mp3 is None:
        max_download_retries = 2
        for dl_attempt in range(1, max_download_retries + 1):
            print(f"  SSHFS: Downloading audio to remote {remote_mp3.name}..." + (f" (attempt {dl_attempt})" if dl_attempt > 1 else ""))

            # Download audio directly to remote mount
            result = sp.run([
                "yt-dlp",
                "--cookies-from-browser", "chrome",
                "-x",  # Extract audio
                "--audio-format", "mp3",
                "-o", str(remote_mp3),
                video_url
            ], capture_output=True, text=True)

            if result.returncode == 0:
                break  # Download succeeded
            elif dl_attempt < max_download_retries:
                print(f"  SSHFS: Download failed, retrying in 3s...")
                if result.stderr:
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  SSHFS: {err_lines[-1]}")
                time.sleep(3)
            else:
                print(f"  SSHFS: Failed to download audio after {max_download_retries} attempts")
                if result.stderr:
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  SSHFS: {err_lines[-1]}")
                return False, "Failed to download audio"

        # Find the actual audio file (yt-dlp may add extension)
        audio_files = list(sshfs_mount.glob(f"{safe_title}.*"))
        audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
        if not audio_files:
            print(f"  SSHFS: No audio file found on remote")
            return False, "No audio file found after download"
        actual_mp3 = audio_files[0]

        # Rename to .mp3 if different extension
        if actual_mp3.suffix != '.mp3':
            new_mp3 = actual_mp3.with_suffix('.mp3')
            shutil.move(str(actual_mp3), str(new_mp3))
            actual_mp3 = new_mp3

    # Run whisper on remote via SSH
    sshfs_start = time.time()
    remote_mp3_path = f"{remote_path}/{actual_mp3.name}"
    remote_output_dir = remote_path

    print(f"  SSHFS: Transcribing on {ssh_host} via SSH...")
    print(f"  SSHFS: Remote file: {remote_mp3_path}")

    # Run whisper via SSH - output streams directly to terminal
    ssh_cmd = [
        "ssh", f"{ssh_user}@{ssh_host}",
        "whisper",
        remote_mp3_path,
        "--language", "Chinese",
        "--output_format", "txt",
        "--output_dir", remote_output_dir,
        "--verbose", "True",
        "--initial_prompt", "繁體中文",
        "--condition_on_previous_text", "False"
    ]

    result = sp.run(ssh_cmd)  # No capture - output goes directly to terminal

    if result.returncode != 0:
        print(f"  SSHFS: Transcription failed (exit code {result.returncode})")
        return False, f"SSH whisper failed with exit code {result.returncode}"

    # Check for output file on remote mount
    expected_txt = actual_mp3.with_suffix('.txt')
    if not expected_txt.exists():
        print(f"  SSHFS: No transcript file found on remote")
        return False, "No transcript file found after whisper"

    # Read, convert to Traditional Chinese, and save locally
    with open(expected_txt, 'r', encoding='utf-8') as f:
        transcript = f.read()

    traditional_transcript = convert_to_traditional(transcript)

    # Save to local transcripts directory
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    with open(local_txt, 'w', encoding='utf-8') as f:
        f.write(traditional_transcript)

    # Also update remote txt with Traditional Chinese
    with open(expected_txt, 'w', encoding='utf-8') as f:
        f.write(traditional_transcript)

    sshfs_elapsed = int(time.time() - sshfs_start)
    sshfs_mins, sshfs_secs = divmod(sshfs_elapsed, 60)
    print(f"  SSHFS: Done in {sshfs_mins}m{sshfs_secs:02d}s ({ssh_host})")
    print(f"  SSHFS: Remote mp3: {actual_mp3}")
    print(f"  SSHFS: Local txt: {local_txt}")

    return True, str(local_txt)


def whisper_via_ssh(
    video_url: str,
    video_title: str,
    transcripts_dir: Path,
    ssh_user: str,
    ssh_host: str,
    remote_path: str
) -> tuple[bool, str]:
    """
    Download audio locally, upload to remote, transcribe via SSH on remote GPU.

    Flow:
    1. Check if local txt exists → reuse it
    2. Check if local mp3 exists → reuse it, else download with yt-dlp locally
    3. scp mp3 to remote
    4. Run whisper on remote via SSH (streams progress to terminal)
    5. scp txt back to local transcripts_dir
    6. Delete remote mp3 and txt

    Args:
        video_url: YouTube video URL
        video_title: Video title for filename
        transcripts_dir: Local directory for final transcripts
        ssh_user: SSH username
        ssh_host: SSH hostname
        remote_path: Remote working directory

    Returns:
        (success, local_txt_path or error_message)
    """
    import subprocess as sp
    import shutil

    # Convert title to Traditional Chinese and clean for filename
    traditional_title = convert_to_traditional(video_title)
    safe_title = "".join(c if c.isalnum() or c in ' -_' else '_' for c in traditional_title)[:100]

    # Local paths
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    local_mp3 = transcripts_dir / f"{safe_title}.mp3"
    local_txt = transcripts_dir / f"{safe_title}.txt"

    # Remote paths
    remote_mp3 = f"{remote_path}/{safe_title}.mp3"
    remote_txt = f"{remote_path}/{safe_title}.txt"

    # Check if transcript already exists locally - reuse it
    if local_txt.exists():
        print(f"  SSH: Found existing transcript: {local_txt.name}")
        print(f"  SSH: Reusing existing txt file (skipping download & transcription)")
        return True, str(local_txt)

    # Step 1: Check if txt already exists on remote
    print(f"  SSH: Checking for existing files on {ssh_host}...")
    check_result = sp.run(
        ["ssh", f"{ssh_user}@{ssh_host}", f"test -f '{remote_txt}' && echo EXISTS"],
        capture_output=True, text=True
    )
    if "EXISTS" in check_result.stdout:
        print(f"  SSH: Found existing transcript on remote, copying...")
        # scp txt back to local
        scp_result = sp.run(
            ["scp", f"{ssh_user}@{ssh_host}:{remote_txt}", str(local_txt)],
            capture_output=True, text=True
        )
        if scp_result.returncode == 0:
            # Convert to Traditional Chinese
            with open(local_txt, 'r', encoding='utf-8') as f:
                transcript = f.read()
            traditional_transcript = convert_to_traditional(transcript)
            with open(local_txt, 'w', encoding='utf-8') as f:
                f.write(traditional_transcript)
            print(f"  SSH: Copied and converted: {local_txt.name}")
            return True, str(local_txt)

    # Step 2: Check if mp3 already exists locally or on remote
    actual_mp3 = None
    mp3_on_remote = False

    # Check local first
    if local_mp3.exists():
        actual_mp3 = local_mp3
        print(f"  SSH: Found existing audio locally: {local_mp3.name}")
    else:
        # Check for other audio formats locally
        audio_files = list(transcripts_dir.glob(f"{safe_title}.*"))
        audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
        if audio_files:
            actual_mp3 = audio_files[0]
            print(f"  SSH: Found existing audio locally: {actual_mp3.name}")

    # Check remote if not found locally
    if actual_mp3 is None:
        check_mp3 = sp.run(
            ["ssh", f"{ssh_user}@{ssh_host}", f"test -f '{remote_mp3}' && echo EXISTS"],
            capture_output=True, text=True
        )
        if "EXISTS" in check_mp3.stdout:
            print(f"  SSH: Found existing audio on remote: {safe_title}.mp3")
            mp3_on_remote = True

    # Step 3: Download locally if no mp3 found
    if actual_mp3 is None and not mp3_on_remote:
        max_download_retries = 2
        for dl_attempt in range(1, max_download_retries + 1):
            print(f"  SSH: Downloading audio locally..." + (f" (attempt {dl_attempt})" if dl_attempt > 1 else ""))

            # Download with cookies from Chrome (works for age-restricted videos)
            result = sp.run([
                "yt-dlp",
                "--cookies-from-browser", "chrome",
                "-x",
                "--audio-format", "mp3",
                "-o", str(local_mp3),
                video_url
            ], capture_output=True, text=True)

            if result.returncode == 0:
                break
            elif dl_attempt < max_download_retries:
                print(f"  SSH: Download failed, retrying in 3s...")
                if result.stderr:
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  SSH: {err_lines[-1]}")
                time.sleep(3)
            else:
                print(f"  SSH: Failed to download audio after {max_download_retries} attempts")
                if result.stderr:
                    err_lines = [l for l in result.stderr.strip().split('\n') if l.startswith('ERROR')]
                    if err_lines:
                        print(f"  SSH: {err_lines[-1]}")
                return False, "Failed to download audio locally"

        # Find the actual audio file
        audio_files = list(transcripts_dir.glob(f"{safe_title}.*"))
        audio_files = [f for f in audio_files if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']]
        if not audio_files:
            print(f"  SSH: No audio file found after download")
            return False, "No audio file found"
        actual_mp3 = audio_files[0]

        # Rename to .mp3 if different extension
        if actual_mp3.suffix != '.mp3':
            new_mp3 = actual_mp3.with_suffix('.mp3')
            shutil.move(str(actual_mp3), str(new_mp3))
            actual_mp3 = new_mp3

    # Step 4: Upload mp3 to remote (if we have it locally) - with retry for VPN flakiness
    if actual_mp3 is not None and not mp3_on_remote:
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            print(f"  SSH: Uploading {actual_mp3.name} to {ssh_host}..." + (f" (attempt {attempt})" if attempt > 1 else ""))
            scp_up = sp.run(
                ["scp", str(actual_mp3), f"{ssh_user}@{ssh_host}:{remote_mp3}"],
                capture_output=True, text=True
            )
            if scp_up.returncode == 0:
                break
            if attempt < max_retries:
                print(f"  SSH: Upload failed: {scp_up.stderr.strip()}")
                print(f"  SSH: Retrying in 5s...")
                time.sleep(5)
            else:
                print(f"  SSH: Upload failed after {max_retries} attempts: {scp_up.stderr.strip()}")
                return False, "Failed to upload mp3 to remote"

    # Step 5: Run whisper on remote via SSH
    ssh_start = time.time()

    # Kill any existing whisper processes to free GPU memory (with retry)
    for attempt in range(1, 4):
        kill_result = sp.run(
            ["ssh", f"{ssh_user}@{ssh_host}", "pkill -f '/usr/local/bin/whisper' 2>/dev/null; sleep 1"],
            capture_output=True
        )
        if kill_result.returncode == 0 or kill_result.returncode == 1:  # 1 = no process found (ok)
            break
        if attempt < 3:
            time.sleep(5)

    # Use bash -l to load user's PATH (whisper may be in ~/.local/bin or /usr/local/bin)
    whisper_cmd = (
        f"bash -l -c \"whisper '{remote_mp3}' "
        f"--language Chinese "
        f"--output_format txt "
        f"--output_dir '{remote_path}' "
        f"--verbose True "
        f"--initial_prompt 繁體中文 "
        f"--condition_on_previous_text False\""
    )

    # Run whisper via SSH with retry for connection issues
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        print(f"  SSH: Transcribing on {ssh_host}..." + (f" (attempt {attempt})" if attempt > 1 else ""))
        whisper_result = sp.run(
            ["ssh", "-t", f"{ssh_user}@{ssh_host}", whisper_cmd]
        )  # No capture - streams to terminal

        if whisper_result.returncode == 0:
            break
        # Check if it's a connection error (255) vs whisper error (1)
        if whisper_result.returncode == 255 and attempt < max_retries:
            print(f"  SSH: Connection failed, retrying in 5s...")
            time.sleep(5)
        elif whisper_result.returncode != 0:
            print(f"  SSH: whisper failed (exit code {whisper_result.returncode})")
            return False, "whisper failed on remote"

    # Step 6: scp txt back to local with retry
    for attempt in range(1, max_retries + 1):
        print(f"  SSH: Copying transcript to local..." + (f" (attempt {attempt})" if attempt > 1 else ""))
        scp_result = sp.run(
            ["scp", f"{ssh_user}@{ssh_host}:{remote_txt}", str(local_txt)],
            capture_output=True, text=True
        )
        if scp_result.returncode == 0:
            break
        if attempt < max_retries:
            print(f"  SSH: scp failed: {scp_result.stderr.strip()}")
            print(f"  SSH: Retrying in 5s...")
            time.sleep(5)
        else:
            print(f"  SSH: scp failed after {max_retries} attempts: {scp_result.stderr.strip()}")
            return False, "scp failed"

    # Convert to Traditional Chinese
    with open(local_txt, 'r', encoding='utf-8') as f:
        transcript = f.read()
    traditional_transcript = convert_to_traditional(transcript)
    with open(local_txt, 'w', encoding='utf-8') as f:
        f.write(traditional_transcript)

    # Step 6: Delete remote mp3 and txt
    print(f"  SSH: Cleaning up remote files...")
    sp.run(
        ["ssh", f"{ssh_user}@{ssh_host}", f"rm -f '{remote_mp3}' '{remote_txt}'"],
        capture_output=True
    )

    ssh_elapsed = int(time.time() - ssh_start)
    ssh_mins, ssh_secs = divmod(ssh_elapsed, 60)
    print(f"  SSH: Done in {ssh_mins}m{ssh_secs:02d}s ({ssh_host})")
    print(f"  SSH: Local txt: {local_txt}")

    return True, str(local_txt)


def do_whisper_transcription(
    video_url: str,
    video_title: str,
    transcripts_dir: Path,
    colab_url: str | None = None,
    sshfs_config: tuple[Path, str, str, str] | None = None,
    ssh_config: tuple[str, str, str] | None = None,
    local_fallback: bool = True,
    colab_timeout: int = 600
) -> tuple[bool, str]:
    """
    Transcribe video using fallback chain: Colab → SSHFS/SSH → Local.

    Args:
        video_url: YouTube video URL
        video_title: Video title
        transcripts_dir: Output directory
        colab_url: Gradio API URL (None = skip Colab)
        sshfs_config: Tuple of (mount_point, user, host, remote_path) for SSHFS method
        ssh_config: Tuple of (user, host, remote_path) for direct SSH method (no mount)
        local_fallback: If True and remote options fail, try local whisper
        colab_timeout: Colab API timeout in seconds

    Returns:
        (success, txt_file_path or error_message)
    """
    last_error = "No whisper method available"

    # 1. Try Colab first (if configured)
    if colab_url:
        success, result = whisper_via_colab(
            video_url, video_title, transcripts_dir,
            colab_url, colab_timeout
        )
        if success:
            return True, result
        last_error = result
        print(f"  COLAB failed: {result}")

    # 2. Try SSHFS remote (if configured and mounted)
    if sshfs_config:
        mount_point, ssh_user, ssh_host, remote_path = sshfs_config
        if colab_url:
            print(f"  Falling back to SSHFS remote ({ssh_host})...")
        success, result = whisper_via_sshfs(
            video_url, video_title, transcripts_dir,
            mount_point, ssh_user, ssh_host, remote_path
        )
        if success:
            return True, result
        last_error = result
        print(f"  SSHFS failed: {result}")

    # 3. Try SSH remote (if configured - no mount needed)
    if ssh_config:
        ssh_user, ssh_host, remote_path = ssh_config
        if colab_url or sshfs_config:
            print(f"  Falling back to SSH remote ({ssh_host})...")
        success, result = whisper_via_ssh(
            video_url, video_title, transcripts_dir,
            ssh_user, ssh_host, remote_path
        )
        if success:
            return True, result
        last_error = result
        print(f"  SSH failed: {result}")

    # 4. Try local whisper (if allowed)
    if local_fallback:
        if colab_url or sshfs_config or ssh_config:
            print(f"  Falling back to local whisper...")
        return whisper_fallback(video_url, video_title, transcripts_dir)

    return False, last_error


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


def parse_remote_sshfs(value: str | None) -> tuple[str, str, str] | None:
    """Parse --remote-sshfs argument.

    Format: user@host[:path]
    Default path: /genesis/tmp

    Returns (user, host, path) or None if not provided.
    """
    if not value:
        return None

    DEFAULT_PATH = "/genesis/tmp"

    # Must contain @ for user
    if '@' not in value:
        print(f"Error: --remote-sshfs must include user@ (e.g., cschen@genesis)", file=sys.stderr)
        sys.exit(1)

    user_part, rest = value.split('@', 1)

    # Check if path is specified (host:path)
    if ':' in rest:
        host, path = rest.split(':', 1)
    else:
        host = rest
        path = DEFAULT_PATH

    return user_part, host, path


def is_sshfs_mounted(mount_point: Path) -> bool:
    """Check if a path is an sshfs mount."""
    import subprocess as sp
    result = sp.run(["mount"], capture_output=True, text=True)
    # Look for the mount point in output (macOS format)
    return str(mount_point.absolute()) in result.stdout


def mount_sshfs(user: str, host: str, remote_path: str, mount_point: Path, max_retries: int = 2) -> bool:
    """Mount remote path via sshfs. Returns True on success.

    Retries up to max_retries times before giving up.
    Returns False if sshfs is not installed or mount fails.
    """
    import subprocess as sp
    import shutil

    # Check if sshfs is installed
    if not shutil.which("sshfs"):
        print(f"  SSHFS: 'sshfs' command not found (not installed)")
        return False

    # Create mount point if needed
    mount_point.mkdir(parents=True, exist_ok=True)

    # Check if already mounted
    if is_sshfs_mounted(mount_point):
        print(f"  SSHFS: Already mounted at {mount_point}")
        return True

    # Mount via sshfs with retry
    sshfs_target = f"{user}@{host}:{remote_path}"

    for attempt in range(1, max_retries + 1):
        print(f"  SSHFS: Mounting {sshfs_target} → {mount_point}" + (f" (attempt {attempt})" if attempt > 1 else ""))

        try:
            result = sp.run(
                ["sshfs", sshfs_target, str(mount_point), "-o", "reconnect,ServerAliveInterval=15"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"  SSHFS: Mounted successfully")
                return True

            error_msg = result.stderr.strip()
            print(f"  SSHFS: Mount failed: {error_msg}")

        except FileNotFoundError:
            print(f"  SSHFS: 'sshfs' command not found")
            return False
        except Exception as e:
            print(f"  SSHFS: Error: {e}")

        if attempt < max_retries:
            print(f"  SSHFS: Retrying in 2s...")
            time.sleep(2)

    return False


def unmount_sshfs(mount_point: Path) -> bool:
    """Unmount sshfs mount point. Returns True on success."""
    import subprocess as sp

    if not is_sshfs_mounted(mount_point):
        return True  # Not mounted, nothing to do

    print(f"  SSHFS: Unmounting {mount_point}...")

    # Use umount on macOS/Linux
    result = sp.run(["umount", str(mount_point)], capture_output=True, text=True)

    if result.returncode != 0:
        # Try fusermount on Linux
        result = sp.run(["fusermount", "-u", str(mount_point)], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  SSHFS: Unmount failed: {result.stderr.strip()}")
        return False

    print(f"  SSHFS: Unmounted successfully")
    return True


def parse_skip_indices(skip_args: list[str] | None) -> set[int]:
    """Parse skip arguments into a set of indices.

    Supports formats:
    - Space separated: --skip 41 12 53
    - Ranges: --skip 43-47
    - Comma separated: --skip 14,9,21,33-37
    - Mixed: --skip 41 12 53 43-47
    """
    if not skip_args:
        return set()

    indices = set()
    for arg in skip_args:
        # Split by comma first
        parts = arg.split(',')
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if '-' in part and not part.startswith('-'):
                # Range like 43-47
                try:
                    start, end = part.split('-', 1)
                    for i in range(int(start), int(end) + 1):
                        indices.add(i)
                except ValueError:
                    print(f"Warning: Invalid range '{part}', skipping")
            else:
                # Single number
                try:
                    indices.add(int(part))
                except ValueError:
                    print(f"Warning: Invalid index '{part}', skipping")

    return indices


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Upload YouTube playlist to NotebookLM with Simplified → Traditional Chinese conversion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 manipulate_bookmarklm_from_yt_playlist.py "https://www.youtube.com/playlist?list=PLxxx"
  python3 manipulate_bookmarklm_from_yt_playlist.py "https://www.youtube.com/watch?v=abc&list=PLxxx"
  python3 manipulate_bookmarklm_from_yt_playlist.py -i 25 "https://..."      # 25 second interval
  python3 manipulate_bookmarklm_from_yt_playlist.py -r                       # Resume (URL from index.list)
  python3 manipulate_bookmarklm_from_yt_playlist.py -r "https://..."         # Resume with explicit URL
  python3 manipulate_bookmarklm_from_yt_playlist.py --retry 3 "https://..."  # Max 3 retries before whisper
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
    parser.add_argument(
        "--start-from",
        type=int,
        metavar="N",
        help="Start from index N (skip all entries before N)"
    )
    parser.add_argument(
        "--skip",
        type=str,
        nargs='*',
        metavar="N",
        help="Skip specific indices (e.g., --skip 41 12 53 43-47 or --skip 14,9,21,33-37)"
    )
    parser.add_argument(
        "--colab-url",
        type=str,
        metavar="URL",
        help="Gradio API URL for Colab T4 GPU transcription (e.g., https://xxxxx.gradio.live)"
    )
    parser.add_argument(
        "--no-local-fallback",
        action="store_true",
        help="Disable local whisper fallback when remote options fail (default: fallback enabled)"
    )
    parser.add_argument(
        "--remote-sshfs",
        type=str,
        metavar="USER@HOST[:PATH]",
        help="Remote whisper via SSHFS (e.g., cschen@genesis or cschen@genesis:/custom/path, default path: /genesis/tmp)"
    )
    parser.add_argument(
        "--colab-timeout",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Timeout for Colab API requests in seconds (default: 0 = no timeout, status checked every 5s)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )
    return parser.parse_args()


def main():
    print()  # Empty line prefix for readability

    # Register exit timestamp (prints on any exit including Ctrl+C and errors)
    import atexit
    from datetime import datetime
    def print_exit_timestamp():
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Session ended")
    atexit.register(print_exit_timestamp)

    # Check for local .notebooklm directory (project-local config)
    import os
    local_notebooklm = Path(".notebooklm")
    if local_notebooklm.is_dir():
        os.environ["NOTEBOOKLM_HOME"] = str(local_notebooklm.absolute())
        print(f"Using local config: {local_notebooklm.absolute()}")

    args = parse_args()
    url = args.url
    delay_seconds = args.interval
    resume_mode = args.resume
    max_retries = args.retry
    use_whisper = not args.without_whisper
    colab_url = args.colab_url
    local_fallback = not args.no_local_fallback  # Default: True (fallback enabled)
    colab_timeout = args.colab_timeout
    global DEBUG
    DEBUG = args.debug
    start_from = args.start_from
    skip_indices = parse_skip_indices(args.skip)
    remote_sshfs = parse_remote_sshfs(args.remote_sshfs)

    # File paths (in current directory)
    index_file = Path("index.list")
    ok_file = Path("add_source_ok.txt")
    video2txt_file = Path("add_source_video2txt.txt")  # For whisper fallback successes
    skip_file = Path("add_source_skip.txt")  # For skipped videos (when whisper disabled)
    transcripts_dir = Path("transcripts")  # For whisper transcripts
    lock_file = Path("add_source_working.lock")  # Multi-session coordination
    sshfs_mount_point = transcripts_dir / "remote_sshfs"  # SSHFS mount point
    sshfs_config = None  # Will be set if --remote-sshfs is used and mount succeeds
    ssh_config = None  # Will be set if SSHFS mount fails (fallback to direct SSH)

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
    if start_from is not None:
        print(f"Start from: #{start_from}")
    if skip_indices:
        print(f"Skip indices: {sorted(skip_indices)}")
    if colab_url:
        print(f"Colab URL: {colab_url}")
        print(f"Colab timeout: {colab_timeout}s")
    if remote_sshfs:
        ssh_user, ssh_host, remote_path = remote_sshfs
        print(f"Remote SSHFS: {ssh_user}@{ssh_host}:{remote_path}")
    if colab_url or remote_sshfs:
        print(f"Local fallback: {'ON' if local_fallback else 'OFF'}")

    # 2a. Mount SSHFS if configured (try SSHFS first, fall back to SSH if mount fails)
    if remote_sshfs:
        ssh_user, ssh_host, remote_path = remote_sshfs
        print(f"\nMounting SSHFS...")
        if mount_sshfs(ssh_user, ssh_host, remote_path, sshfs_mount_point):
            # SSHFS mounted successfully
            sshfs_config = (sshfs_mount_point, ssh_user, ssh_host, remote_path)
            # Register cleanup on exit (normal or error)
            import atexit
            atexit.register(unmount_sshfs, sshfs_mount_point)
        else:
            # SSHFS mount failed - fall back to direct SSH method
            print(f"  SSHFS mount failed, will use direct SSH method instead")
            ssh_config = (ssh_user, ssh_host, remote_path)

    # 2b. Cleanup stale locks from crashed sessions
    stale_removed = cleanup_stale_locks(lock_file)
    if stale_removed > 0:
        print(f"Cleaned up {stale_removed} stale lock(s) from crashed sessions")

    # 2c. Cleanup any existing error sources
    print(f"\nChecking for error sources to clean up...")
    deleted_count = cleanup_error_sources()
    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} error source(s)")
    else:
        print("No error sources found")

    # 3. Get video URLs (from YouTube or index.list)
    # video_entries: list of (index, url, title) tuples
    video_entries = []
    url_to_index = {}  # Map URL to its index number

    if resume_mode and index_file.exists():
        # Resume: load from index.list
        print(f"\nLoading videos from {index_file}...")
        with open(index_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Format: "index\turl\ttitle" (tab-separated)
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        idx = int(parts[0])
                        video_url = parts[1]
                        title = parts[2].strip('"') if len(parts) >= 3 else ""
                        video_entries.append((idx, video_url, title))
                        url_to_index[video_url] = idx
        print(f"Loaded {len(video_entries)} videos from index.list")
    else:
        # Fresh: extract from YouTube
        print(f"\nExtracting videos from playlist...")
        video_data = get_playlist_videos(playlist_url)

        if not video_data:
            print("Error: No videos found in playlist.", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(video_data)} videos")

        # Build entries with index
        for i, (video_url, title) in enumerate(video_data, 1):
            video_entries.append((i, video_url, title))
            url_to_index[video_url] = i

        # Write to index.list (with playlist URL on first line)
        write_index_list(video_data, playlist_url, index_file)
        print(f"Written to {index_file}")

    # 4. Load completed URLs from ok file and video2txt file
    completed_urls = load_ok_urls(ok_file)
    video2txt_urls = load_video2txt_urls(video2txt_file)
    all_completed = completed_urls | video2txt_urls


    # 5. Determine pending entries (index, url, title)
    pending_entries = [(idx, u, t) for idx, u, t in video_entries if u not in all_completed]

    # Apply --start-from filter if specified
    if start_from is not None:
        pending_entries = [(idx, u, t) for idx, u, t in pending_entries if idx >= start_from]
        print(f"Starting from index #{start_from}")

    # Apply --skip filter if specified
    if skip_indices:
        before_count = len(pending_entries)
        pending_entries = [(idx, u, t) for idx, u, t in pending_entries if idx not in skip_indices]
        skipped_count = before_count - len(pending_entries)
        if skipped_count > 0:
            print(f"Skipped {skipped_count} entries by --skip filter")

    # Filter out indices being processed by other sessions
    working_indices = load_working_indices(lock_file)
    if working_indices:
        pending_entries = [(idx, u, t) for idx, u, t in pending_entries if idx not in working_indices]
        print(f"Other sessions working on: {sorted(working_indices)}")

    if len(all_completed) > 0:
        print(f"\nProgress: {len(completed_urls)} YouTube + {len(video2txt_urls)} Whisper = {len(all_completed)} completed, {len(pending_entries)} remaining")

    if not pending_entries:
        print("\nAll videos already processed!")
        print()  # Empty line suffix
        sys.exit(0)

    # 7. Process each video
    success_count = 0
    youtube_count = 0  # Counter for direct YouTube source additions
    whisper_count = 0  # Counter for whisper transcription fallbacks
    processed_count = 0  # Counter for videos actually processed by this session
    current_working_idx = None  # Track current index for Ctrl+C cleanup

    def handle_interrupt(signum, frame):
        """Release lock and unmount sshfs on Ctrl+C."""
        if current_working_idx is not None:
            print(f"\n  Interrupted! Releasing lock for #{current_working_idx}...")
            release_index(current_working_idx, lock_file)
        if sshfs_config:
            unmount_sshfs(sshfs_mount_point)
        sys.exit(130)

    import signal
    signal.signal(signal.SIGINT, handle_interrupt)

    for entry_idx, video_url, cached_title in pending_entries:
        # Multi-session: reload completed URLs to avoid re-processing
        fresh_completed = load_ok_urls(ok_file) | load_video2txt_urls(video2txt_file)
        if video_url in fresh_completed:
            print(f"\n#{entry_idx}: Already completed by another session, skipping")
            continue

        # Multi-session: claim this index (skip if another session grabbed it)
        if not claim_index(entry_idx, lock_file):
            print(f"\n#{entry_idx}: Being processed by another session, skipping")
            continue
        current_working_idx = entry_idx
        processed_count += 1

        print(f"\n[{processed_count}/{len(pending_entries)}] #{entry_idx}: {video_url}")

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
                        # Try whisper fallback - use cached title from index.list
                        fallback_method = "Colab" if colab_url else ("SSHFS" if sshfs_config else ("SSH" if ssh_config else "local"))
                        print(f"  Trying whisper fallback ({fallback_method})...")
                        # cached_title is already in Traditional Chinese
                        indexed_title = format_title_with_index(entry_idx, cached_title)
                        whisper_ok, txt_file = do_whisper_transcription(
                            video_url, cached_title, transcripts_dir,
                            colab_url=colab_url,
                            sshfs_config=sshfs_config,
                            ssh_config=ssh_config,
                            local_fallback=local_fallback,
                            colab_timeout=colab_timeout
                        )
                        if whisper_ok:
                            print(f"  Adding transcript as text source: {indexed_title}")
                            text_ok, text_source_id = add_text_source(txt_file, indexed_title)
                            if text_ok:
                                elapsed_seconds = int(time.time() - start_time)
                                record_video2txt_url(entry_idx, video_url, elapsed_seconds, video2txt_file)
                                success_count += 1
                                whisper_count += 1
                                print(f"  SUCCESS [Whisper]: Recorded to {video2txt_file}")
                            else:
                                print(f"\n  FATAL [#{entry_idx}]: Add text source failed: {text_source_id}")
                                release_index(entry_idx, lock_file)
                                print()
                                sys.exit(1)
                        else:
                            print(f"\n  FATAL [#{entry_idx}]: Whisper fallback failed!")
                            release_index(entry_idx, lock_file)
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
                        # Try whisper fallback - use cached title from index.list
                        fallback_method = "Colab" if colab_url else ("SSHFS" if sshfs_config else ("SSH" if ssh_config else "local"))
                        print(f"  Trying whisper fallback ({fallback_method})...")
                        # cached_title is already in Traditional Chinese
                        indexed_title = format_title_with_index(entry_idx, cached_title)
                        whisper_ok, txt_file = do_whisper_transcription(
                            video_url, cached_title, transcripts_dir,
                            colab_url=colab_url,
                            sshfs_config=sshfs_config,
                            ssh_config=ssh_config,
                            local_fallback=local_fallback,
                            colab_timeout=colab_timeout
                        )
                        if whisper_ok:
                            print(f"  Adding transcript as text source: {indexed_title}")
                            text_ok, text_source_id = add_text_source(txt_file, indexed_title)
                            if text_ok:
                                elapsed_seconds = int(time.time() - start_time)
                                record_video2txt_url(entry_idx, video_url, elapsed_seconds, video2txt_file)
                                success_count += 1
                                whisper_count += 1
                                print(f"  SUCCESS [Whisper]: Recorded to {video2txt_file}")
                            else:
                                print(f"\n  FATAL [#{entry_idx}]: Add text source failed: {text_source_id}")
                                release_index(entry_idx, lock_file)
                                print()
                                sys.exit(1)
                        else:
                            print(f"\n  FATAL [#{entry_idx}]: Whisper fallback failed!")
                            release_index(entry_idx, lock_file)
                            print()
                            sys.exit(1)
                    else:
                        # Whisper disabled - skip this video
                        print(f"  SKIP [#{entry_idx}]: Whisper disabled, skipping...")
                        record_skip_url(entry_idx, video_url, skip_file)
                    break  # Move to next URL
            print(f"OK (status: {status})")

            # Convert to Traditional Chinese and add index prefix
            traditional_title = convert_to_traditional(title)
            indexed_title = format_title_with_index(entry_idx, traditional_title)
            print(f"  Renaming: {title}")
            print(f"        → {indexed_title}")

            # Rename source with indexed title
            print("  Renaming...", end=" ", flush=True)
            if rename_source(source_id, indexed_title):
                print("OK")
            else:
                print("FAILED (source still added)")

            # Calculate elapsed time
            elapsed_seconds = int(time.time() - start_time)

            # Mark as completed - record to ok file with index and elapsed time
            record_success_url(entry_idx, video_url, elapsed_seconds, ok_file)
            success_count += 1
            youtube_count += 1
            print(f"  SUCCESS [YouTube]: Recorded to {ok_file} (elapsed: {elapsed_seconds}s)")

            # Success - exit retry loop
            break

        # Multi-session: release lock after processing (success or failure)
        release_index(entry_idx, lock_file)
        current_working_idx = None

        # Delay before next (always wait - last processed item will just exit loop)
        print(f"  Waiting {delay_seconds}s before next...")
        time.sleep(delay_seconds)

    # 8. Summary
    # Reload counts (may have been updated during this run)
    final_ok_urls = load_ok_urls(ok_file)
    final_video2txt_urls = load_video2txt_urls(video2txt_file)
    final_total = len(final_ok_urls) + len(final_video2txt_urls)
    skip_count = 0
    if skip_file.exists():
        with open(skip_file, 'r') as f:
            skip_count = sum(1 for line in f if line.strip())

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total in playlist:    {len(video_entries)}")
    print(f"Remaining:            {len(video_entries) - final_total - skip_count}")
    if skip_count > 0:
        print(f"Skipped:              {skip_count}")
    print()
    print(f"This session:")
    print(f"  YouTube direct:     {youtube_count}")
    print(f"  Whisper fallback:   {whisper_count}")
    print(f"  Total:              {success_count}")
    print()
    print(f"All time (cumulative):")
    print(f"  YouTube direct:     {len(final_ok_urls)}")
    print(f"  Whisper fallback:   {len(final_video2txt_urls)}")
    print(f"  Total completed:    {final_total}")

    print(f"\nFiles:")
    print(f"  Playlist:    {index_file.absolute()}")
    print(f"  YouTube OK:  {ok_file.absolute()} ({len(final_ok_urls)} entries)")
    print(f"  Whisper OK:  {video2txt_file.absolute()} ({len(final_video2txt_urls)} entries)")
    if skip_count > 0:
        print(f"  Skipped:     {skip_file.absolute()} ({skip_count} entries)")
    if transcripts_dir.exists():
        print(f"  Transcripts: {transcripts_dir.absolute()}/")

    print()  # Empty line suffix for readability


if __name__ == "__main__":
    main()
