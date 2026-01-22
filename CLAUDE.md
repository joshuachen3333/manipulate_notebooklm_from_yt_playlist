# CLAUDE.md - Project Knowledge Base

## Project Overview

Batch upload YouTube playlist videos to Google NotebookLM with automatic Simplified → Traditional Chinese (簡體 → 正體中文) conversion.

## Main Script: `upload_playlist.py`

### Usage

```bash
# Fresh upload
python3 upload_playlist.py "https://youtube.com/playlist?list=PLxxx"

# Resume from where you left off
python3 upload_playlist.py -r

# Custom interval between uploads (default: 20s)
python3 upload_playlist.py -i 30 "https://..."

# Disable whisper fallback (just skip failed videos)
python3 upload_playlist.py --without-whisper "https://..."

# Max retries before whisper fallback (default: 2)
python3 upload_playlist.py --retry 3 "https://..."
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

When NotebookLM fails to process a YouTube video (no transcript):

```
1. Download audio with yt-dlp → transcripts/<title>.mp3
2. Transcribe with whisper:
   - --language Chinese
   - --initial_prompt 繁體中文
   - --verbose True (shows real-time progress)
3. Convert transcript 簡體 → 正體中文 (opencc)
4. Save to transcripts/<title>.txt
5. Add as text source to NotebookLM
```

## File Structure

```
./
├── upload_playlist.py      # Main script
├── index.list              # Playlist URLs (auto-generated)
├── add_source_ok.txt       # Successfully uploaded (direct)
├── add_source_video2txt.txt # Successfully uploaded (via whisper)
├── add_source_skip.txt     # Skipped (when --without-whisper)
├── transcripts/            # Whisper output folder
│   ├── <title>.mp3         # Downloaded audio
│   └── <title>.txt         # Transcripts (正體中文)
└── CLAUDE.md               # This file
```

## File Formats

**index.list:**
```
# playlist: https://youtube.com/playlist?list=PLxxx
1 https://youtube.com/watch?v=aaa
2 https://youtube.com/watch?v=bbb
...
```

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
| `add_source(url)` | Add YouTube URL to NotebookLM |
| `wait_for_source_with_status(id)` | Wait and check if source processed OK |
| `convert_to_traditional(text)` | 簡體 → 正體中文 using opencc |
| `format_title_with_index(idx, title)` | Create `[001] 標題` format |
| `whisper_fallback(url, title, dir)` | Download audio, transcribe, save |
| `add_text_source(txt, title)` | Add text file to NotebookLM |

## Dependencies

```bash
pip install opencc-python-reimplemented yt-dlp openai-whisper
```

Also requires:
- `notebooklm` CLI (notebooklm-py)
- ffmpeg (for whisper/yt-dlp)

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

**Whisper too slow**: Use `--without-whisper` to skip, or be patient (30+ min for long videos).

**Error sources accumulating**: Script auto-cleans, but you can manually run:
```bash
notebooklm source list  # Find error sources
notebooklm source delete <id> --yes
```
