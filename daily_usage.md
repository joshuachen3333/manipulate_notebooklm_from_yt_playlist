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

# 把本機逐字稿 + index.list 改成臺灣標準字形。純本機，會先列清單問你才寫
manipulate_notebooklm_from_yt_playlist --normalize-tw /path/to/dir
```

---

## 保護手校過的逐字稿（台語漢字學）

預設流程對手校版是**有敵意的**：每次上傳結束都會跑 text-back-to-video，
把文字來源換成 YouTube 原生匯入 —— 而原生字幕是 ASR 產的，會直接蓋掉校正成果。

在該資料夾放一個空的 `.keep_transcripts` 就整個關掉：

```bash
cd <資料夾> && touch .keep_transcripts
```

要取消保護就把檔案刪掉，沒有覆寫旗標（刻意的）。

這個標記只擋「雲端蓋掉本機」。**把校正推上去是另外兩個指令，永遠要手動下**
（`--auto` / `--update` 碰不到它們，270 個資料夾的 sweep 絕不該動雲端來源）：

```bash
cd <資料夾>

# 雲端是文字來源、但內容已經和本機 txt 不一樣 → 推上去
manipulate_notebooklm_from_yt_playlist --resync-text

# 雲端是 YouTube 原生來源 → 用本機校正版取代它
manipulate_notebooklm_from_yt_playlist --text-over-video
```

兩者都只動「本機有對應 `#URL` 逐字稿」的項目；`--text-over-video` 另外會把
內文不到 200 字的檔案當成只有標題的殘檔擋下來，不會拿它去覆蓋能用的來源。

**每支影片的轉錄引導句**可以用 `.whisper_prompt` 逐資料夾覆寫（台語漢字學兩個
資料夾已經放了）。寫短一點 —— whisper 的 prompt 上限是 224 tokens，超過會默默
吃掉音訊上下文。

引導句**每個 30 秒窗口都會重新餵一次**（靠 `--carry_initial_prompt True`；沒有
這個旗標的話只有開頭那一窗有效，後面會整段掉回簡體）。所以放進去的專業術語是
**真的會影響 ASR 的** —— 台語漢字學就是在術語列進去之前，把「聲母／韻母」聽成
「生母／孕母」。相對地，改完引導句要抽下一支看看有沒有 prompt 裡的詞出現在
音檔沒講的地方。

⚠️ **全域預設那句一定要中性**（「以下是這段影片的逐字稿，以臺灣正體中文書寫。」），
因為所有 270 個資料夾都吃它 —— 包含 MIT、哈佛、趙啟超線性代數那些。whisper 會把
prompt 裡的詞彙吐進聽不清楚的段落，所以全域那句放任何學科名詞，都會在不相干的
頻道變成幻覺內容。學科用語只能放進個別資料夾的 `.whisper_prompt`。

---

## Auth 壞掉：先判斷「哪一份還活著」，再決定怎麼救

### 為什麼會壞

notebooklm-py 0.4+ 每次跟 Google 說話都會輪替 `__Secure-1PSIDTS`。輪替之後，
**所有其他副本（含 global）當場作廢** —— Google 的防重放機制會拒絕舊值。

關鍵是：**唯讀指令也算數。** `notebooklm source list`、`source fulltext`、
`notebooklm list` 全都會輪替。不是只有上傳才危險，在某個資料夾底下「看一下有
哪些來源」就足以把其他兩百多個資料夾的 auth 全部弄死。

典型症狀：某個資料夾好好的，隔壁資料夾一啟動就叫你 `notebooklm login`。

> 額外陷阱：`notebooklm source list --json` 在 auth 過期時會回**空的 sources
> 陣列**而不是報錯，看起來像「這本 notebook 是空的」。不加 `--json` 跑一次才
> 會看到真正的錯誤訊息。`notebooklm status` 讀的是本機 context，過期也照印，
> 不能拿來當 auth 健康檢查。

### 診斷：比對 `__Secure-1PSIDTS`

在放 playlist 的母目錄跑，不會發出任何網路請求：

```bash
python3 - <<'EOF'
import json, glob, pathlib
paths = [pathlib.Path.home() / ".notebooklm/profiles/default/storage_state.json"]
paths += [pathlib.Path(p) for p in glob.glob("**/.notebooklm/profiles/default/storage_state.json", recursive=True)]
rows = []
for p in paths:
    try:
        d = json.loads(p.read_text())
    except Exception:
        continue
    v = next((c["value"] for c in d.get("cookies", []) if c["name"] == "__Secure-1PSIDTS"), "<none>")
    rows.append((str(p).replace(str(pathlib.Path.home()), "~"), v, p.stat().st_mtime))
newest = max(r[2] for r in rows)
live = {r[1] for r in rows if r[2] == newest}
for path, v, _ in sorted(rows, key=lambda r: -r[2]):
    print(f"{'CURRENT' if v in live else 'STALE  '}  ...{v[-12:]}  {path}")
EOF
```

輸出長這樣（2026-08-08 實際案例）：

```
CURRENT  ...LJJaNILqsxAA  臺語漢字學/.notebooklm/...      ← 最後被用到的
STALE    ...yQTPzAllOBAA  ~/.notebooklm/...
STALE    ...yQTPzAllOBAA  台語漢字學短篇/.notebooklm/...
```

**最新 mtime 的那份就是 Google 目前接受的那份**，其餘一律作廢。

### 修復 A：把還活著的那份提升回 global（不用開瀏覽器）

`--reauth` 的方向是 global → 各資料夾。如果作廢的剛好是 global，直接 `--reauth`
只會把死的推下去、全部一起死。要先把活的那份補回 global：

```bash
# 先確定沒有 job 在跑
ps aux | grep manipulate_notebooklm | grep -v grep

cp ~/.notebooklm/profiles/default/storage_state.json{,.bak}
cp <CURRENT那份的路徑> ~/.notebooklm/profiles/default/storage_state.json
manipulate_notebooklm_from_yt_playlist --reauth .
```

這跟「不要手動複製 storage_state.json」那條**不衝突** —— 那條講的是在 session
活著的時候複製**舊快照**去重放。這裡沒有 job 在跑，而且複製的是 Google 唯一
接受的那份，方向相反。失敗也不會比現在更糟。

**2026-08-08 實測有效**，省掉一次瀏覽器登入。

### 為什麼 8 月開始特別常壞

不是過期變快，是**換了死法**。0.3.0 不輪替 cookie，270 份副本可以並存，只有
自然壽命（1–2 個月）會到期。0.8.0 每次呼叫都輪替 `__Secure-1PSIDTS`，而輪替
帶防重放 —— 任一份被用過，其餘全部**被撤銷**。症狀一樣，成因完全不同。

現在腳本會自動走 notebooklm-py 的 L3 headless re-auth：從常駐瀏覽器 profile
免人工重新取得 cookie。`NOTEBOOKLM_HEADLESS_REAUTH=1` 由腳本自己設（不寫進
`~/.zshrc` —— 你手動下指令時人就在旁邊，不需要無人值守復原），profile 則靠
symlink 從 `~/.notebooklm/browser_profile` 共用到每個資料夾。

⚠️ **profile 自己也會腐化。** Christine 那份在 2026-06-10 雙帳號遷移時被留在
`~/.notebooklm.backup.20260610/`，等到 8 月接回來時裡面的 Google session 已經
死了 —— 放了三個月沒人發現，因為 0.3.0 時代根本用不到它。

`notebooklm login` 會同時重灌 profile 和 storage_state，所以這條自癒路徑的新鮮度
等於你上次登入的時間。想檢查（純本機，不開瀏覽器、不碰 cookie）：

```bash
python3 -c "
from notebooklm._auth.headless_reauth import headless_reauth_readiness
print(headless_reauth_readiness().detail)"
```

注意它只驗證「條件齊了」，**刻意不聲稱 session 還活著** —— 只有真的驅動瀏覽器
才知道。

### 修復 B：A 失敗就走正規路

```bash
notebooklm login
manipulate_notebooklm_from_yt_playlist --reauth /Users/joshua/work/youtube_list
```

### 預防

**`--update` 和 `--auto` 現在開頭會自動做這件事**（2026-08-10 起）：比對所有副本、
必要時把活的那份提升回 global，然後才 `--reauth` 往下推。上面那套手動流程現在
只在自動判斷失敗、或你想先看清楚狀況時才需要。

`--update` 的 270 個子程序不會各自重跑這個檢查（靠 `NBLM_SWEEP_CHILD` 環境變數
擋掉）—— 否則它們會在彼此輪替 cookie 的同時各自判斷「誰是活的」。

還是要守的一條：**不要在 sweep 跑的時候去別的資料夾下唯讀指令**查東西 ——
那會當場把正在跑的那個弄死，而且 preflight 只在開頭跑，救不了跑到一半的你。

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
一起死。auth 的複製交給 `--reauth` 處理。唯一的例外（把還活著的那份提升回 global）
見上面〈Auth 壞掉〉。

**不要同時跑不同資料夾的 job，唯讀指令也算。** 每個 job 啟動時把全域 auth 複製
一份到自己的 `.notebooklm/`，之後各自輪替 cookie；誰最後輪替，其他人手上那份
（含全域那份）就作廢了。症狀就是：先跑的那個一路跑下去，後開的那個一啟動就叫你
`notebooklm login`。**連 `source list` / `source fulltext` 這種唯讀指令都會輪替**
—— 在別的資料夾「看一下」就足以弄死正在跑的那個。
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

**台語／方言內容**：whisper fallback 走 `--language Chinese` + 一整句正體中文的
initial prompt（可用 `.whisper_prompt` 逐資料夾覆寫）。沒有 YouTube 原生字幕的
影片轉出來品質可能不理想，跑完值得抽幾支看一下。

**Colab 路徑沒有 prompt 控制。** Gradio 端點只吃一個音訊參數，所以 `--colab-url`
轉出來的稿子完全靠 opencc 事後轉換 —— 而 opencc 對「一簡對多繁」（发→發/髮、
干→乾/幹/干）是用詞頻**猜**的，猜錯事後看不出來。在意字形就走 genesis。

---

## 環境版本（2026-08-08）

| 套件 | 版本 | 備註 |
|---|---|---|
| `notebooklm-py` | 0.8.0 | 0.3.0 會因 Google 搬到 `notebook.google.com` 而永遠報 auth expired，**不可退回** |
| `yt-dlp` | 2026.07.04 | |
| genesis whisper | python3.12 + cu124 + RTX 2060 SUPER | SSH/SSHFS fallback 用 |
