# 平行跑多個資料夾

**日期**: 2026-08-11
**結論**: 能，而且**不需要任何旗標** —— cookie 輪替已改為預設關閉。

```bash
# 終端機 1
cd /Users/joshua/work/youtube_list/書本A
manipulate_notebooklm_from_yt_playlist -r

# 終端機 2（同時）
cd /Users/joshua/work/youtube_list/書本B
manipulate_notebooklm_from_yt_playlist -r

# 終端機 3、4… 同理
```

> **沿革**：最初做成 `--parallel` 旗標（必須每個 process 都加，漏一個就全毀）。
> 後來確認輪替對這個 codebase **在任何情況下都是純粹的危害**，於是倒過來設成預設關閉。
> `--parallel` 保留為 no-op，舊指令照樣能跑。

---

## 三條規則

### 1. 不用加任何東西

預設就是安全的。這是刻意的設計 —— **「忘記加旗標」不該是會毀掉 270 個資料夾 auth 的失誤。**

### 2. 同一個資料夾開多個終端機，本來就安全

共用同一份 auth，靠 `add_source_working.lock` 協調索引。跟跨資料夾平行是兩回事。

### 3. 手動下的 `notebooklm` 指令**仍然會輪替**

腳本只能管自己發出的呼叫。你在終端機直接打 `notebooklm list`、`notebooklm source list`
仍然會換發 cookie，把正在跑的 job 弄死。

**跑 job 的時候不要手動下 notebooklm 指令**，唯讀的也不行。

---

## 為什麼輪替對這個專案是純粹的危害

notebooklm-py 0.4+ 每次呼叫都換發 `__Secure-1PSIDTS`，換發是**防重放**的 ——
新值一產生，其餘所有副本當場作廢。

套件自己的模型是「多個 process **共用同一份** `storage_state.json`」（它的跨 process
flock 就是為 `xargs -P` 這種 fan-out 設計的）。而這個腳本的模型正好相反：
**一個 playlist 資料夾一份 `.notebooklm/`，總共約 270 份。** 每輪替一次就孤立 269 份加上 global。

**這在循序執行下同樣成立**，不只是平行。`--update` 每跑完一個資料夾就輪替一次，
其餘全部持有死值 —— sweep 之所以「看起來安全」，只是因為 `resolve_live_auth()` /
`--reauth` 事後收拾。關掉輪替是**消除churn**，而不是修補它。

### 關掉安全嗎

套件的 docstring 講得很清楚：

> Failures are logged at DEBUG and swallowed: **this is purely a freshness optimisation**.
> The caller's request to notebooklm.google.com is the authoritative health check.

輪替**不是功能必需**，關掉不會壞任何東西。唯一的代價是 session 走自然壽命 ——
也就是 0.4 之前那個**一兩個月才要 login** 的行為。

### 什麼情況該把它打開回去

```bash
manipulate_notebooklm_from_yt_playlist --enable-keepalive ...
```

**只有一種情況**：session 開始比以前**更早**過期（0.4 之前是 1–2 個月）。
那才代表保鮮確實有用、值得付出 churn 的代價。

---

## 實測（2026-08-11）

三臂受控實驗，用 `--reindex`（rename-only，不動內容）跑已完成的資料夾：

| 臂 | 設定 | 結果 |
|---|---|---|
| 對照 | 1 個資料夾，輪替開 | 輪替了：`PuLJZbDosEAA` → `q55zavasfEAA` |
| 陰性 | 3 個平行，輪替開 | **分岔**：一個變 `VdquXzRerEAA`，其餘兩份持有死值 |
| 實驗 | 3 個平行，輪替關 | **完全沒變**，所有副本一致 |

改成預設之後又驗了一次：**不帶任何旗標**、兩個資料夾平行、`rc=0`、值完全沒變。

### 最重要的觀察

陰性臂三個都 `rc=0`、當下都沒報錯。**毒是下一次呼叫才發作。**

這就是為什麼這件事一直以「後開的那個叫我 login」的形式出現，而不是以明顯的失敗出現 ——
你看到報錯的時候，肇事的那次執行早就結束了。

### 一個做實驗時踩到的坑

前兩次跑出「沒變化」，差點被當成結論。實際是撞到
`_KEEPALIVE_RATE_LIMIT_SECONDS = 60` 的節流窗口（以 storage 檔的 mtime 計算）——
三臂都在 60 秒內，所以「沒輪替」跟環境變數無關。

**要重現這個實驗，每一臂之間必須等 storage 檔 mtime 年齡 > 60 秒。**

---

## 一個實務上的天花板

平行度別開太大。沒有 YouTube 原生字幕的影片會走 whisper，而 whisper 全部排到
**genesis 那一張 RTX 2060**。開 5 個終端機不會讓轉錄快 5 倍，只會讓 5 個 job
在同一張卡上排隊。

真正能平行加速的是「大多數影片都有原生字幕」的那種資料夾。
**2–3 個並行是甜蜜點**，再多就是 GPU 排隊了。

---

## 相關

- `daily_usage.md` →〈Auth 壞掉〉：副本分岔時怎麼判斷哪份還活著、怎麼修
- `CLAUDE.md` → §5 Auth is self-healing：`resolve_live_auth()` 的方向判斷
- `NBLM_DUAL_ACCOUNT_SOP_20260610.md`：`nbswitch` 切帳號
