# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Batch upload YouTube playlist videos to Google NotebookLM with automatic Simplified → Traditional Chinese (簡體 → 正體中文) conversion.

## Main Script: `manipulate_notebooklm_from_yt_playlist.py`

### Usage

```bash
# Fresh upload (sorted by date, oldest first — default)
python3 manipulate_notebooklm_from_yt_playlist.py "https://youtube.com/playlist?list=PLxxx"

# Keep original YouTube playlist order (no date sorting)
python3 manipulate_notebooklm_from_yt_playlist.py --sort-by-original-list-order "https://..."

# Sort newest first instead of oldest first
python3 manipulate_notebooklm_from_yt_playlist.py --reverse-order "https://..."

# Only create index.list, don't upload (no notebook needed)
python3 manipulate_notebooklm_from_yt_playlist.py --list-only "https://..."

# Reindex: rename notebook sources to match current sorted index.list
# (matches by title against YouTube playlist)
python3 manipulate_notebooklm_from_yt_playlist.py --reindex

# Reindex: rename notebook sources to match current sorted index.list
python3 manipulate_notebooklm_from_yt_playlist.py --reindex

# Resume from where you left off
python3 manipulate_notebooklm_from_yt_playlist.py -r

# Custom interval between uploads (default: 20s)
python3 manipulate_notebooklm_from_yt_playlist.py -i 30 "https://..."

# Disable whisper fallback (just skip failed videos)
python3 manipulate_notebooklm_from_yt_playlist.py --without-whisper "https://..."

# Max retries before whisper fallback (default: 2)
python3 manipulate_notebooklm_from_yt_playlist.py --retry 3 "https://..."

# Start from a specific index (skip entries before #15)
python3 manipulate_notebooklm_from_yt_playlist.py -r --start-from 15

# Skip specific indices (multiple formats supported)
python3 manipulate_notebooklm_from_yt_playlist.py -r --skip 41 12 53
python3 manipulate_notebooklm_from_yt_playlist.py -r --skip 43-47
python3 manipulate_notebooklm_from_yt_playlist.py -r --skip 14,9,21,33-37

# Use Google Colab T4 GPU for whisper (6-15x faster)
# Local fallback is ON by default (if Colab fails, falls back to local whisper)
python3 manipulate_notebooklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live "https://..."

# Colab only, no local fallback (exit if Colab fails)
python3 manipulate_notebooklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live --no-local-fallback "https://..."

# Custom Colab timeout (default: 0 = no timeout, health checked every 5s)
python3 manipulate_notebooklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live --colab-timeout 1800 "https://..."

# Use remote GPU via SSHFS (e.g., Rocky Linux desktop with RTX 2060)
python3 manipulate_notebooklm_from_yt_playlist.py --remote-sshfs cschen@genesis "https://..."

# Remote SSHFS with custom path (default: /genesis/tmp)
python3 manipulate_notebooklm_from_yt_playlist.py --remote-sshfs cschen@genesis:/custom/path "https://..."

# Remote only, no local fallback (exit if remote fails)
python3 manipulate_notebooklm_from_yt_playlist.py --remote-sshfs cschen@genesis --no-local-fallback "https://..."

# Fallback chain: Colab → SSHFS → Local
python3 manipulate_notebooklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live --remote-sshfs cschen@genesis "https://..."

# Debug mode (shows extra diagnostic output for Colab connection issues)
python3 manipulate_notebooklm_from_yt_playlist.py --debug --colab-url https://xxxxx.gradio.live "https://..."

# Multi-session: run multiple terminals in parallel (auto-coordinates)
# Terminal 1 (picks first pending video)
python3 manipulate_notebooklm_from_yt_playlist.py -r --colab-url https://xxxxx.gradio.live "https://..."
# Terminal 2 (auto-skips videos being processed, picks next available)
python3 manipulate_notebooklm_from_yt_playlist.py -r --colab-url https://xxxxx.gradio.live "https://..."

# Full auto: setup folder + notebook + index + reindex + upload (one command)
python3 manipulate_notebooklm_from_yt_playlist.py --auto "https://..."

# Setup only: create folder, auth, find/create notebook, then exit
python3 manipulate_notebooklm_from_yt_playlist.py --setup "https://..."

# Update all playlist folders under a directory (batch --auto)
python3 manipulate_notebooklm_from_yt_playlist.py --update              # current dir
python3 manipulate_notebooklm_from_yt_playlist.py --update /path/to/dir # specific dir
python3 manipulate_notebooklm_from_yt_playlist.py --update -v           # verbose output
python3 manipulate_notebooklm_from_yt_playlist.py --update --debug      # debug output

# Cleanup: delete audio files where matching txt exists
python3 manipulate_notebooklm_from_yt_playlist.py --cleanup             # current dir
python3 manipulate_notebooklm_from_yt_playlist.py --cleanup /path/to/dir

# Add a single extra video (not from the source playlist) to a notebook folder
python3 manipulate_notebooklm_from_yt_playlist.py --add-video "https://youtu.be/XYZ"             # cwd
python3 manipulate_notebooklm_from_yt_playlist.py --add-video "https://youtu.be/XYZ" /path/folder # explicit folder
python3 manipulate_notebooklm_from_yt_playlist.py /path/folder --add-video "https://youtu.be/XYZ" # same (order-agnostic)

# Create a Curated notebook from scratch (no source playlist). Folder is always created in cwd.
python3 manipulate_notebooklm_from_yt_playlist.py --new-notebook "日內交易直播"                  # empty
python3 manipulate_notebooklm_from_yt_playlist.py --new-notebook "https://youtu.be/XYZ"          # name auto-derived
python3 manipulate_notebooklm_from_yt_playlist.py --new-notebook "日內交易直播" "https://youtu.be/XYZ"  # both, any order, comma OK

# Promote a Curated notebook to Managed by attaching a source playlist
python3 manipulate_notebooklm_from_yt_playlist.py --attach-playlist "https://...playlist?list=PLxxx"  # cwd
python3 manipulate_notebooklm_from_yt_playlist.py --attach-playlist "https://..." /path/folder         # explicit folder
# (Then run --auto separately to bulk-import the playlist's videos)

# Try to replace whisper text sources with native YouTube sources
python3 manipulate_notebooklm_from_yt_playlist.py --text-back-to-video-effort          # all text sources
python3 manipulate_notebooklm_from_yt_playlist.py --text-back-to-video-effort "https://..." # specific URL

# Disable remote SSHFS (on by default with cschen@genesis)
python3 manipulate_notebooklm_from_yt_playlist.py --no-remote-sshfs "https://..."

# Auto-accept all yes/no prompts
python3 manipulate_notebooklm_from_yt_playlist.py -y -r "https://..."
```

### URL Handling (Fool-proof)

- `https://youtube.com/playlist?list=PLxxx` → Uses directly
- `https://youtube.com/watch?v=xxx&list=PLyyy&index=5` → Extracts playlist ID
- `https://youtube.com/watch?v=xxx` (no list=) → Error, exits

## Flow / SOP

```
1. Parse URL → Extract playlist ID
2. Check notebook selected (`notebooklm status`)
3. Cleanup error sources from NotebookLM
4. Load video URLs (from YouTube or index.list if -r)
4b. Sort by date (default): title date → upload timestamp → original order
5. Load completed URLs from add_source_ok.txt and add_source_video2txt.txt
6. For each pending video:
   a) Try `notebooklm source add <url>`
   b) Wait for processing, check status
   c) If error → cleanup error sources → retry (up to --retry times)
   d) If still fails → whisper fallback (unless --without-whisper)
   e) Convert title 簡體 → 正體中文
   f) Rename source in NotebookLM
   g) Record to add_source_ok.txt
7. Summary
```

## Whisper Fallback Flow

When NotebookLM fails to process a YouTube video (no transcript), the script tries whisper transcription in this order:

**Fallback Chain: Colab → SSHFS → SSH → Local**

1. **Colab** (if `--colab-url` provided): Send to Google Colab T4 GPU via Gradio API
2. **SSHFS** (if `--remote-sshfs` provided and mount succeeds): Run on remote GPU via SSHFS mount
3. **SSH** (if SSHFS mount fails): Run on remote GPU via direct SSH (no mount needed)
4. **Local** (default fallback): Run whisper locally

Use `--no-local-fallback` to exit instead of falling back to local whisper.

### Whisper Steps (applies to all methods)

```
1. Check for existing files (resume support):
   - If txt exists → reuse directly (skip steps 2-4)
   - If mp3 exists but no txt → skip to step 3
   - If neither exists → continue to step 2
2. Download audio with yt-dlp → transcripts/<title>.mp3
3. Transcribe with whisper:
   - --language Chinese
   - --initial_prompt 繁體中文
   - --verbose True (shows real-time progress)
4. Convert transcript 簡體 → 正體中文 (opencc)
5. Prepend `#URL <video_url>` as first line (traceability)
6. Save to transcripts/<title>.txt
7. Add as text source to NotebookLM
```

### SSHFS Remote Whisper

When using `--remote-sshfs user@host[:path]`:

**Primary method (SSHFS mount):**
```
1. Mount remote filesystem via SSHFS at ./transcripts/remote_sshfs/ (2 attempts)
2. Download mp3 to remote mount (via sshfs)
3. Run whisper on remote via SSH (output streams to terminal)
4. Copy txt to local ./transcripts/
5. Unmount on exit (normal, error, or Ctrl-C)
```

**Fallback method (direct SSH, if SSHFS mount fails):**
```
1. Run yt-dlp on remote via SSH → /genesis/tmp/<title>.mp3
2. Run whisper on remote via SSH (output streams to terminal)
3. scp txt back to local ./transcripts/
4. Delete remote mp3 and txt (cleanup)
```

Default remote: `cschen@genesis:/genesis/tmp` (enabled by default, use `--no-remote-sshfs` to disable)

**Resume from partial whisper state**: If script exits during whisper (e.g., download succeeded but transcription failed), the next `-r` run will reuse the existing mp3/txt files instead of restarting from scratch.

## Auto Mode (`--auto`)

Fully automated single-playlist processing in one command:
```
1. auto_setup(): get playlist title → create subfolder → copy auth → find/create notebook
2. Create index.list (sorted by date)
3. Reindex existing sources (if any)
4. Upload all pending videos (same as normal flow)
5. Text-back-to-video effort (try to upgrade whisper sources)
```

## Update Mode (`--update [PATH]`)

Batch processing across multiple playlists:
```
1. Find all subdirs under PATH containing index.list files
2. For each: run `--auto` as subprocess (1-hour timeout per folder)
3. Log output to update.log in each folder
4. Print summary (up-to-date / updated / errors)
```

## Text-Back-to-Video (`--text-back-to-video-effort`)

Attempts to replace whisper text sources with native YouTube imports:
```
1. List all sources, find text-type sources with #URL header
2. For each: try notebooklm source add <youtube_url>
3. If success: delete old text source, rename new source, update tracking
4. If fail: delete failed new source, keep old text source unchanged
```
Also runs automatically at the end of every normal upload session.

## File Structure

```
./
├── manipulate_notebooklm_from_yt_playlist.py  # Main script
├── index.list              # Playlist URLs (auto-generated)
├── add_source_ok.txt       # Successfully uploaded (direct)
├── add_source_video2txt.txt # Successfully uploaded (via whisper)
├── add_source_skip.txt     # Skipped (when --without-whisper)
├── add_source_working.lock # Multi-session coordination (auto-managed)
├── update.log              # Last --update run output (per folder)
├── transcripts/            # Whisper output folder
│   ├── <title>.mp3         # Downloaded audio
│   ├── <title>.txt         # Transcripts (正體中文)
│   └── remote_sshfs/       # SSHFS mount point (auto-managed)
└── CLAUDE.md               # This file
```

## File Formats

**index.list:** (tab-separated, sorted by date by default)
```
# playlist: https://youtube.com/playlist?list=PLxxx
1	https://youtube.com/watch?v=aaa	影片標題一	20141226
2	https://youtube.com/watch?v=bbb	影片標題二	20150102
...
```
Format: `<index>\t<url>\t<title>\t<sort_date>` (title in Traditional Chinese, sort_date is optional)

**add_source_ok.txt / add_source_video2txt.txt:**
```
1 https://youtube.com/watch?v=aaa 45
2 https://youtube.com/watch?v=bbb 32
```
Format: `<index> <url> <elapsed_seconds>`

**add_source_skip.txt:**
```
5 https://youtube.com/watch?v=eee
```
Format: `<index> <url>`

## Key Functions

| Function | Purpose |
|----------|---------|
| `extract_playlist_id(url)` | Extract playlist ID from various URL formats |
| `check_notebook_selected()` | Verify a notebook is selected in notebooklm |
| `cleanup_error_sources()` | Delete all sources with status=error |
| `get_playlist_videos(url)` | Extract video URLs and titles (正體中文) from playlist |
| `extract_date_from_title(title)` | Extract YYYYMMDD date from title (multiple formats) |
| `fetch_upload_timestamps(urls)` | Fetch upload timestamps via yt-dlp (parallel, 4 threads) |
| `sort_videos_by_date(videos, reverse)` | Sort by date: title date → upload timestamp → original order |
| `reindex_sources(old_index, ...)` | Rename notebook sources to match current sorted index.list |
| `add_source(url)` | Add YouTube URL to NotebookLM |
| `wait_for_source_with_status(id)` | Wait and check if source processed OK |
| `convert_to_traditional(text)` | 簡體 → 正體中文 using opencc |
| `format_title_with_index(idx, title)` | Create `[001] 標題` format |
| `whisper_fallback(url, title, dir)` | Download audio, transcribe locally (with resume support) |
| `whisper_via_colab(url, title, dir, colab_url)` | Transcribe via Colab T4 GPU (with resume support) |
| `whisper_via_sshfs(url, title, dir, mount, user, host, path)` | Transcribe via remote GPU over SSHFS |
| `do_whisper_transcription(...)` | Wrapper: routes to Colab → SSHFS → local |
| `mount_sshfs(user, host, path, mount_point)` | Mount remote filesystem via SSHFS |
| `unmount_sshfs(mount_point)` | Unmount SSHFS mount point |
| `add_text_source(txt, title)` | Add text file to NotebookLM |
| `auto_setup(url)` | Create subfolder, copy auth, find/create notebook |
| `find_or_create_notebook(title)` | Find existing or create new notebook by playlist title |
| `text_back_to_video_effort(...)` | Replace whisper text sources with native YouTube sources |
| `run_update(start_path, verbose, debug)` | Traverse dirs, run `--auto` for each playlist folder |
| `cleanup_mp3_files(start_path)` | Delete audio files where matching txt exists |
| `find_playlist_folders(start_path)` | Find subdirs containing index.list files |
| `claim_index(idx, lock_file)` | Multi-session: atomically claim a video index |
| `release_index(idx, lock_file)` | Multi-session: release a claimed index |

## Dependencies

```bash
pip install notebooklm-py opencc-python-reimplemented yt-dlp openai-whisper gradio_client
```

Also requires:
- ffmpeg (for whisper/yt-dlp)

## Setup (First Time)

```bash
# 1. Authenticate with Google (opens browser)
notebooklm auth

# 2. List available notebooks
notebooklm list

# 3. Select target notebook
notebooklm use <notebook_id>

# 4. Verify notebook is selected
notebooklm status
```

## Multi-Notebook Support (Local Config)

The script auto-detects `.notebooklm/` in the current directory for project-local config. This allows running multiple sessions targeting different notebooks simultaneously.

```bash
# Setup project-local config
mkdir -p .notebooklm
cp ~/.notebooklm/storage_state.json .notebooklm/   # Copy auth
notebooklm use <notebook_id>                        # Saved to .notebooklm/context.json
```

Add to `~/.zshrc` or `~/.bashrc` for CLI auto-detection:
```bash
notebooklm() {
  if [[ -d ".notebooklm" ]]; then
    NOTEBOOKLM_HOME=.notebooklm command notebooklm "$@"
  else
    command notebooklm "$@"
  fi
}
```

**For Colab integration:**
- `gradio_client` (included above)
- Running Colab notebook with Gradio API (see USING_COLAB_4WHISPER.md)

**For SSHFS/SSH integration:**
- `sshfs` (optional, macOS: `brew install macfuse sshfs`, Linux: `yum install fuse-sshfs`)
- SSH key-based auth to remote host (passwordless)
- `whisper` and `yt-dlp` installed on remote with GPU support (CUDA)
- If `sshfs` is not installed, script automatically uses direct SSH method

## NotebookLM CLI Commands

```bash
# List notebooks
notebooklm list

# Select notebook
notebooklm use <notebook_id>

# Check status
notebooklm status

# List sources
notebooklm source list
notebooklm source list --json

# Add source
notebooklm source add <url>
notebooklm source add --type text --title "Title" file.txt

# Delete source
notebooklm source delete <source_id> --yes

# Rename source
notebooklm source rename <source_id> "New Title"
```

## Important Notes

1. **Source Title Format**: `[001] 標題`
   - Zero-padded 3-digit index prefix
   - Matches index.list entry numbers
   - Helps sort/identify sources in NotebookLM
   - Regex to extract: `\[(\d+)\]`

2. **正體中文 Conversion**: Applied to:
   - Source title in NotebookLM
   - Transcript content (txt body)
   - Filenames (mp3, txt)

3. **Error Source Cleanup**: Runs at startup AND after each failure to prevent orphaned error entries

4. **Title Matching Unreliable**: Don't match by title to detect duplicates - playlists often have same titles for different videos

5. **Whisper Progress**: Uses `--verbose True` with direct terminal output to show real-time transcription

6. **Resume Mode (-r)**:
   - Can omit URL (reads from index.list)
   - Skips URLs in add_source_ok.txt and add_source_video2txt.txt

7. **Never redo work on disk**: Before downloading or transcribing, always check `transcripts/` (in current working directory) for existing files:
   - `.txt` exists → reuse directly (skip download + whisper)
   - `.mp3` exists but no `.txt` → skip download, just whisper
   - Neither exists → full download + whisper
   - Applies to all flows: normal upload, resume, and `--reindex` (when re-adding text sources)

8. **notebooklm source add**: Do NOT use `--type text` for file uploads — it treats the argument as inline text (stores the file path, not the content). Let auto-detect handle `.txt` files, then rename to set the correct title.

9. **#URL traceability**: Whisper transcripts have `#URL <video_url>` as the first line for URL-based matching in `--reindex`/`--reorder`

10. **`--reindex`/`--reorder` = rename only**: Never delete sources, never re-create. YouTube sources imported natively are precious (notebooklm-py `source add` for YouTube fails frequently). Only use `notebooklm source rename` to update titles.

## Troubleshooting

**"API returned no data for URL"**: Video has no transcript on YouTube. Whisper fallback will handle it.

**Whisper too slow**: Use `--without-whisper` to skip, use `--colab-url` for Colab T4 GPU, use `--remote-sshfs` for your own GPU server, or be patient (30+ min for long videos on CPU).

**Error sources accumulating**: Script auto-cleans, but you can manually run:
```bash
notebooklm source list  # Find error sources
notebooklm source delete <id> --yes
```

**Colab connection failed**: Ensure Colab notebook is running with `demo.launch(share=True)`. The URL changes each session.

**Colab timeout**: Increase with `--colab-timeout 900` for very long videos. Default is 600s (10 min).

**Colab disconnected mid-transcription**: Local fallback is enabled by default. Use `--no-local-fallback` if you want to exit on Colab failure instead.

**SSHFS mount failed**: The script will automatically fall back to direct SSH method (no mount needed). If SSH also fails, check connection with `ssh user@host`.

**SSHFS/SSH whisper failed**: Ensure `whisper` and `yt-dlp` are installed on remote with CUDA support. Test with:
```bash
ssh user@host "whisper --help"
ssh user@host "yt-dlp --help"
```

**SSHFS/SSH permission denied**: Ensure the remote path is writable. Test with `ssh user@host "touch /genesis/tmp/test && rm /genesis/tmp/test"`.
