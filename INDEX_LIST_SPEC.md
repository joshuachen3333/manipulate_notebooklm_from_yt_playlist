# index.list spec + notebook binding rules

Canonical record of the index.list header format and the rules that govern how the script binds to a notebook and standardizes names. Added 2026-04-17.

## 1. File format

Three header lines (tab-separated after the colon) followed by tab-separated video entries:

```
# playlist:		<playlist_url>
# notebook url:		<notebook_url>
# notebook title:	<notebook_title>
1	<video_url>	"<title>"	<YYYYMMDD>
2	<video_url>	"<title>"
...
```

Separator between key and value is **two tabs** for lines 1-2, **one tab** for line 3 — this aligns the value columns at tab stop 3 (col 24 with 8-char tabs).

- **Line 1** (`# playlist:`) — source YouTube playlist. Used to regenerate entries and to derive folder name on first create.
- **Line 2** (`# notebook url:`) — full NotebookLM URL (`https://notebooklm.google.com/notebook/<uuid>`). Records the current binding.
- **Line 3** (`# notebook title:`) — user-editable source of truth for the notebook title. Also determines the folder name.

Parser is whitespace-tolerant: any amount of tabs/spaces around the `:` is fine. Lines after the last `#` header are video entries.

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
| `classify_setup_arg(arg)`             | `'notebook' | 'playlist' | 'path' | 'unknown'` |
