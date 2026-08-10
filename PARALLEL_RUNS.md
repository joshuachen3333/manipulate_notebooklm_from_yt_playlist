# 平行跑多個資料夾

**日期**: 2026-08-11
**結論**: 能 —— 每一個都加 `--parallel`。

```bash
# 終端機 1
cd /Users/joshua/work/youtube_list/書本A
manipulate_notebooklm_from_yt_playlist --parallel -r

# 終端機 2（同時）
cd /Users/joshua/work/youtube_list/書本B
manipulate_notebooklm_from_yt_playlist --parallel -r

# 終端機 3、4… 同理
```

---

## 四條規則

### 1. 每一個都要加

漏掉一個就毀掉全部 —— 那一個會輪替 cookie，把其他所有人手上的值變死。
**這不是「加了比較好」，是全有全無。**

### 2. `--update` 不要加

sweep 本來就是循序跑的，那裡的輪替是有益的續命。加了反而讓 session 提早自然過期。

### 3. 同一個資料夾開多個終端機，不需要旗標

那本來就是安全的（共用同一份 auth，靠 `add_source_working.lock` 協調索引）。
要旗標的是**不同資料夾**。

### 4. 跑完之後不用手動收拾

下次 `--update` 開頭的 preflight 會自己判斷哪份是活的、對齊 270 個。

---

## 為什麼需要這個旗標

notebooklm-py 0.4+ 每次呼叫都換發 `__Secure-1PSIDTS`，而換發是**防重放**的 ——
誰最後換，其他所有副本當場作廢。270 個資料夾各持一份副本的架構，跟這個機制天生衝突。

`--parallel` 就是把換發整個關掉（`NOTEBOOKLM_DISABLE_KEEPALIVE_POKE=1`）。

代價是失去 keepalive 續命，session 走自然壽命 —— 也就是回到 0.3.0 時代那個
**一兩個月才要 login** 的行為。

---

## 實測（2026-08-11）

三臂受控實驗，用 `--reindex`（rename-only，不動內容）跑已完成的資料夾：

| 臂 | 設定 | 結果 |
|---|---|---|
| 對照 | 1 個資料夾，輪替開 | 輪替了：`PuLJZbDosEAA` → `q55zavasfEAA` |
| 陰性 | 3 個平行，輪替開 | **分岔**：一個變 `VdquXzRerEAA`，其餘兩份持有死值 |
| 實驗 | 3 個平行，輪替關 | **完全沒變**，所有副本一致 |

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
