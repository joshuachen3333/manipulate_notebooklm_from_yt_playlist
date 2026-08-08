# 日常操作手冊

`manipulate_notebooklm_from_yt_playlist` 的常用指令。完整旗標清單看 `CLAUDE.md`，
index.list 格式看 `INDEX_LIST_SPEC.md`。

指令名稱是 `~/.local/bin/manipulate_notebooklm_from_yt_playlist`，
symlink 指向本 repo 的 `manipulate_notebooklm_from_yt_playlist.py`。

---

## 兩條主線

### 1. 新增一條 playlist

在**想要放它的目錄**底下跑（會在該目錄再開一層子資料夾，名字取自 playlist 標題）：

```bash
cd /Users/joshua/work/youtube_list/台語漢字學/陳世明老師
manipulate_notebooklm_from_yt_playlist --auto "https://www.youtube.com/watch?v=LPEuY9zWbdw&list=PLH1v_wCmILkqdy3rVsg5nIgptjbdKVCSa"
```

一發到底：建資料夾 → 複製 auth → 找/建 notebook → 建 index.list（按日期排序）
→ reindex → 上傳全部影片（失敗的走 whisper fallback）→ 試著把 whisper 文字來源
換回原生 YouTube 來源。

> **URL 一定要用引號包起來。** 含 `&` 的網址在 zsh 沒引號會被當成背景指令，
> `&list=...` 整段消失，playlist ID 抓不到。

### 2. 例行更新全部 playlist

在**放所有 playlist 資料夾的母目錄**跑：

```bash
cd /Users/joshua/work/youtube_list
manipulate_notebooklm_from_yt_playlist --update -v
```

掃出每個含 `index.list` 的子資料夾，各自以 `cwd=<該資料夾>` 開 subprocess 跑
`--auto`（每個 1 小時 timeout，完整輸出存在該資料夾的 `update.log`）。
`-v` 是即時串流輸出；不加就只印每個資料夾一行狀態。

已完成的資料夾會顯示 `up to date` 秒過，**中斷後直接重跑即可，不會重做**。

---

## 其他常用

```bash
# 重新登入（auth 過期、或 session 被撤銷時）
notebooklm login

# 登入後把新 auth 推到所有資料夾的 .notebooklm/
manipulate_notebooklm_from_yt_playlist --reauth /Users/joshua/work/youtube_list

# 只跑單一資料夾（除錯用）
manipulate_notebooklm_from_yt_playlist --update -v <資料夾名>

# 在某個 notebook 資料夾裡補一支不屬於來源 playlist 的影片
cd <資料夾> && manipulate_notebooklm_from_yt_playlist --add-video "https://youtu.be/XYZ"

# 手動調整順序後，把雲端來源名稱重新對齊 index.list
cd <資料夾> && manipulate_notebooklm_from_yt_playlist --reindex

# 只產生 index.list，完全不碰雲端 notebook（唯一無副作用的乾跑）
manipulate_notebooklm_from_yt_playlist --list-only "<playlist_url>"

# 清掉已經有 txt 的音檔，省磁碟
manipulate_notebooklm_from_yt_playlist --cleanup /Users/joshua/work/youtube_list
```

---

## 改資料夾／notebook 名稱

`index.list` **第 3 行**是唯一真相來源：

```
# notebook title:	Joshua_陳世明老師
```

改完之後跑一次 `--update`（或該資料夾的 `--auto`），雲端 notebook 會改名，
本機資料夾也會改成 `陳世明老師/`（自動去掉 `Joshua_` 前綴）。

在 NotebookLM 網頁端改名**不會留住** —— 下次跑會被改回第 3 行的值。

⚠️ 若目標名稱的資料夾已存在（例如你先手動建了空的同名資料夾），改名會被跳過並印警告。
先把空資料夾刪掉。

---

## 踩雷筆記

**所有指令都對 cwd 敏感。** 綁定是靠該資料夾的 `.notebooklm/` 加上 `index.list`
第 2 行，不是全域設定。跑錯目錄就會動到錯的 notebook。

**不要手動複製 `storage_state.json`。** notebooklm-py 0.4+ 每次使用都會輪替
`__Secure-1PSIDTS`；把舊快照拿去重放，Google 會**撤銷整個 session**，所有資料夾
一起死，只能重新 `notebooklm login`。auth 的複製交給 `--reauth` 處理。

**不要同時跑不同資料夾的 job。** 每個 job 啟動時把全域 auth 複製一份到自己的
`.notebooklm/`，之後各自輪替 cookie；誰最後輪替，其他人手上那份（含全域那份）
就作廢了。症狀就是：先跑的那個一路跑下去，後開的那個一啟動就叫你 `notebooklm login`。
**同一個資料夾**開多個終端機是安全的（共用同一份 auth，靠 `add_source_working.lock`
協調索引）—— 不安全的是**不同資料夾**並行。

**playlist 標題會被正規化，「台」和「臺」會撞在一起。** 資料夾名與 notebook 名都
走 opencc 簡→繁，所以「台語漢字學」和「臺語漢字學」會落到同一個資料夾、同一本
notebook，兩邊的 `index.list` 互相覆寫。標題只差異體字的兩條 playlist，要手動
改 `index.list` 第 3 行給它們不同的名字。

**sweep 跑到一半 auth 死掉**：腳本會自動重推 global auth 並重試該資料夾一次
（全 sweep 上限 10 次）；若 global 本身已死，連續 3 次失敗後會**中止整個 sweep**
並提示重新登入，不會空轉剩下的兩百多個資料夾。

**雙帳號**：`nbswitch christine` / `nbswitch joshua` 切全域帳號，`nbwhich` 看現況。
**已經綁定的資料夾不會跟著切** —— 綁定時就用 `.account` 標記釘住身份了。

**台語／方言內容**：whisper fallback 走 `--language Chinese` + `繁體中文` initial
prompt，沒有 YouTube 原生字幕的影片轉出來品質可能不理想，跑完值得抽幾支看一下。

---

## 環境版本（2026-08-08）

| 套件 | 版本 | 備註 |
|---|---|---|
| `notebooklm-py` | 0.8.0 | 0.3.0 會因 Google 搬到 `notebook.google.com` 而永遠報 auth expired，**不可退回** |
| `yt-dlp` | 2026.07.04 | |
| genesis whisper | python3.12 + cu124 + RTX 2060 SUPER | SSH/SSHFS fallback 用 |
