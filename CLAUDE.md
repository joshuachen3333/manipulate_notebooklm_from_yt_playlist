# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Batch upload YouTube playlist videos to Google NotebookLM with automatic Simplified → Traditional Chinese (簡體 → 正體中文) conversion.

## Main Script: `manipulate_bookmarklm_from_yt_playlist.py`

### Usage

```bash
# Fresh upload
python3 manipulate_bookmarklm_from_yt_playlist.py "https://youtube.com/playlist?list=PLxxx"

# Resume from where you left off
python3 manipulate_bookmarklm_from_yt_playlist.py -r

# Custom interval between uploads (default: 20s)
python3 manipulate_bookmarklm_from_yt_playlist.py -i 30 "https://..."

# Disable whisper fallback (just skip failed videos)
python3 manipulate_bookmarklm_from_yt_playlist.py --without-whisper "https://..."

# Max retries before whisper fallback (default: 2)
python3 manipulate_bookmarklm_from_yt_playlist.py --retry 3 "https://..."

# Start from a specific index (skip entries before #15)
python3 manipulate_bookmarklm_from_yt_playlist.py -r --start-from 15

# Skip specific indices (multiple formats supported)
python3 manipulate_bookmarklm_from_yt_playlist.py -r --skip 41 12 53
python3 manipulate_bookmarklm_from_yt_playlist.py -r --skip 43-47
python3 manipulate_bookmarklm_from_yt_playlist.py -r --skip 14,9,21,33-37

# Use Google Colab T4 GPU for whisper (6-15x faster)
# Local fallback is ON by default (if Colab fails, falls back to local whisper)
python3 manipulate_bookmarklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live "https://..."

# Colab only, no local fallback (exit if Colab fails)
python3 manipulate_bookmarklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live --no-local-fallback "https://..."

# Custom Colab timeout (default: 0 = no timeout, health checked every 5s)
python3 manipulate_bookmarklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live --colab-timeout 1800 "https://..."

# Use remote GPU via SSHFS (e.g., Rocky Linux desktop with RTX 2060)
python3 manipulate_bookmarklm_from_yt_playlist.py --remote-sshfs cschen@genesis "https://..."

# Remote SSHFS with custom path (default: /genesis/tmp)
python3 manipulate_bookmarklm_from_yt_playlist.py --remote-sshfs cschen@genesis:/custom/path "https://..."

# Remote only, no local fallback (exit if remote fails)
python3 manipulate_bookmarklm_from_yt_playlist.py --remote-sshfs cschen@genesis --no-local-fallback "https://..."

# Fallback chain: Colab → SSHFS → Local
python3 manipulate_bookmarklm_from_yt_playlist.py --colab-url https://xxxxx.gradio.live --remote-sshfs cschen@genesis "https://..."

# Debug mode (shows extra diagnostic output for Colab connection issues)
python3 manipulate_bookmarklm_from_yt_playlist.py --debug --colab-url https://xxxxx.gradio.live "https://..."

# Multi-session: run multiple terminals in parallel (auto-coordinates)
# Terminal 1 (picks first pending video)
python3 manipulate_bookmarklm_from_yt_playlist.py -r --colab-url https://xxxxx.gradio.live "https://..."
# Terminal 2 (auto-skips videos being processed, picks next available)
python3 manipulate_bookmarklm_from_yt_playlist.py -r --colab-url https://xxxxx.gradio.live "https://..."
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
5. Save to transcripts/<title>.txt
6. Add as text source to NotebookLM
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

Default remote path: `/genesis/tmp`

**Resume from partial whisper state**: If script exits during whisper (e.g., download succeeded but transcription failed), the next `-r` run will reuse the existing mp3/txt files instead of restarting from scratch.

## File Structure

```
./
├── manipulate_bookmarklm_from_yt_playlist.py  # Main script
├── index.list              # Playlist URLs (auto-generated)
├── add_source_ok.txt       # Successfully uploaded (direct)
├── add_source_video2txt.txt # Successfully uploaded (via whisper)
├── add_source_skip.txt     # Skipped (when --without-whisper)
├── add_source_working.lock # Multi-session coordination (auto-managed)
├── transcripts/            # Whisper output folder
│   ├── <title>.mp3         # Downloaded audio
│   ├── <title>.txt         # Transcripts (正體中文)
│   └── remote_sshfs/       # SSHFS mount point (auto-managed)
└── CLAUDE.md               # This file
```

## File Formats

**index.list:** (tab-separated)
```
# playlist: https://youtube.com/playlist?list=PLxxx
1	https://youtube.com/watch?v=aaa	影片標題一
2	https://youtube.com/watch?v=bbb	影片標題二
...
```
Format: `<index>\t<url>\t<title>` (title in Traditional Chinese)

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
