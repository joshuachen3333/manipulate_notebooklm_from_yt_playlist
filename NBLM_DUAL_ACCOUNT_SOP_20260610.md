# NotebookLM 雙帳號切換 SOP

**日期**: 2026-06-10
**作者**: manipulate_notebooklm_from_yt_playlist-obe (Claude)
**情境**: Christine 帳號撞 NotebookLM 每日 chat quota；要在 Christine ↔ Joshua (joysons3) 兩個 Google 帳號間自由切換，不每次都麻煩 Christine 重新授權

---

## 完工狀態

**主架構 ✓ 完工** — symlink + nbswitch + nbwhich + Christine auth 都齊了。

**還缺一塊** — Joshua (joysons3) 帳號自己的儲存還沒建。要靠你一次手動 login 才能填上。

### 已完成的檔案結構

```
~/.notebooklm                  → symlink → ~/.notebooklm-christine  (現在 active)
~/.notebooklm-christine/       (Christine auth，hash 對得上原始)
~/.notebooklm.backup.20260610/ (原 ~/.notebooklm 的 safety archive)
~/.notebooklm-joshua/          (待建立 — 等你完成 joysons3 login)
```

### 已新增的 shell function (在 ~/.zshrc)

- **`nbswitch <name>`** — atomic symlink 替換；目標目錄不存在會自動 mkdir
- **`nbwhich`** — 顯示當前 active + 可用 identities + 當前 notebook

---

## 你現在的 SOP (按順序，~5 分鐘)

### 步驟 1：建立 Joshua 帳號的儲存（**只需做一次**）

```bash
nbswitch joshua         # 自動 mkdir ~/.notebooklm-joshua/ 並切過去 (status 會顯示 no auth — 正常)
notebooklm login        # 開 browser，用 joysons3@gmail.com (你的 Pro 帳號) 登入
```

第一個指令會看到「`created empty /Users/joshua/.notebooklm-joshua — run 'notebooklm login' after switch to populate`」訊息，是正常的。

第二個指令會彈瀏覽器，你完成 OAuth 流程即可。`storage_state.json` + `browser_profile/` 會落到 `~/.notebooklm-joshua/`。

### 步驟 2：處理 `book1_dream_v0_5vid` 分享問題

> youtuber_strategies-obe 在等這個答案

到 NotebookLM 網頁端，用 Christine 帳號登入，打開 `book1_dream_v0_5vid` notebook（UUID `bc1973b3-...`），找 share 按鈕，加入 `joysons3@gmail.com`。

可能結果：

- **成功** → joysons3 看得到同一本 notebook（NotebookLM 支援 cross-account share 的話）→ 對家 obe 改 wrapper 後可雙帳號輪流跑同一本
- **失敗** → joysons3 看不到 → 需要在 joysons3 那邊重新建 notebook 並 ingest 297 sources（~50 分鐘）

### 步驟 3：把 step 1+2 的結果報告對家 obe

```bash
nbwhich              # 確認當前是 joshua (可選驗證)
nbswitch christine   # 切回 Christine 確認也能切回
```

然後跟我說「Joshua login 完成，share 結果是 ✓/✗」— 我會幫你 inject [STATUS] 給 youtuber_strategies-obe，他就會啟動他的 wrapper / chunked / watchdog 三支改造（加 `--storage` flag passthrough）。

或你直接到 youtuber_strategies 那個 tab 跟對家 obe 講也行。

### 步驟 4：撞牆時就切換

```bash
# Christine 撞每日 quota → 切到 Joshua 繼續
nbswitch joshua
notebooklm ask "..."

# 想用 Christine 的 notebook → 切回去
nbswitch christine
```

---

## 流程圖

```
你現在 (Christine 撞牆)
   │
   ▼
[Step 1] nbswitch joshua + notebooklm login
   │   ⇒ ~/.notebooklm-joshua/ 填上 joysons3 auth
   ▼
[Step 2] 網頁 share book1_dream 給 joysons3 (試試看)
   │   ⇒ 成功/失敗任一結果都 OK，只是後續路徑不同
   ▼
[Step 3] 報告對家 obe 兩件事的結果
   │   ⇒ 對家 obe 動工改 wrapper
   ▼
[Step 4] 日常 nbswitch joshua / christine 自由切
```

---

## 風險提醒

- **Christine cookies 過期前**（~2-4 週）切回去都不用她幫忙。過期就還是要她開手機一次，但只是「填新 `storage_state.json`」而已，nbswitch 機制本身不需要改。
- **`nbswitch` 切換時別同時跑多個 `notebooklm` 指令** — symlink 替換是 atomic，但 process 拿到的可能是替換前後的不同 storage。手動切沒問題；wrapper 自動化要避免。
- **Project local `.notebooklm/`**（例如 `youtuber_strategies/notebooklm/book1_dream/.notebooklm/`）已綁定當初 setup 時的身份，不受全域 `nbswitch` 影響。要切某 project 的身份需另外處理。

---

## 對家 obe 分工約定（main-obe ↔ youtuber_strategies-obe）

採 **(C) hybrid** 分工，兩條獨立、不衝突：

| 由 | 做什麼 | 狀態 |
|---|---|---|
| **main-obe**（這隻） | nbswitch symlink 切換機制 + `~/.zshrc` 兩個 function | ✓ DONE |
| **youtuber_strategies-obe** | 在 wrapper / chunked / watchdog 三支加 `--storage` flag passthrough，default 跟 `NOTEBOOKLM_STORAGE` env var | ⏳ block on Joshua login + share 結果 |

兩條的契約：
- youtuber_strategies-obe 的 wrapper 顯式 `--storage ~/.notebooklm-X/storage_state.json` 時，繞過 symlink 走 absolute path，與 nbswitch 並存
- 不帶 `--storage` 時透明跟著 symlink (`~/.notebooklm/`) → 跟他 `NOTEBOOKLM_STORAGE` env var 的 default 對齊就好
- `~/.notebooklm-christine/` 同時是 `nbswitch christine` 的目標 + `--storage ~/.notebooklm-christine/storage_state.json` 的 path，命名一致

---

## 副檔/工具索引

- 原始實作落地：`~/.zshrc` lines 52-101 (nbswitch + nbwhich)
- Christine 備份做法：`cp -R ~/.notebooklm ~/.notebooklm-christine`（由 youtuber_strategies-obe 在 2026-06-10 00:28 執行）
- Symlink 建立：`ln -s ~/.notebooklm-christine ~/.notebooklm`（main-obe 同日 01:08）
- 驗證指令：`notebooklm status` / `notebooklm list --json` / `nbwhich`
