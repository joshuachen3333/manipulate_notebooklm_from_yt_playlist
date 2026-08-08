# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Batch upload YouTube playlist videos to Google NotebookLM with automatic Simplified → Traditional Chinese (簡體 → 正體中文) conversion.

## Everyday Commands (the two that matter)

```bash
# 1. Routine update of ALL existing playlists — run from the PARENT directory
#    that holds every playlist subfolder. Finds each subfolder with an
#    index.list and runs --auto inside it (subprocess, 1h timeout per folder).
python3 manipulate_notebooklm_from_yt_playlist.py --update
python3 manipulate_notebooklm_from_yt_playlist.py --update -v      # stream subprocess output
python3 manipulate_notebooklm_from_yt_playlist.py --update /path/to/playlists

# 2. A brand-new playlist — run from the PARENT directory; creates the
#    subfolder, binds/creates the notebook, indexes, uploads, all in one shot.
python3 manipulate_notebooklm_from_yt_playlist.py --auto "https://www.youtube.com/playlist?list=PLxxx"
```

Everything else in the Usage block below is a narrower tool for when one of
these two goes wrong (resume a half-finished folder, rebind a notebook,
re-order sources, add one-off videos).

### Verification / dry runs

There is no test suite. Only two non-mutating checks exist:

```bash
python3 -m py_compile manipulate_notebooklm_from_yt_playlist.py             # syntax only
python3 manipulate_notebooklm_from_yt_playlist.py --list-only "https://..."  # writes index.list only
```

`--list-only` skips `check_notebook_selected()` entirely and never calls the
notebooklm CLI — its only side effect is writing `index.list` in cwd.

**Every other flag mutates something durable.** Not just uploads:
`--setup` / `--auto` / `--bind-notebook` can *create* a cloud notebook, rename an
existing one, and `os.rename` the folder on disk. `--debug` / `-v` are output
modifiers, not dry-run switches. There is no `--dry-run`.

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
# (matches by URL / #URL header / title; rename-only, never deletes)
python3 manipulate_notebooklm_from_yt_playlist.py --reindex

# Resume from where you left off
python3 manipulate_notebooklm_from_yt_playlist.py -r

# Custom interval between uploads (default: 1s — DEFAULT_DELAY_SECONDS)
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

# Multi-session: several terminals on the SAME folder (auto-coordinates via
# add_source_working.lock). Safe — they share that folder's single .notebooklm/.
# Terminal 1 (picks first pending video)
python3 manipulate_notebooklm_from_yt_playlist.py -r --colab-url https://xxxxx.gradio.live "https://..."
# Terminal 2 (auto-skips videos being processed, picks next available)
python3 manipulate_notebooklm_from_yt_playlist.py -r --colab-url https://xxxxx.gradio.live "https://..."
# NOT safe: concurrent runs in DIFFERENT folders. Each holds its own copy of
# storage_state.json, notebooklm-py >= 0.4 rotates __Secure-1PSIDTS on use, and
# whichever rotates last revokes every other copy (including the global one).
# Run different folders sequentially. See "Storage layout changed" above.

# Full auto: setup folder + notebook + index + reindex + upload (one command)
python3 manipulate_notebooklm_from_yt_playlist.py --auto "https://..."

# Setup only: create folder, auth, find/create notebook, then exit
python3 manipulate_notebooklm_from_yt_playlist.py --setup "https://..."

# Update all playlist folders under a directory (batch --auto)
python3 manipulate_notebooklm_from_yt_playlist.py --update              # current dir
python3 manipulate_notebooklm_from_yt_playlist.py --update /path/to/dir # specific dir
python3 manipulate_notebooklm_from_yt_playlist.py --update -v           # verbose output
python3 manipulate_notebooklm_from_yt_playlist.py --update --debug      # debug output

# Re-auth: push fresh ~/.notebooklm/storage_state.json into every folder's
# local .notebooklm/. Run after `notebooklm login` when auth expired.
python3 manipulate_notebooklm_from_yt_playlist.py --reauth              # current dir
python3 manipulate_notebooklm_from_yt_playlist.py --reauth /path/to/dir

# Cleanup: delete audio files where matching txt exists
python3 manipulate_notebooklm_from_yt_playlist.py --cleanup             # current dir
python3 manipulate_notebooklm_from_yt_playlist.py --cleanup /path/to/dir

# Bind an existing folder to a specific NotebookLM notebook (standalone rebind)
python3 manipulate_notebooklm_from_yt_playlist.py --bind-notebook "https://notebooklm.google.com/notebook/<uuid>"                    # cwd
python3 manipulate_notebooklm_from_yt_playlist.py --bind-notebook "https://notebooklm.google.com/notebook/<uuid>" /path/to/folder     # explicit folder
python3 manipulate_notebooklm_from_yt_playlist.py --bind-notebook <bare-uuid>                                                          # UUID alone also OK
# (Deprecated: --notebook-url is the old name for the same flag; still works with a stderr warning.)

# Combined with --setup to bind to a specific (manually-imported) notebook instead of find/create by title
python3 manipulate_notebooklm_from_yt_playlist.py --setup "<playlist_url>" --bind-notebook "<notebook_url>"

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
# (refuses to run in a folder carrying a .keep_transcripts marker)
python3 manipulate_notebooklm_from_yt_playlist.py --text-back-to-video-effort          # all text sources
python3 manipulate_notebooklm_from_yt_playlist.py --text-back-to-video-effort "https://..." # specific URL

# Push locally corrected transcripts/*.txt back into the notebook (cwd only)
python3 manipulate_notebooklm_from_yt_playlist.py --resync-text                 # every drifted text source
python3 manipulate_notebooklm_from_yt_playlist.py --resync-text "https://..."   # one video / one playlist

# Replace NATIVE YouTube sources with the local corrected transcript (cwd only)
python3 manipulate_notebooklm_from_yt_playlist.py --text-over-video
python3 manipulate_notebooklm_from_yt_playlist.py --text-over-video "https://..."

# Rewrite local transcripts with Taiwan-standard glyphs (裏→裡, 着→著). Local-only.
python3 manipulate_notebooklm_from_yt_playlist.py --normalize-tw               # cwd
python3 manipulate_notebooklm_from_yt_playlist.py --normalize-tw /path/to/dir

# Disable remote SSHFS (on by default with cschen@genesis)
python3 manipulate_notebooklm_from_yt_playlist.py --no-remote-sshfs "https://..."

# Auto-accept all yes/no prompts
python3 manipulate_notebooklm_from_yt_playlist.py -y -r "https://..."
```

### URL Handling (Fool-proof)

- `https://youtube.com/playlist?list=PLxxx` → Uses directly
- `https://youtube.com/watch?v=xxx&list=PLyyy&index=5` → Extracts playlist ID
- `https://youtube.com/watch?v=xxx` (no list=) → Error, exits

## Architecture

Everything lives in one ~5,100-line script. The parts that need several files to
understand:

### 1. Three layers of state, one source of truth

| Layer | Files | Role |
|-------|-------|------|
| **Truth** | `index.list` | Ordering + titles + notebook binding. Hand-editable; every automated rewrite preserves manual edits. |
| **Derived** | `add_source_ok.txt`, `add_source_video2txt.txt`, `add_source_skip.txt`, `add_source_working.lock` | Per-folder progress ledgers. Rebuildable — `--reindex` re-syncs them from `index.list` + the cloud notebook. |
| **Mirror** | The NotebookLM notebook | Reconciled **rename-only**. Never bulk-deleted, because native YouTube imports are expensive and fail often. |

Reconciliation matches a cloud source to an `index.list` row by, in order:
canonical URL → the `#URL <video_url>` first line of whisper transcripts →
fuzzy title. See `_match_sources_by_title()` and `reindex_sources()`.

### 2. One folder = one notebook, and the binding is cwd-scoped

Every entry point does the same two-step before touching the CLI:
`os.chdir(<playlist folder>)`, then
`os.environ["NOTEBOOKLM_HOME"] = <folder>/.notebooklm`. That's why **every
command is cwd-sensitive** and why parallel sessions in different folders can
target different notebooks simultaneously. The binding itself is recorded in
`index.list` line 2, not in the CLI's global state.

`--update` therefore launches each subprocess with `cwd=<folder>` (not the
parent), so custom folder names survive repeated runs.

### 3. Managed vs Curated is decided by one empty field

`index.list` line 1 (`# playlist:`). Non-empty → **Managed** (re-scan the
YouTube playlist on every `--update`). Empty → **Curated** (hand-picked; only
`--reindex` + tracking sync run, videos arrive one at a time via `--add-video`).
`--new-notebook` creates Curated; `--attach-playlist` promotes it to Managed
(one-way, by design).

### 4. `main()` is a flat dispatch of early-exit modes

In order (`main()` starts ~line 4290):

1. `--update` → `--reauth` → `--cleanup` → `--normalize-tw` → `--add-video`
   → `--attach-playlist` → `--new-notebook` — each does its thing and
   `sys.exit()`s. `--normalize-tw` is purely local, so it exits before any
   `chdir` / `NOTEBOOKLM_HOME` work.
2. `setup_mode = args.setup or args.auto or args.target_notebook` — the shared
   folder/binding/standardize block; `--setup` exits here, `--auto` continues.
3. Post-binding standalone exits (notebook already selected, cwd-scoped):
   `--reindex`, then `--resync-text` / `--text-over-video`, then
   `--text-back-to-video-effort` — all skipped under `--auto`.
4. Fall-through: the main pipeline (index → reindex → upload loop →
   text-back-to-video). `--list-only` is *not* a dispatch mode — it's a flag
   inside this pipeline that skips the notebook check and stops after writing
   `index.list`.

When adding a mode, place it in that chain and remember it must set up
`NOTEBOOKLM_HOME` itself — the early-exit branches each do their own
`chdir` + `NOTEBOOKLM_HOME` dance.

### 5. Auth is self-healing at two levels

- `run_command()` sniffs output with `_is_auth_failure()` and, on a hit, calls
  `refresh_auth()` (copies `~/.notebooklm/storage_state.json` into the folder's
  `.notebooklm/` if newer) and retries **once**.
- `--reauth` does that push proactively across every folder in a tree.

**Both push global → local, which is the wrong direction when *global* is the
dead copy.** Every `notebooklm` call rotates `__Secure-1PSIDTS` and invalidates
every other copy, including global — and **read-only calls count**: a single
`source list` or `source fulltext` in one folder revokes the other 269 and the
global. So the freshest local `.notebooklm/` is often the only live credential,
and `--reauth` would overwrite it with a dead one.

Diagnose without any network call by comparing `__Secure-1PSIDTS` across
`~/.notebooklm/` and every `*/.notebooklm/` — newest mtime wins, everything
with a different value is revoked. Recovery is to promote that live copy back
to global *first*, then `--reauth`. Full operator procedure with the diagnostic
script: `daily_usage.md` → 〈Auth 壞掉〉.

Function inventory: `grep -n "^def " manipulate_notebooklm_from_yt_playlist.py`.

## Dual-Account (Christine / Joshua)

Two Google accounts share this tooling; `~/.notebooklm` is a **symlink** that
`nbswitch <name>` (a `~/.zshrc` function, with `nbwhich` to inspect) atomically
repoints at `~/.notebooklm-christine` / `~/.notebooklm-joshua`.

Code-facing rules:

- `get_current_account_identity()` resolves, in order: `NOTEBOOKLM_ACCOUNT` env
  var → a `.account` marker file inside `NOTEBOOKLM_HOME` → the symlink target's
  name suffix → default `christine`.
- `notebook_title_prefix()` returns `""` for joshua and `"Joshua_"` for
  christine (disambiguation inside her notebook list). New notebooks are named
  `<prefix><playlist_title>`.
- **Project-local `.notebooklm/` bindings do not follow `nbswitch`.** They are
  stamped at bind time with a `.account` marker and stay on that identity.
- Don't run `notebooklm` commands while `nbswitch` is flipping the symlink.

Full operator SOP (backup layout, share flow, risks): `NBLM_DUAL_ACCOUNT_SOP_20260610.md`.

**Storage layout changed in notebooklm-py 0.4+** (upgraded 2026-08-08, 0.3.0 → 0.8.0):
auth now lives at `<home>/profiles/<profile>/storage_state.json`, not `<home>/storage_state.json`.
The CLI auto-migrates a legacy flat dir on first use — including each folder's
`.notebooklm/`. Use `storage_state_path(home)` / `global_storage_state()` in this
script rather than hardcoding either layout. `nbswitch` / `nbwhich` in `~/.zshrc`
still switch at the `~/.notebooklm-<name>` level, which is unaffected, but any
of their internals that reference the old flat path need updating.

**Never copy a `storage_state.json` around while a session is live.** 0.8.0 rotates
`__Secure-1PSIDTS` on use; replaying a divergent snapshot makes Google revoke the
whole session and forces a fresh `notebooklm login`.

The one sanctioned copy is the reverse direction — promoting the *live* local
copy back to global when global is the revoked one, with no job running. That
is not a replay: it installs the value Google currently accepts. Verified in
practice 2026-08-08; procedure in `daily_usage.md` → 〈Auth 壞掉〉.

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
   - Attempts 1-2: --cookies-from-browser chrome (live local cookies)
   - Attempt 3: --cookies /tmp/youtube_cookies_genesis_shared.txt (scp'd
     once from cschen@genesis:/genesis/tmp/youtube_cookies_codex.txt;
     fallback for when local Chrome is closed / cookies expired)
3. Transcribe with whisper:
   - --language Chinese
   - --initial_prompt <WHISPER_INITIAL_PROMPT, or the folder's .whisper_prompt>
   - --verbose True (shows real-time progress)
4. Convert transcript 簡體 → 正體中文 (opencc `s2tw`, Taiwan standard)
5. Prepend `#URL <video_url>` as first line (traceability)
6. Save to transcripts/<title>.txt
7. Add as text source to NotebookLM
```

### Getting Traditional output out of whisper directly

Post-conversion can't be trusted alone: opencc has to *guess* on one-to-many
restorations (发 → 發/髮, 干 → 乾/幹/干, 后 → 後/后) and a wrong guess is
invisible afterwards. Text that is Traditional coming out of the decoder never
raises the question, so the prompt is the primary lever and opencc is the net.

- **`WHISPER_INITIAL_PROMPT`** is a full Traditional sentence, not the bare
  `繁體中文` this used to send — four characters are too little to steer the
  decoder. It **must stay domain-neutral** — it is what all ~270 folders get,
  from 台語 lectures to MIT/Harvard maths, and whisper emits prompt vocabulary
  into low-confidence audio, so a subject word here would surface as
  hallucinated content in unrelated channels. Subject wording goes in a
  per-folder **`.whisper_prompt`** (used by the 台語漢字學 folders), and even
  there it is a tradeoff worth spot-checking after the first re-transcription.
  Keep overrides short: whisper caps the prompt at 224 tokens and silently eats
  audio context past that.
- **Quote the prompt for the remote paths.** `ssh` joins its trailing argv with
  spaces and hands the result to the *remote* shell, which re-splits it — so
  `whisper_via_sshfs` and `whisper_via_ssh` both `shlex.quote()` it even though
  one is a list-form `sp.run`. Only the local path can pass it raw. This is why
  the old value worked: `繁體中文` has no spaces.
- **The Colab path has no prompt lever** — the Gradio endpoint takes a single
  audio input (`fn_index=0`), so `--colab-url` transcripts depend on opencc alone.

### Genesis GPU activity probe

For SSHFS/SSH whisper paths, a background daemon thread queries
`nvidia-smi` on Genesis ~90s after dispatching the whisper job. Prints
one line per probe:
- `GPU-PROBE: genesis GPU 98%, 4231 MiB (SSHFS whisper active)` — normal
- `GPU-PROBE: ⚠ genesis GPU idle (0%, 0 MiB) 90s after SSHFS whisper dispatch — possible silent failure` — sshfs hung / model load failed / etc.

The probe is informational; never blocks whisper.

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

### genesis whisper environment (as of 2026-05-05)

- `python3.12` + `cu124` torch + RTX 2060 SUPER GPU available; user-site at `/asiaa/home/cschen/.local/lib/python3.12/`
- `whisper` CLI shebang is `/usr/bin/python3.12` → calling `whisper` directly uses GPU
- Persistence mode is on; survives reboots via systemd unit `nvidia-persistenced` (fixes a NVRM `mem_desc.c:1353` kernel-space OOM)
- `whisper_via_ssh` and `whisper_via_sshfs` pass `--device cuda` (model unchanged, defaults to multilingual `turbo`)
- DO NOT use system `python3` (3.9) or its cu128 nightly torch — broken
- Verify: `ssh cschen@genesis 'python3.12 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"'` → `True NVIDIA GeForce RTX 2060 SUPER`

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

## Hand-Corrected Transcripts (`.keep_transcripts`)

Some folders (the 台語漢字學 family) hold transcripts that were hand-corrected
against 台語漢字學 scholarship. Those corrections must survive `--update`, and
the default pipeline is actively hostile to them: `text_back_to_video_effort()`
runs at the end of *every* upload session and would swap a corrected text source
for a native YouTube import whose captions are ASR.

Drop an empty **`.keep_transcripts`** next to `index.list` to opt the folder out.
The guard sits at the top of `text_back_to_video_effort()` — the single choke
point covering both the `--auto` tail and the standalone flag — so a protected
folder makes zero cloud calls. To undo, delete the marker; there is no override
flag by design.

The marker only stops the cloud from overwriting local files. Pushing
corrections **up** is a separate, always-explicit step:

| Cloud source is… | Use | What it does |
|---|---|---|
| a text source that drifted from the local txt | `--resync-text` | add local txt → verify → delete old source |
| a native YouTube import | `--text-over-video` | same swap, plus moves the row from `add_source_ok.txt` to `add_source_video2txt.txt` |

Both operate on cwd, compare/act only where a local `transcripts/*.txt` carries a
matching `#URL` header, and are **deliberately unreachable from `--auto` /
`--update`** — a 270-folder sweep must never mutate cloud sources this way.
`--text-over-video` additionally rejects any transcript whose body is under
`MIN_TRANSCRIPT_BODY_CHARS` (200) as a title-only stub.

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
├── .keep_transcripts       # Optional marker: transcripts are hand-corrected
├── .whisper_prompt         # Optional per-folder whisper --initial_prompt
├── transcripts/            # Whisper output folder
│   ├── <title>.mp3         # Downloaded audio
│   ├── <title>.txt         # Transcripts (正體中文)
│   └── remote_sshfs/       # SSHFS mount point (auto-managed)
└── CLAUDE.md               # This file
```

## File Formats

**index.list:** three header lines + tab-separated 5-column rows.
**`INDEX_LIST_SPEC.md` is authoritative** — read it before touching any index.list code.

```
# playlist:		https://youtube.com/playlist?list=PLxxx
# notebook url:		https://notebooklm.google.com/notebook/<uuid>
# notebook title:	Joshua_影片系列
1	https://youtube.com/watch?v=aaa	"影片標題一"<padded to 100>	<pad 7>	20141226
2	https://youtube.com/watch?v=bbb	"影片標題二"<padded to 100>	extra  	t:1516992468
```

Columns: `<index>\t<url>\t"<title>"\t<source>\t<sort_date>`.

- **Line 1 empty ⇒ Curated notebook**; non-empty ⇒ Managed (see Architecture §3).
- **Line 3 is the user-editable source of truth** for both the cloud notebook
  title and the on-disk folder name; automated rewrites never clobber it.
- **Column 1 is parsed as `float`** — edit a row to `0.5` / `-1` and the next
  `--reindex` sorts by it, then renumbers back to clean integers.
- **Column 4** `source`: empty = from the playlist, `extra` = added via `--add-video`.
- Column 5 `sort_date` is historical metadata, **not** the `--reindex` sort key.
- A short 3-column row (`idx\turl\t"title"`) and legacy 4-column rows are both
  still parsed; the next rewrite normalizes them.

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
| `whisper_via_ssh(url, title, dir, user, host, path)` | Transcribe via remote GPU over plain SSH (no mount) |
| `do_whisper_transcription(...)` | Wrapper: routes to Colab → SSHFS → SSH → local |
| `mount_sshfs(user, host, path, mount_point)` | Mount remote filesystem via SSHFS |
| `unmount_sshfs(mount_point)` | Unmount SSHFS mount point |
| `add_text_source(txt, title)` | Add text file to NotebookLM |
| `auto_setup(url)` | Create subfolder, copy auth, find/create notebook |
| `find_or_create_notebook(title)` | Find existing or create new notebook by playlist title |
| `text_back_to_video_effort(...)` | Replace whisper text sources with native YouTube sources (no-ops under `.keep_transcripts`) |
| `resync_text_sources(...)` | Push locally corrected transcripts back over drifted cloud text sources |
| `text_over_video(...)` | Replace native YouTube sources with the local corrected transcript |
| `normalize_tree_to_taiwan(path)` | Rewrite transcripts + index.list with Taiwan-standard glyphs (`t2tw`, in place, prompts first) |
| `load_local_transcripts(dir)` | Map canonical URL → local txt via the `#URL` header (never by filename) |
| `whisper_initial_prompt()` | Folder's `.whisper_prompt`, else `WHISPER_INITIAL_PROMPT` |
| `transcripts_are_protected()` | True when `.keep_transcripts` is present in cwd |
| `is_text_source(type)` | Text-vs-native check that tolerates `pasted_text` and `text` |
| `source_fulltext(id)` | `source fulltext` with the CLI's header block stripped |
| `comparable_text(text)` | Whitespace-normalized form for local-vs-cloud comparison |
| `run_update(start_path, verbose, debug)` | Traverse dirs, run `--auto` for each playlist folder |
| `cleanup_mp3_files(start_path)` | Delete audio files where matching txt exists |
| `find_playlist_folders(start_path)` | Find subdirs containing index.list files |
| `claim_index(idx, lock_file)` | Multi-session: atomically claim a video index |
| `release_index(idx, lock_file)` | Multi-session: release a claimed index |
| `get_current_account_identity()` | Resolve active account (`joshua` / `christine`) |
| `standardize_folder_and_notebook(...)` | Enforce index.list line 3 on cloud title + folder name |

(Not exhaustive — `grep -n "^def " manipulate_notebooklm_from_yt_playlist.py`
lists all ~90.)

## Dependencies

```bash
pip install notebooklm-py opencc-python-reimplemented yt-dlp openai-whisper gradio_client
```

Also requires:
- ffmpeg (for whisper/yt-dlp)

## Setup (First Time)

```bash
# 1. Authenticate with Google (opens browser)
notebooklm login          # (`notebooklm auth` is a different, management-only command group)

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

2. **正體中文 Conversion is Taiwan-standard everywhere** — `convert_to_traditional()`
   uses **`s2tw`**, and every generated string goes through it: transcript
   bodies, source titles, notebook titles, folder names, mp3/txt filenames.
   There is no second config and no opt-out; Taiwan orthography is the house
   standard for all generated text.

   It used to be `s2t` (general Traditional), which produces glyphs no
   Taiwanese reader uses. Measured across the tree before switching:

   | | Count |
   |---|---|
   | Video titles corrected (喫→吃, 牀→床, 脣→唇, 羣→群) | 225 of 9,790 |
   | Folder renames caused | 1 (林哲羣 → 林哲群) |
   | Notebook renames caused | 1 |

   `normalize_to_taiwan()` (`t2tw`) retrofits what was written under the old
   config: `t2tw(s2t(x)) == s2tw(x)`, verified, so **`--normalize-tw`** fixes
   files in place with no re-download and no GPU time. It covers `transcripts/*.txt`
   *and* `index.list` — the latter verified safe to convert wholesale across all
   270 files (length-preserving, no ASCII byte touched, East-Asian visual width
   unchanged, so TSV padding stays aligned). It prints the full file list and
   prompts before writing; a changed index.list line 3 makes the next `--update`
   rename the folder and cloud notebook, and changed column-3 titles are pushed
   by the next `--reindex`.

   Retrofit is **not** automatic — `--normalize-tw` is a standalone mode,
   never reached from `--auto`/`--update`.

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

10. **Three CLI-output traps — always go through the wrappers** (all three were
    live bugs found on 2026-08-08, each silently producing "nothing to do"):

    | Trap | Wrapper to use |
    |---|---|
    | `source list --json` reports text sources as **`pasted_text`**, not `text`. An exact `== "text"` test classifies every whisper upload as a native import. | `is_text_source(s.get("type"))` |
    | `source fulltext` prints a **`Source:`/`Title:`/`Characters:`/`Content:` header** before the body, so `raw.startswith('#URL ')` is never true. | `source_fulltext(source_id)` |
    | NotebookLM **double-spaces text on ingest** (98 local lines → 196 cloud lines, measured). A raw or `.strip()`-only compare marks every source as drifted. | `comparable_text(text)` on both sides |

    `source list --json` also returns `{"sources": []}` rather than an error
    when auth is expired — an empty list is not proof the notebook is empty.
    Cross-check with plain `notebooklm source list`, which does report the error.

11. **`--reindex`/`--reorder` = rename only**: Never delete sources, never re-create. YouTube sources imported natively are precious (notebooklm-py `source add` for YouTube fails frequently). Only use `notebooklm source rename` to update titles.

12. **Rename immediately after add doesn't stick**: NotebookLM overwrites the
    title when it finishes processing. Always `wait_for_source_with_status()`
    first, then rename — see `add_text_source()`.

## Companion Docs (all tracked in git)

| File | Read it when |
|------|--------------|
| `INDEX_LIST_SPEC.md` | Touching index.list parsing/writing, notebook binding, folder/title standardization, or Curated↔Managed. **Authoritative over this file** on those topics. |
| `NBLM_DUAL_ACCOUNT_SOP_20260610.md` | Switching Google accounts, `nbswitch`/`nbwhich`, quota exhaustion on one account. |
| `USING_COLAB_4WHISPER.md` | Setting up the Colab T4 Gradio endpoint for `--colab-url`. |

Untracked `.md` files in the repo root are session scratch — don't treat them as spec.

`prompt.history` / `response.history` (+ their `.backups/` dirs) are provenance
logs written by the `/ph` and `/logoutput` skills. Append via those skills'
writer scripts; never hand-edit or truncate.

## Troubleshooting

**"API returned no data for URL"**: Video has no transcript on YouTube. Whisper fallback will handle it.

**Whisper too slow**: Use `--without-whisper` to skip, use `--colab-url` for Colab T4 GPU, use `--remote-sshfs` for your own GPU server, or be patient (30+ min for long videos on CPU).

**Error sources accumulating**: Script auto-cleans, but you can manually run:
```bash
notebooklm source list  # Find error sources
notebooklm source delete <id> --yes
```

**Colab connection failed**: Ensure Colab notebook is running with `demo.launch(share=True)`. The URL changes each session.

**Colab timeout**: Default is `0` = no timeout (health-checked every 5s). Set `--colab-timeout 900` if you want a hard cap.

**Colab disconnected mid-transcription**: Local fallback is enabled by default. Use `--no-local-fallback` if you want to exit on Colab failure instead.

**SSHFS mount failed**: The script will automatically fall back to direct SSH method (no mount needed). If SSH also fails, check connection with `ssh user@host`.

**SSHFS/SSH whisper failed**: Ensure `whisper` and `yt-dlp` are installed on remote with CUDA support. Test with:
```bash
ssh user@host "whisper --help"
ssh user@host "yt-dlp --help"
```

**SSHFS/SSH permission denied**: Ensure the remote path is writable. Test with `ssh user@host "touch /genesis/tmp/test && rm /genesis/tmp/test"`.

**Auth expired everywhere / `--update` fails across all folders**: don't reach for
`notebooklm login` first — check whether some folder still holds a live credential.
Compare `__Secure-1PSIDTS` across `~/.notebooklm/` and every `*/.notebooklm/`
(no network call); the newest-mtime value is the live one and everything else is
revoked. If a *local* copy is the live one, promote it to global, then
`--reauth <parent dir>`. Only if nothing is live do you need `notebooklm login`
followed by `--reauth`. Diagnostic script and full procedure: `daily_usage.md`
→ 〈Auth 壞掉〉.

**One folder works, the next says "login" / a notebook looks empty**: the same
rotation, seen from the other side — something (even a read-only `source list`)
ran in another folder and revoked this one. Note `source list --json` returns an
empty `sources` array instead of an error when auth is expired, so an
"empty notebook" is not evidence the notebook is empty; re-run without `--json`
to see the real error. `notebooklm status` reads local context and prints
happily even when revoked — it is not an auth check.

**Wrong notebook got touched**: The binding is `index.list` line 2 + the folder's `.notebooklm/`, not a global setting. Check you were in the right cwd; `--bind-notebook <url>` overwrites line 2 unconditionally.
