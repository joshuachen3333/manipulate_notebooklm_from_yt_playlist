# index.list spec + notebook binding rules

Canonical record of the index.list header format and the rules that govern how the script binds to a notebook and standardizes names. Added 2026-04-17.

## 1. File format

Three header lines (tab-separated after the colon) followed by tab-separated video entries:

```
# playlist:		<playlist_url>
# notebook url:		<notebook_url>
# notebook title:	<notebook_title>
1	<video_url>	"<title>"                                                                                           	       	t:1516992468
2	<video_url>	"<title>"                                                                                           	extra  	
3	<video_url>	"<title>"
...
```

Separator between header key and value is **two tabs** for lines 1–2, **one tab** for line 3.

- **Line 1** (`# playlist:`) — source YouTube playlist. Used to regenerate entries and to derive folder name on first create. **Empty value (`# playlist:\t\t` with nothing after the tabs) signals Curated mode** — see §11 below.
- **Line 2** (`# notebook url:`) — full NotebookLM URL (`https://notebooklm.google.com/notebook/<uuid>`). Records the current binding.
- **Line 3** (`# notebook title:`) — user-editable source of truth for the notebook title. Also determines the folder name.

Parser is whitespace-tolerant: any amount of tabs/spaces around the `:` is fine. Lines after the last `#` header are video entries.

### Data-row schema (line 4 onward) — 5 columns

| # | Column | Width | Meaning |
|---|--------|-------|---------|
| 1 | `index` | — | Row number. Parsed as `float` to support **fractional reordering** (`0.5`, `0.51`, `-1` for "definitely first"). `--reindex` sorts by this float and renumbers back to clean sequential integers. |
| 2 | `url` | — | YouTube video URL. |
| 3 | `title` | padded to `INDEX_TITLE_WIDTH = 100` chars (incl. quotes) | Traditional-Chinese title. Parser rstrips before stripping quotes — width is purely visual. |
| 4 | `source` | padded to `INDEX_SOURCE_WIDTH = 7` chars | Empty = from the source playlist. `extra` = manually added via `--add-video`. Future markers may use `extra:<tag>` form. |
| 5 | `sort_date` | — | `YYYYMMDD` or `t:<unix_epoch_seconds>` or empty. Historical metadata only — not used as sort key by `--reindex`. |

**Short 3-column form** (`idx\turl\t"title"`) is accepted for rows that have neither a source marker nor a sort_date. The writer only emits short rows when columns 4 and 5 are both empty; otherwise the full padded 5-column form is written.

**Legacy 4-column tolerance:** pre-schema-v2 files had `sort_date` in column 4 (no `source` column). The parser detects this (value matches `t:\d+` or exactly 8 digits) and treats it as `sort_date` with empty `source`. The next `--reindex` / `--update` pass rewrites the file in the new 5-column layout.

### Manual reordering via fractional indices

To move a row to a different position, edit its index (column 1) to any float that sorts where you want it, save, and run `--reindex` (or let the next `--update` sweep pick it up). The index column accepts negative numbers (for "always first"), leading zeros (`0000.5` parses as `0.5`), and arbitrary precision (`0.51`, `0.511`, …).

After `--reindex`:
- Rows are sorted by the float index (stable — file order is the tiebreaker).
- Each row is renumbered to a clean sequential integer starting at 1.
- `index.list` is rewritten with the new integers — fractions are consumed.
- Every notebook source that matches a row (by URL, `#URL` fulltext header, or title) is renamed to `[NNN] <title>` to match the new order.
- Tracking files (`add_source_ok.txt`, `add_source_video2txt.txt`) are re-synced with the new indices.

## 2. Priority order for notebook title

1. **Line 3** of index.list — user-edited value **always wins**.
2. **`Joshua_<playlist_title>`** — the default standardized form, used when line 3 is missing.
3. **Cloud / web-UI notebook title** — lowest priority; gets overwritten to match the winner.

On every bind / standardize, if line 3 is missing, it's seeded with `Joshua_<playlist_title>` (fetched via `yt-dlp`).

**Web-UI renames don't persist.** If you rename the notebook in the NotebookLM web UI, the next `--setup` / `--auto` / `--update` run renames it back to match line 3. To change the notebook's name permanently, edit line 3.

## 3. Folder name rule

Folder name = `derive_folder_name(line 3)` =

1. Strip leading `Joshua_` / `Joshua ` / `Joshua` prefix.
2. Run `sanitize_folder_name()` (replaces spaces and shell-special chars with `_`, collapses and trims `_`).

Examples:
| Line 3                                    | Folder                      |
|-------------------------------------------|-----------------------------|
| `Joshua_Education Series`                 | `Education_Series`          |
| `Joshua_Algorithm Trading Education`      | `Algorithm_Trading_Education` |
| `Algorithm Trading` (no prefix)           | `Algorithm_Trading`         |
| `Joshua ABC 《XYZ》`                       | `ABC_《XYZ》`                |

**Folder never carries the `Joshua_` prefix** — even though the notebook title does.

When standardize runs, if the current folder name ≠ derived target, the folder is renamed on disk via `os.rename` + `chdir`. If the target path already exists the rename is skipped (safe no-op, warning printed).

## 4. When the rules are enforced

| Entry point                                   | Standardize? | Line 2 written | Line 3 written |
|-----------------------------------------------|--------------|----------------|----------------|
| `--setup <playlist>` (find/create)            | yes          | from `find_or_create_notebook` UUID | `Joshua_<playlist_title>` |
| `--setup <nb_url> <playlist>` (bind new)      | yes          | from CLI nb_url | `Joshua_<playlist_title>` |
| `--setup <nb_url> [path]` (bind existing)     | yes          | from CLI nb_url | existing line 3, else `Joshua_<playlist_title>` |
| `--notebook-url <url>` (standalone)           | yes          | from CLI nb_url | same as above |
| `--auto <playlist>` (incl. `--update` subprocess) | yes      | from bound nb_id | existing line 3, else `Joshua_<playlist_title>` |
| `-r`, `--reindex` (legacy folder)             | no           | backfill from current binding (if missing) | backfill from cloud title (if missing) |

"Standardize" here means: enforce line 3 on the cloud notebook (rename if different) **and** enforce the derived folder name on disk.

The `-r` / `--reindex` path deliberately **doesn't standardize** — it only backfills missing headers. This keeps these modes fast (no `yt-dlp` call for playlist title) and non-disruptive (no notebook / folder renames). To force a full standardization on a legacy folder, run `--setup <nb_url>` standalone or any `--auto` / `--update` pass.

## 5. Line-2 rebind behavior

Any `--setup <nb_url>` / `--notebook-url <nb_url>` invocation **overwrites line 2** with the CLI-supplied URL unconditionally. This is treated as an explicit rebind — the CLI always wins. If you typed the wrong URL, you effectively switched notebooks; edit line 2 or re-run with the correct URL to fix.

## 6. Preservation across regeneration

Every rewrite of `index.list` (new videos detected, re-sorted, re-imported) reads the current metadata and re-emits lines 2 and 3 unchanged. This is implemented by having `write_index_list()` accept `notebook_url` and `notebook_title` as optional overrides — when either is `None`, the existing value in the file is preserved.

Manual edits to line 3 survive all automated rewrites. That's the guarantee.

## 7. `--update` in-place mode

Custom folder names (from line-3 edits) would conflict with the old `run_update` behavior of `cwd=folder_path.parent` + `--auto <url>` creating a fresh `sanitize_folder_name(title)` subfolder. Fix:

- `run_update` now launches each subprocess with `cwd=<folder_path>` (inside the folder itself).
- `auto_setup` detects "in-place" mode — if cwd already has an `index.list` whose playlist ID matches the given url, it skips folder creation and `chdir` entirely.

This means custom-named folders survive indefinite `--update` runs.

## 8. Minimal edit flow to rename a notebook

1. Open the folder's `index.list`.
2. Change line 3 — e.g., `# notebook title:	Joshua_Algorithm Trading Education`.
3. Run one of:
   - `--setup <nb_url>` from inside the folder (rebinds + standardizes)
   - `--update` from the parent directory
   - `--auto <playlist_url>` from inside the folder
4. Cloud notebook title gets renamed, folder name gets renamed to `Algorithm_Trading_Education`.

`-r` alone will not trigger the rename (by design — see §4).

## 9. Edge cases

- **Line 3 without `Joshua_` prefix** (e.g., `CustomName`): notebook renamed to exactly `CustomName`; folder renamed to `CustomName` (sanitized).
- **Rename target folder already exists**: on-disk rename is skipped with a warning; cloud rename still proceeds.
- **No notebook selected when `backfill_index_metadata` runs**: backfill becomes a no-op; lines 2-3 remain missing until next bind.
- **`update_index_metadata` on a file without `# playlist:` line 1**: line 1 is dropped (current behavior; shouldn't happen in this project since all index.list files start with line 1).

## 10. Related code

| Function                              | Role                                           |
|---------------------------------------|------------------------------------------------|
| `read_index_metadata(idx)`            | Parse lines 1-3 from index.list                |
| `write_index_list(..., nb_url, nb_title)` | Write full file; preserve metadata when `None` |
| `update_index_metadata(idx, ...)`     | Rewrite header only, preserve video entries    |
| `derive_folder_name(title)`           | Strip `Joshua_` + sanitize → folder name       |
| `build_notebook_url(nb_id)`           | UUID → full NotebookLM URL                     |
| `standardize_folder_and_notebook(playlist_title, idx)` | Seed lines 2/3 if missing; rename cloud + folder |
| `backfill_index_metadata(idx)`        | Append missing lines 2/3 for legacy files (no rename) |
| `extract_notebook_id(url_or_uuid)`    | Accept URL or bare UUID → UUID                 |
| `classify_setup_arg(arg)`             | `'notebook' \| 'playlist' \| 'video' \| 'path' \| 'name' \| 'unknown'` |
| `new_notebook_setup(name, seed_url)`  | Bootstrap a Curated notebook (§11) |

## 11. Curated vs Managed notebooks

Added 2026-04-18 with the `--new-notebook` / `--attach-playlist` commands.

A notebook is either:

| Mode | Line 1 (`# playlist:`) | Created via | Typical source |
|------|------------------------|-------------|----------------|
| **Managed** | non-empty URL | `--setup`, `--auto` | YouTube source playlist; `--update` re-scans the playlist for new videos |
| **Curated** | empty | `--new-notebook` | Hand-curated theme collection; videos added one-by-one via `--add-video`; `--update` does a *light* pass (reindex + sync tracking only, no playlist re-scan) |

### Bootstrap a Curated notebook

```
# Empty notebook, named manually
manipulate_notebooklm_from_yt_playlist --new-notebook "日內交易直播"

# Seeded with one video; name auto-derives from the video title
manipulate_notebooklm_from_yt_playlist --new-notebook "https://youtu.be/abc123"

# Both, in any order (comma/space tolerant)
manipulate_notebooklm_from_yt_playlist --new-notebook "日內交易直播" "https://youtu.be/abc123"
```

Folder is **always** created in cwd. Run from the directory where you want the notebook to live.

### Grow a Curated notebook

Every addition after bootstrap uses `--add-video` (which already supports the `source='extra'` marker):

```
cd 日內交易直播
manipulate_notebooklm_from_yt_playlist --add-video "https://youtu.be/XYZ"
```

### Promote Curated → Managed

If you later discover a YouTube playlist you want to bulk-import into the same notebook:

```
cd 日內交易直播
manipulate_notebooklm_from_yt_playlist --attach-playlist "https://youtube.com/playlist?list=PLxxx"
# Then bulk-import:
manipulate_notebooklm_from_yt_playlist --auto "https://youtube.com/playlist?list=PLxxx"
```

`--attach-playlist` only writes line 1; the `--auto` run fills in the new rows. Existing `source='extra'` rows are preserved.

### Behavioral differences

- **`--update`** scans all folders with `index.list` regardless of mode. Managed folders get the full `--auto` treatment (re-scan playlist, add new videos). Curated folders get `--reindex` only (apply any fractional-index reordering the user did).
- **`_match_sources_by_title`** skips the playlist-title fetch when line 1 is empty; relies solely on URL-equality and `#URL` fulltext matching.
- **`find_playlist_folders`** returns Curated folders too (url = None for those), so `--update` discovers them.

### One-way contract

Line 1 is the "sync contract." Once you promote a folder from Curated to Managed via `--attach-playlist`, you can't trivially go back without manually editing `index.list`. The tool doesn't offer `--detach-playlist` — removing the sync source is rare and should be a conscious manual act.
