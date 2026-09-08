# 心情點唱機

把 YouTube 帳號裡的所有音樂用 AI 打上標籤（語言／心情／曲風／情境／年代），
之後在手機上點幾個標籤就能立刻產出一份臨時歌單開始播。

解決的問題：YouTube 只有「播放清單」一種分類方式，沒有曲風／年代／心情的維度，
所以想聽特定調性的音樂只能手動翻。

這是個人自用工具，不是套裝軟體 —— 要跑起來需要自己申請 Google OAuth 憑證。
歡迎 fork 改成自己的。

> 私人資訊（自己的 Artifact 網址、Sheet 網址）建議寫在 `LOCAL.md`，
> 該檔已在 `.gitignore` 裡。

---

## 運作方式

分兩階段，因為執行頻率和裝置都不同：

| | 在哪 | 何時 | 需要授權？ |
|---|---|---|---|
| **標記** `sync` | Mac | 有新增歌曲才跑 | YouTube 唯讀 + Anthropic API |
| **聽歌** 手機網頁 | 手機 | 隨時 | 不需要 |

手機端不需要後端或憑證：標籤資料在 `build` 時直接內嵌進網頁，播放則透過
YouTube 自己的 `watch_videos` 臨時歌單機制（不消耗 API 配額、不需登入）。

臨時歌單會落在 YouTube app 而不是 YouTube Music —— 這是 YouTube 自己的行為，
無法從網頁端改變（Artifact 的 CSP 禁止跨網域請求，拿不到產生出來的 TLGG 清單 ID）。
Premium 下 YouTube app 本身就能背景播放；聽到喜歡的組合按「儲存」就會變成
常駐歌單，那份歌單在 YouTube Music 裡就看得到。

### 為什麼用官方 API，不用 ytmusicapi

實測結果：官方 Data API 讀得到帳號的全部播放清單，
而且 `playlistItems.list(playlistId="LM")` 意外可用（官方文件未記載）——
但實測該帳號的 **LM 完全是 LL（喜歡的影片）的子集**，也就是 LM 只是 YouTube 讚裡
被歸類為音樂的那部分，不是獨立媒體庫。所以讀 `LL` + 所有播放清單就已涵蓋，
不需要 `ytmusicapi`。

> 你的帳號可能不同 —— 跑一次 `sync` 後用 `stats` 比對 YouTube Music app 裡
> 「喜歡的音樂」的數量，就知道有沒有缺口。

這也讓授權能維持在官方、唯讀、可單獨撤銷的 OAuth token；
`ytmusicapi` 的瀏覽器 headers 模式要存的是等同整個 Google 帳號的工作階段 cookie，
本專案刻意不採用。

---

## 一次性設定

### 1. 安裝套件

```bash
pip install -r requirements.txt
```

### 2. YouTube 授權（唯讀）

1. 到 https://console.cloud.google.com 建立或選擇專案
2. 啟用「**YouTube Data API v3**」
3. 「憑證」→「建立憑證」→「OAuth 用戶端 ID」→ **桌面應用程式**
   - 選桌面應用程式是因為它允許 loopback 轉址且比對時忽略 port，
     不用登記任何 redirect URI。網頁應用程式會逐字比對，反而更麻煩。
4. 下載 JSON，改名為 `client_secret.json` 放在此資料夾
5. 「OAuth 同意畫面」→「測試使用者」→ 加入**你聽音樂那個 Google 帳號**

scope 只要 `youtube.readonly` —— 連寫入權限都不給。

> 私人帳號建立的專案只能用「外部 + 測試中」，此模式下 refresh token 7 天過期，
> 也就是隔一段時間跑 `sync` 要重新授權一次（瀏覽器點兩下）。因為 `sync` 本來就
> 不常跑，通常可以接受。想免掉可以把應用程式發布到正式版，代價是授權時會出現
> 「未經 Google 驗證」的警告畫面。

### 3. Anthropic API key（可選）

**只有想讓 `sync` 自動標記新歌時才需要。** 也可以完全不用 API key，
改由 Claude Code 直接標記（見下方「沒有 API key 的標記方式」）。

到 https://console.anthropic.com 取得，然後：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

這跟 Claude Code 訂閱是分開計費的。首次標記約 700 首歌的成本大約 4 美元
（`claude-opus-5`、medium effort），之後 `sync` 只標記新歌，幾乎不再花錢。

---

## 使用

```bash
python3 music_tool.py sync     # 抓媒體庫 + 標記新歌
python3 music_tool.py build    # 產出 mood.html
python3 music_tool.py stats    # 看標籤分佈
python3 music_tool.py list -f 中文 放鬆   # 終端機預覽篩選結果
python3 music_tool.py edit 周杰倫 +睡前 -派對   # 手動調整標籤
python3 music_tool.py sheet-init               # 改用 Google Sheet 當共用資料庫
```

`build` / `stats` / `list` 支援 `--offline`（用本地快取，不讀 Sheet）。

### 自定義標籤

**改既有標籤** —— `edit` 依歌名或頻道關鍵字批次調整：

```bash
python3 music_tool.py edit 周杰倫              # 只列出，看現有標籤
python3 music_tool.py edit 周杰倫 +睡前 -派對    # 套用（會先要你確認）
python3 music_tool.py edit "" --id dQw4w9WgXcQ +嗨歌   # 用 videoId 精準指定
python3 music_tool.py edit 小安 +悲傷 -y        # -y 跳過確認
```

未知標籤會被擋下並列出可用清單。改完語言／年代數量不對 1 個時會警告但不阻止。

**新增自己的標籤** —— 編輯 `custom_tags.json`：

```json
{ "自訂": ["雨天", "健身房", "加班"] }
```

分類名稱隨你取，會直接變成網頁上新的一排 chips。沒有任何歌曲用到的標籤
`build` 時會自動略過，不會出現一排永遠是 0 的選項。

指派方式同上用 `edit`。改完記得 `build` 再請 Claude 重新發布。

### 用 Google Sheets 當共用資料庫

啟用後 **Google Sheet 就是唯一真相**，本地 `song_tags.json` 降級為純快取
（只會被 Sheet 覆寫，永遠不會回寫）。這樣手機、電腦、腳本都改同一份資料，
不會有「哪邊比較新」的問題。

**一次性設定**

1. 到 https://console.cloud.google.com/apis/library/sheets.googleapis.com
   選同一個專案 →「啟用」
2. ```bash
   python3 music_tool.py sheet-init
   ```
   會建立試算表、把現有曲目搬上去、並把 ID 記在 `sheet.json`

Sheets 用獨立的 `token_sheets.pickle`，所以 YouTube 那份維持
`youtube.readonly` 不受影響，也不用重新授權 YouTube。

**關於權限範圍**

Google 的 scope **沒有「可寫但不可刪」這個選項** —— 讀寫權限本來就包含
清空儲存格、刪列、刪工作表。實際能限制破壞範圍的是這三層：

| 保護 | 效果 |
|---|---|
| 用 `drive.file` 而非 `spreadsheets` | 只能碰**本程式建立的**那一份，不是你 Drive 裡所有試算表 |
| 不索取 `drive` scope | **無法刪除檔案本身** —— 刪檔需要 Drive 權限，本程式從不索取 |
| 程式內的資料腰斬守門 | 任何讓資料量少於一半的覆寫都會被擋下（見下方） |

代價：`drive.file` 之下**無法用 `--id` 接管一份你自己手動建的試算表**（那不是本程式建立的）。
若真的需要，設環境變數放寬並重新授權：

```bash
export MUSIC_TOOL_SHEET_SCOPE=spreadsheets
rm token_sheets.pickle
```

**最後的防線是 Sheets 自己的版本紀錄**（檔案 →「版本紀錄」），任何誤刪都能還原
—— 這比任何 scope 設定都可靠。

**專案怎麼知道是哪一份 Sheet**

它不會搜尋你的 Drive，只記住一個 ID。那個 ID 就是網址中間那一段：

```
https://docs.google.com/spreadsheets/d/1a2B3cD4eF5gH6iJ7kL8mN9oP0qR/edit
                                       └─────── spreadsheetId ───────┘
```

`sheet-init` 建立試算表時，Google 回傳這個 ID，程式寫進 `sheet.json`；
之後每個指令都讀它。`drive.file` 之下程式連「看見」你其他試算表的能力都沒有，
所以不需要分辨。

隨時查目前用哪一份：

```bash
python3 music_tool.py sheet-info           # 顯示 ID、網址、token 實際範圍
python3 music_tool.py sheet-info --check    # 加上連線確認與實際列數
```

**⚠️ `sheet.json` 弄丟了怎麼辦**：直接跑 `sheet-init` 會建立**第二份**試算表。
正確做法是從舊試算表的網址複製 ID 重新指定：

```bash
python3 music_tool.py sheet-init --id 1a2B3cD4eF5gH6iJ7kL8mN9oP0qR
```

**之後的日常**

```bash
# 在手機或電腦的 Google Sheets 上直接改標籤（Google 自動跨裝置同步）
python3 music_tool.py build      # 讀 Sheet → 產生網頁
# 再請 Claude 重新發布
```

`build` / `stats` / `list` 都會直接讀 Sheet，所以**不需要 pull 這個步驟**。
沒網路或想快一點時加 `--offline` 用本地快取。

`sync` 與 `edit` 會把結果寫回 Sheet，`manual_tag.py` 也一樣。

**表格規則**

- **`videoId` 欄是比對的鍵，不要改動**
- 同一分類多個標籤用「、」或半角逗號分隔
- `非音樂` 欄填 `Y` 就從點唱機排除
- **直接打新標籤就會生效** —— 讀取時自動登記進 `custom_tags.json` 並提示你
  （打錯字也長一樣，所以看到提示要確認一下）
- 表格裡多打的 `videoId` 會被略過並警告 —— 曲目只能由 `sync` 從 YouTube 加入
- `來源清單` 是唯讀參考欄，改它沒有作用

**已知限制**

- **網頁不會自己更新。** 頁面因 CSP 讀不到 Google Sheet，所以改完仍需
  `build` + 重新發布。Sheet 同步的是你的編輯，不是點唱機。
- **整張覆寫。** `sync`／`edit` 是把整張表重寫（一次 API 呼叫，避免半套狀態）。
  如果你正在手機上編輯而同時跑了 `sync`，可能被覆蓋 ——
  Sheets 有版本紀錄可以還原，但避免同時操作比較好。
- **資料腰斬守門。** 因為 scope 攔不住刪除，程式在覆寫前會比對數量：
  現有 20 首以上、而要寫入的少於一半時直接中止。媒體庫真的大幅縮減時
  用 `sync --force` 通過。

**不想用 Google 的替代**：`export` / `import` 走純 CSV，零 API、零額外授權：

```bash
python3 music_tool.py export        # → tags.csv
python3 music_tool.py import        # 從 tags.csv 匯回
```

---

## 上 GitHub 前的安全檢查

### 絕對不能提交（已在 `.gitignore`）

| 檔案 | 風險 | 為什麼 |
|---|---|---|
| `token.pickle`<br>`token_sheets.pickle` | 🔴 **最高** | 含 **refresh token** —— 等同對你 YouTube（唯讀）與 Drive 檔案的持續存取權，且不會隨密碼變更失效 |
| `client_secret.json` | 🟠 中 | client_id + client_secret + project_id。桌面應用程式的 secret 依 Google 定義不算真機密（必然發佈到使用者端），但它識別你的 Cloud 專案，會被拿去消耗配額或做釣魚頁 |
| `.env` | 🔴 高 | 同上兩者，加上 `ANTHROPIC_API_KEY` |
| `song_tags.json`<br>`tags.csv`<br>`mood.html` | 🟡 隱私 | 不是憑證，但是你**整個媒體庫**（歌名、頻道、videoId）。公開 repo 等於公開你聽什麼 |
| `sheet.json` | 🟢 低 | 只是 spreadsheetId。試算表沒公開分享時，知道 ID 也存取不了 —— 但沒必要外流 |
| `LOCAL.md` | 🟢 低 | Artifact 與 Sheet 的私人網址 |

### 該搬到環境變數的

只有兩樣是程式真正需要、又不該進版控的：

```bash
GOOGLE_CLIENT_ID=...          # 取代 client_secret.json
GOOGLE_CLIENT_SECRET=...
```

設了這兩個就**完全不需要 `client_secret.json`**。另外三個是選用：

```bash
MUSIC_TOOL_SHEET_ID=...       # 取代 sheet.json
MUSIC_TOOL_SHEET_SCOPE=...    # 預設 drive.file，通常不用改
ANTHROPIC_API_KEY=...         # 只有要讓 sync 自動標記時才需要
```

範本見 `.env.example`。**token 檔沒有環境變數版本** —— 它們是授權流程產生的快取，
本來就該留在本機，用 `.gitignore` 擋掉就好。

### 自己驗證一次

`.gitignore` 很容易寫錯（**行尾註解無效**是最常見的坑，git 只認整行 `#` 開頭）。
`git init` 之後實測，不要用眼睛檢查：

```bash
git init && git add -A
git status --short          # 這份清單就是會公開的內容
git check-ignore -v token.pickle client_secret.json song_tags.json .env
```

`git status` 應該只出現這 8 個檔案：

```
.env.example  .gitignore  custom_tags.json  manual_tag.py
music_tool.py  page_template.html  README.md  requirements.txt
```

> ⚠️ 如果不小心提交過憑證，**改 `.gitignore` 沒有用** —— 它還在 git 歷史裡。
> 必須用 `git filter-repo` 清掉歷史，並到 Google Cloud Console
> **撤銷那組憑證重新產生**（假設它已經洩漏）。

---

## 檔案

| 檔案 | 說明 |
|---|---|
| `music_tool.py` | 主程式 |
| `page_template.html` | 手機網頁模板（`build` 會把資料填進 `__DATA__`） |
| `mood.html` | 產出的網頁，不要手改 —— 下次 `build` 會覆蓋 |
| `song_tags.json` | Sheet 模式下是快取；未啟用 Sheet 時是主資料 |
| `sheet.json` | 記住試算表 ID（存在即代表 Sheet 模式） |
| `token_sheets.pickle` | Sheets 授權（與 YouTube 分開） |
| `tags.csv` | `export` 產物 |
| `custom_tags.json` | 你自訂的標籤分類 |
| `manual_tag.py` | 不需 API key 的標記流程 |
| `client_secret.json` | Google OAuth 憑證（你自己下載） |
| `token.pickle` | 授權 token（自動產生） |
| `.env.example` | 環境變數範本，複製成 `.env` 使用 |
| `LOCAL.md` | 你的私人連結與備註（不進版控） |

`client_secret.json`、`token.pickle`、`song_tags.json`、`mood.html` 都已排除在版控外。

---

## 標籤

| 類別 | 標籤 | 選幾個 |
|---|---|---|
| 語言 | 中文、英文、日文、韓文、粵語、純音樂、其他 | 恰好 1 |
| 年代 | 70s以前、80s、90s、2000s、2010s、2020s | 恰好 1（原曲發行年代） |
| 心情 | 放鬆、嗨歌、悲傷、浪漫、振奮、療癒、孤獨 | 1–3 |
| 曲風 | 流行、搖滾、爵士、Indie、電子、R&B、古典、嘻哈、民謠、後搖 | 1–2 |
| 情境 | 開車、工作、運動、睡前、派對、通勤 | 1–3 |

網頁上**同類別內是 OR、跨類別是 AND**（「中文 或 英文」且「放鬆」）。

另有特殊標記 **`非音樂`**：媒體庫混雜大量遊戲實況、程式教學、車評、Vlog，
這些標成非音樂後不會出現在點唱機裡。

媒體庫裡有大量 cover、Live、鋼琴版，這時頻道名是翻唱者不是原唱，所以提示詞
明確要求 AI 判斷「背後的原曲」。年代指的也是原曲發行年代，不是影片上傳年份。

### 沒有 API key 的標記方式

`manual_tag.py` 讓 Claude Code（或你自己）直接標記，不需要 ANTHROPIC_API_KEY：

```bash
python3 manual_tag.py dump 120        # 取出下一批未標記曲目
python3 manual_tag.py apply tags.json # 合併回 song_tags.json
```

每批標完立刻寫檔，中途中斷不會白做。實際的 videoId 由 `.batch.json` 保存，
所以就算 `song_tags.json` 中途變動也不會對錯歌。
