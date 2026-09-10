# 心情點唱機 (Music Tagger & Mobile Jukebox)

把 YouTube 帳號裡的所有音樂用 AI 打上結構化標籤（**男女歌手／語言／曲風／年代／年份／心情／情境**），
並部署至 **GitHub Pages** 打造專屬的手機 PWA 點唱機，隨時挑選標籤即可一鍵產出臨時歌單聽歌。

---

## 🚀 新手快速入門

> 這一節專為**第一次下載這個專案**的人設計。  
> 請先確認你的電腦已安裝 **Python 3.9+** 與 **Git**。

---

### 情境 A：只想用手機點唱機（無需任何 API）

已經有標籤資料或想手動建表？最省事的方式。

**步驟 1　下載專案**
```bash
git clone https://github.com/<你的帳號>/music-tool.git
cd music-tool
```

**步驟 2　準備 Google Sheet**

1. 開啟 [Google 試算表](https://sheets.google.com) 建立新試算表，第一列依序填入欄標題：
   ```
   videoId  歌名  歌手/原唱  頻道  語言  男女歌手  年代  曲風  心情  情境  非音樂  來源清單
   ```
2. 從第二列起填入歌曲資料（`videoId` 為 YouTube 網址中 `v=` 後面那一段）
3. 右上角「共用」→「知道連結的任何人」設為**檢視者**

**步驟 3　連上網頁**

用瀏覽器打開 `index.html`（或部署到 GitHub Pages 後用手機開），貼上試算表網址 → 按「連線」。

---

### 情境 B：完整功能（YouTube 自動同步 + AI 打標籤）

**步驟 1　下載並安裝套件**
```bash
git clone https://github.com/<你的帳號>/music-tool.git
cd music-tool
pip install -r requirements.txt
```

**步驟 2　複製環境變數範本**
```bash
cp .env.example .env
```

**步驟 3　取得 Google OAuth 憑證**

1. 前往 [Google Cloud Console](https://console.cloud.google.com) 建立或選擇一個專案
2. 啟用 **YouTube Data API v3** 與 **Google Sheets API**
3. 「憑證」→「建立憑證」→「OAuth 用戶端 ID」→ 選 **桌面應用程式**
4. 下載 JSON 改名為 `client_secret.json`，放到本專案根目錄
5. 「OAuth 同意畫面」→「測試使用者」→ 加入你聽音樂的 Google 帳號

**步驟 4　取得免費 Gemini API Key（AI 自動打標籤用）**

1. 前往 [Google AI Studio](https://aistudio.google.com/) 登入
2. 點「Get API key」→「Create API key」複製金鑰
3. 填入 `.env`：
   ```
   GEMINI_API_KEY=AIzaSy...
   ```

**步驟 5　建立 Google Sheet 資料庫**
```bash
python3 music_tool.py sheet-init
# 瀏覽器會彈出授權頁面，同意後自動建立試算表
```

**步驟 6　從 YouTube 同步媒體庫並自動打標籤**
```bash
python3 music_tool.py sync
# 第一次執行會彈出 YouTube 授權頁面，同意即可
# 完成後歌曲與標籤自動寫入 Google Sheet
```

**步驟 7　把 Sheet 設為公開**
```bash
python3 music_tool.py sheet-info   # 查看試算表網址
```
打開該網址 → 右上角「共用」→「知道連結的任何人」設為**檢視者**。

**步驟 8　推送到 GitHub 並開啟 Pages**
```bash
python3 music_tool.py check-security   # 確認沒有機密檔案要上傳
git add index.html manifest.json README.md
git commit -m "init"
git push
```
到 GitHub repo → Settings → Pages → Source 選 `main` + `/ (root)` → 儲存。  
幾分鐘後用手機開 `https://<帳號>.github.io/<repo>/`，貼上 Sheet 網址即完成。

---

### 情境 C：最精簡（不申請任何 API，手動標籤）

**步驟 1　下載並安裝套件**
```bash
git clone https://github.com/<你的帳號>/music-tool.git
cd music-tool
pip install -r requirements.txt
```

**步驟 2　匯出待標記批次交給 AI**
```bash
python3 manual_tag.py dump 120      # 取出最多 120 首尚未標記的歌
# 會產生一份清單，複製貼給 Claude / ChatGPT 叫它照格式標記
```

**步驟 3　將 AI 回傳的結果匯回**
```bash
python3 manual_tag.py apply tags.json
```

**步驟 4　啟動 Sheet 並上傳**
```bash
python3 music_tool.py sheet-init    # 需要 Google Sheets 授權，但不需要 YouTube
```

**步驟 5　開啟網頁**

打開 `index.html`，貼上 Sheet 網址即可使用。

---

### 常用指令速查

| 目的 | 指令 |
|---|---|
| 同步 YouTube + AI 打標 | `python3 music_tool.py sync` |
| 手動調整標籤 | `python3 music_tool.py edit 關鍵字 +放鬆 -嗨歌` |
| 查看標籤統計 | `python3 music_tool.py stats` |
| 推送前安全檢查 | `python3 music_tool.py check-security` |
| 查看 Sheet 資訊 | `python3 music_tool.py sheet-info` |

---

## ⚡ 極簡架構特色 (Best Practices)

1. **AI 自動結構化打標籤（支援 0 元 Google Gemini 2.5 Flash）**：
   - 包含**男女歌手 / 編制**（男歌手、女歌手、男女合唱、樂團/組合、純音樂）、**原唱歌手**、**年代/年份**、**曲風**、**心情**、**情境**。
   - 推薦使用 [Google AI Studio](https://aistudio.google.com/) 免費取得 `GEMINI_API_KEY`（免綁信用卡，每天 1,500 次請求免費，千首歌 0 元標完）。亦支援 Anthropic Claude。
2. **免寫後端（徹底消滅 Apps Script）**：
   - 試算表直接啟用 Google 官方「發布到網路」，手機網頁純前端直讀 Google 官方 `gviz` 端點。
   - 零 Apps Script 程式碼、零權限警告畫面、零冷啟動延遲。
3. **100% 零機密外流，安心部署 GitHub Pages**：
   - `index.html` 為純靜態外殼（不含任何歌曲名單、金鑰或 Sheet ID）。
   - 所有憑證、Token 與個人音樂庫受 `.gitignore` 嚴格隔離。
   - 內建資安查驗指令：`python3 music_tool.py check-security`。
4. **雙模式播放**：
   - **模式 A**：一鍵開啟 YouTube App 播放 50 首臨時歌單（超過 50 首支援一鍵「🔄 換一批」）。
   - **模式 B**：網頁內嵌 YouTube 播放器，不跳轉 App 連續聽歌。

---

## 一次性設定

### 1. 安裝套件

```bash
pip install -r requirements.txt
```

### 2. Google OAuth 憑證（YouTube 唯讀 + Sheet 寫入）

1. 前往 https://console.cloud.google.com 建立或選擇專案
2. 啟用 **YouTube Data API v3** 與 **Google Sheets API**
3. 「憑證」→「建立憑證」→「OAuth 用戶端 ID」→ **桌面應用程式**
4. 下載 JSON 改名為 `client_secret.json` 放置於本專案根目錄
   （或將 Client ID / Secret 填入 `.env`）
5. 「OAuth 同意畫面」→「測試使用者」→ 加入你聽音樂的 Google 帳號

### 3. AI 標籤 API Key（推薦 Google Gemini，100% 免費）

前往 https://aistudio.google.com/ 登入後點擊「Get API key」→「Create API key」：

```bash
export GEMINI_API_KEY="AIzaSy..."
# 或直接寫入 .env 檔案中
```

---

## 日常使用

```bash
python3 music_tool.py sync            # 抓取媒體庫 + AI 自動打標籤 + 寫入 Google Sheet
python3 music_tool.py check-security  # 推送至 GitHub 前的資安防護檢查
python3 music_tool.py stats           # 查看標籤分佈統計
python3 music_tool.py list -f 中文 女歌手 放鬆   # 終端機預覽篩選
python3 music_tool.py sheet-init      # 建立或指定共用 Google Sheet
```

`stats` / `list` 支援 `--offline`（用本地快取，不讀 Sheet）。

### 哪個指令需要哪份授權

兩份 token 是分開的，用到的時機也不同：

| 指令 | YouTube<br>`token.pickle` | Sheets<br>`token_sheets.pickle` |
|---|:---:|:---:|
| `sync` | ✓ | ✓ |
| `stats`／`list`／`edit` | — | ✓ |
| `export`／`import`／`sheet-*` | — | ✓ |

**只有 `sync` 會連 YouTube。** 因為 Sheet 是唯一真相，其他指令只需要讀寫 Sheet
—— 所以刪掉 `token.pickle` 之後，除了 `sync` 以外一切照常運作。

想單獨測試 YouTube 授權（不抓資料、不寫任何東西）：

```bash
python3 -c "import music_tool as M; M.get_youtube(); print('OK')"
```

> `sync` 會用 YouTube 的值覆寫 Sheet 裡的**歌名與頻道**（YouTube 是這兩欄的
> 權威來源）。在 Sheet 上手動改過歌名會被改回去；標籤不受影響。

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

分類名稱隨你取，會直接變成網頁上新的一排 chips。

指派方式同上用 `edit`。改完重開網頁就生效，不需要任何發布步驟。

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

在手機或電腦的 Google Sheets 上直接改標籤即可（Google 自動跨裝置同步），
網頁下次開啟就是最新狀態，不需要任何額外步驟。

`stats` / `list` 也會直接讀 Sheet，所以**不需要 pull 這個步驟**。
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

## 為什麼一次只播 50 首

`watch_videos` 的上限是 **50 首，而且超出的部分會被靜默丟棄**。

實測（2026-09）：

| 送出首數 | HTTP | 產生的 TLGG 清單 ID |
|---|---|---|
| 47 / 48 / 49 | 303 | 各自不同 |
| 50 / 51 / 52 / 300 | 303 | **完全相同** |

49 首以下每個數量都得到不同的清單（內容不同），但 50 首之後 ID 就凍結
—— YouTube 只取前 50 首，其餘丟掉，**不報錯、不警告**。

URL 長度不是瓶頸（300 首約 3646 字元仍正常回應），所以
`PLAY_CAP` **不能調大** —— 調大只會得到「看起來成功但少了歌」的結果。
符合條件超過 50 首時，頁面會隨機抽 50 首並提供「🔄 換一批」。

## 手機網頁

手機端只有一份 `index.html`，走 Google **gviz** 公開端點即時讀你自己的 Sheet。

`index.html` 是**通用版** —— 裡面沒有歌曲、沒有密鑰、沒有 spreadsheetId、
沒有 client ID。試算表網址由使用者在頁面上貼入、存在自己的 localStorage。
所以**同一個公開網址，每個人都能接自己的 Sheet**。

> **前置條件**：gviz 端點只讀得到已開放檢視的試算表。請把你的 Sheet 設為
> 「知道連結的任何人 → 檢視者」（或檔案 → 共用 → 發布到網路）。
> 頁面是唯讀的，改標籤請用 CLI 的 `edit` 或直接在 Google Sheets 上改。

### 部署到 GitHub Pages

repo → Settings → Pages → Source 選 `Deploy from a branch`、
Branch 選 `main` + `/ (root)`，開 `https://<帳號>.github.io/<repo>/`。

因為 `index.html` 不含任何資料，**改完標籤不需要重新部署** ——
頁面每次開啟都是 Sheet 的最新狀態。只有改動程式碼時才需要重新部署。

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

範本見 `.env.example`：複製成 `.env` 填值即可，**程式啟動時會自動載入**
（內建解析，不需要 python-dotenv）。兩個刻意的行為：

- **已存在的環境變數優先** —— 真實環境勝過 `.env` 檔，這是 dotenv 慣例
- **空值直接略過** —— `ANTHROPIC_API_KEY=` 不會被設成空字串，
  否則 anthropic SDK 拿到空 key，錯誤訊息會變得難懂

`.env` 建議設成只有自己能讀：

```bash
chmod 600 .env
```

**token 檔沒有環境變數版本** —— 它們是授權流程產生的快取，
本來就該留在本機，用 `.gitignore` 擋掉就好。

### 自己驗證一次

`.gitignore` 很容易寫錯（**行尾註解無效**是最常見的坑，git 只認整行 `#` 開頭）。
`git init` 之後實測，不要用眼睛檢查：

```bash
git init && git add -A
git status --short          # 這份清單就是會公開的內容
git check-ignore -v token.pickle client_secret.json song_tags.json .env
```

`git status` 應該只出現這些（全部不含機密與個資）：

```
.env.example  .gitignore  ai_tagger/  custom_tags.json  index.html
LICENSE  manifest.json  manual_tag.py  music_tool.py  README.md
requirements.txt
```

> ⚠️ 如果不小心提交過憑證，**改 `.gitignore` 沒有用** —— 它還在 git 歷史裡。
> 必須用 `git filter-repo` 清掉歷史，並到 Google Cloud Console
> **撤銷那組憑證重新產生**（假設它已經洩漏）。

---

## 檔案

| 檔案 | 說明 |
|---|---|
| `music_tool.py` | 主程式 |
| `index.html` | 自架版（貼入試算表網址後讀 Sheet，不含資料） |
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
