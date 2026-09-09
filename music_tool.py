#!/usr/bin/env python3
"""
YouTube Music 心情歌單工具

sync   抓取整個帳號的曲目 → AI 標記新歌 → 更新 song_tags.json
stats  標籤分佈統計
list   終端機預覽篩選結果

授權為唯讀（youtube.readonly）；播放透過 YouTube 的 watch_videos
臨時歌單機制，不需要寫入權限。
"""

import argparse
import csv
import json
import os
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

# Google API 相關套件在 _authorize 與 get_youtube/get_sheets 中按需延遲導入

from ai_tagger import (
    NON_MUSIC, TAG_CATEGORIES as BASE_TAG_CATEGORIES,
    SINGLE_PICK as BASE_SINGLE_PICK, get_tagger,
    # 以下兩項本檔未使用，是給 manual_tag.py 取用的 re-export，勿刪
    LANGUAGES, DECADES,
)

HERE = Path(__file__).parent


def _load_dotenv():
    """把 .env 載進 os.environ。"""
    f = HERE / ".env"
    if not f.exists():
        return
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key and val and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

# 合併授權：單次登入同時擁有 YouTube 讀取與 Sheets 存取權限
UNIFIED_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/" + os.environ.get("MUSIC_TOOL_SHEET_SCOPE", "spreadsheets"),
]
SHEET_SCOPES = ["https://www.googleapis.com/auth/" + os.environ.get("MUSIC_TOOL_SHEET_SCOPE", "spreadsheets")]

SHEET_CREDS_FILE = HERE / "token_sheets.pickle"
SHEET_ID_FILE = HERE / "sheet.json"
TAGS_FILE = HERE / "song_tags.json"
CREDS_FILE = HERE / "token.pickle"
CLIENT_SECRETS = HERE / "client_secret.json"
INDEX_FILE = HERE / "index.html"

PLAY_CAP = 50
BATCH_SIZE = 25

TAG_CATEGORIES = {cat: list(tags) for cat, tags in BASE_TAG_CATEGORIES.items()}

# 自訂標籤：custom_tags.json 形如 {"自訂": ["雨天", "健身房"]}
CSV_FILE = HERE / "tags.csv"
CUSTOM_FILE = HERE / "custom_tags.json"
if CUSTOM_FILE.exists():
    for _cat, _tags in json.loads(CUSTOM_FILE.read_text(encoding="utf-8")).items():
        TAG_CATEGORIES.setdefault(_cat, [])
        for _t in _tags:
            if _t not in TAG_CATEGORIES[_cat]:
                TAG_CATEGORIES[_cat].append(_t)

ALL_TAGS = [t for tags in TAG_CATEGORIES.values() for t in tags] + [NON_MUSIC]
SINGLE_PICK = {cat: list(tags) for cat, tags in BASE_SINGLE_PICK.items()}
DEAD_TITLES = ("Deleted video", "Private video")


# ═══════════════════════════════════════════
# 1. YouTube 授權（唯讀）
# ═══════════════════════════════════════════

def _client_config():
    """優先用環境變數，其次才是 client_secret.json。

    公開 repo 裡不該出現憑證檔，所以提供純環境變數的路徑。
    桌面應用程式的 client_secret 依 Google 的定義不算真正的機密
    （它必然要發佈到使用者端），但它識別你的 Cloud 專案、會被拿去
    消耗配額或做釣魚頁面，所以一樣不要公開。
    """
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if cid and secret:
        return {"installed": {
            "client_id": cid,
            "client_secret": secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }}
    return None


def _authorize(scopes, creds_file):
    """取得授權憑證。若已有有效憑證且符合 scope，直接重複使用。"""
    try:
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("\n缺少 Google 授權套件，請先執行：pip install -r requirements.txt\n")

    creds = None
    if creds_file.exists():
        with open(creds_file, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.valid:
        current_scopes = getattr(creds, "scopes", []) or []
        if all(s in current_scopes for s in scopes):
            return creds

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception:
                creds = None

        if not creds or not creds.valid:
            cfg = _client_config()
            if cfg:
                flow = InstalledAppFlow.from_client_config(cfg, scopes)
            elif CLIENT_SECRETS.exists():
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CLIENT_SECRETS), scopes)
            else:
                sys.exit(
                    "\n找不到 OAuth 用戶端憑證。兩種提供方式選一：\n\n"
                    "  a) 環境變數（建議，公開 repo 適用）\n"
                    "     export GOOGLE_CLIENT_ID=...\n"
                    "     export GOOGLE_CLIENT_SECRET=...\n\n"
                    f"  b) 把下載的 JSON 改名為 {CLIENT_SECRETS.name} 放進此資料夾\n\n"
                    "  憑證取得：https://console.cloud.google.com/apis/credentials\n"
                    "  （OAuth 用戶端 ID → 桌面應用程式）\n"
                )
            creds = flow.run_local_server(port=0)
        with open(creds_file, "wb") as f:
            pickle.dump(creds, f)
        print("🔄 token 已刷新" if refreshed else "✅ 授權完成")

    return creds


def _build_service(*args, **kwargs):
    try:
        from googleapiclient.discovery import build as build_svc
        return build_svc(*args, **kwargs)
    except ImportError:
        sys.exit("\n缺少 google-api-python-client 套件，請先執行：pip install -r requirements.txt\n")


def get_youtube():
    # 預設以 UNIFIED_SCOPES 授權，一次登入同時享有 YouTube 與 Sheets 存取權
    return _build_service("youtube", "v3", credentials=_authorize(UNIFIED_SCOPES, CREDS_FILE))


def get_sheets():
    # 若統一的 CREDS_FILE 已經包含 sheets scope，直接共用；否則相容舊的 SHEET_CREDS_FILE
    if CREDS_FILE.exists():
        with open(CREDS_FILE, "rb") as f:
            creds = pickle.load(f)
        current_scopes = getattr(creds, "scopes", []) or []
        if any("spreadsheets" in s or "drive" in s for s in current_scopes):
            return _build_service("sheets", "v4", credentials=_authorize(UNIFIED_SCOPES, CREDS_FILE))

    return _build_service("sheets", "v4",
                          credentials=_authorize(SHEET_SCOPES, SHEET_CREDS_FILE))


# ═══════════════════════════════════════════
# 2. 抓取整個帳號的曲目
# ═══════════════════════════════════════════

def _playlist_items(yt, playlist_id):
    """讀完一個播放清單的所有曲目，跳過已失效者。"""
    out, page = [], None
    while True:
        try:
            resp = yt.playlistItems().list(
                part="snippet", playlistId=playlist_id,
                maxResults=50, pageToken=page,
            ).execute()
        except HttpError as e:
            print(f"   ⚠️  清單 {playlist_id} 讀取失敗（HTTP {e.resp.status}），跳過")
            return out
        for item in resp.get("items", []):
            s = item["snippet"]
            if s.get("title") in DEAD_TITLES:
                continue
            out.append({
                "videoId": s["resourceId"]["videoId"],
                # YouTube 偶爾回傳帶尾端空白的頻道名（例：'TRF '）。
                # 在來源處就 strip，否則表格解析後不一致，sync 會每次誤判為改動。
                "title": s.get("title", "").strip(),
                "channel": s.get("videoOwnerChannelTitle", "").strip(),
            })
        page = resp.get("nextPageToken")
        if not page:
            return out


def fetch_library(yt):
    """回傳 {videoId: song}，跨清單自動去重，並記下每首歌的來源清單。"""
    songs = {}

    def absorb(source_name, items):
        new = 0
        for it in items:
            vid = it["videoId"]
            if vid in songs:
                songs[vid]["sources"].append(source_name)
            else:
                songs[vid] = {**it, "sources": [source_name], "tags": []}
                new += 1
        print(f"   {source_name[:30]:<32} {len(items):>5} 首（新增 {new}）")

    print("\n📥 抓取媒體庫...")

    ch = yt.channels().list(part="contentDetails", mine=True).execute()
    related = ch["items"][0]["contentDetails"]["relatedPlaylists"]
    if "likes" in related:
        absorb("喜歡的影片", _playlist_items(yt, related["likes"]))

    page = None
    while True:
        resp = yt.playlists().list(
            part="snippet", mine=True, maxResults=50, pageToken=page
        ).execute()
        for pl in resp.get("items", []):
            absorb(pl["snippet"]["title"], _playlist_items(yt, pl["id"]))
        page = resp.get("nextPageToken")
        if not page:
            break

    print(f"   ─────────────────────────────────────────")
    print(f"   ✅ 去重後共 {len(songs)} 首")
    return songs


# ═══════════════════════════════════════════
# ═══════════════════════════════════════════
# 3. AI 標記（支援 Gemini 2.5 Flash / Claude 多 Provider）
# ═══════════════════════════════════════════

def tag_songs(songs, provider=None):
    """就地標記 songs（dict）中還沒有 tags 的曲目。"""
    todo = [(vid, s) for vid, s in songs.items() if not s.get("tags")]
    if not todo:
        print("\n🤖 沒有新歌需要標記")
        return 0

    tagger = get_tagger(provider)
    print(f"\n🤖 AI 標記 {len(todo)} 首新歌（每批 {BATCH_SIZE} 首，引擎: {tagger.__class__.__name__}）...")

    tagged = 0
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start : start + BATCH_SIZE]
        batch_no = start // BATCH_SIZE + 1
        total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE

        try:
            results = tagger.tag_batch(batch)
        except Exception as e:
            print(f"   ⚠️ 批次 {batch_no}/{total_batches} API 呼叫失敗: {e}，跳過此批")
            continue

        got = 0
        for row in results:
            idx = row.get("i")
            if not isinstance(idx, int) or not (0 <= idx < len(batch)):
                continue
            vid, song = batch[idx]

            # 儲存原唱、正式曲名、年份
            if row.get("artist"):
                songs[vid]["artist"] = row["artist"].strip()
            if row.get("title"):
                songs[vid]["title"] = row["title"].strip()
            if row.get("year"):
                songs[vid]["year"] = str(row["year"]).strip()

            if row.get("non_music"):
                songs[vid]["tags"] = [NON_MUSIC]
                got += 1
                continue

            tags = (
                [row.get("language"), row.get("vocal_gender"), row.get("decade")]
                + row.get("genres", [])
                + row.get("moods", [])
                + row.get("scenes", [])
            )
            songs[vid]["tags"] = [t for t in dict.fromkeys(tags) if t and t in ALL_TAGS]
            got += 1

        tagged += got
        missing = len(batch) - got
        warn = f"  ⚠️ 漏 {missing} 首" if missing else ""
        print(f"   批次 {batch_no}/{total_batches}：{got}/{len(batch)} 首{warn}")

        # 每批完成立即寫入本地快取，防止中斷丟失進度
        _write_cache(songs)

        if start + BATCH_SIZE < len(todo):
            time.sleep(0.3)

    still = sum(1 for _, s in songs.items() if not s.get("tags"))
    print(f"   ✅ 本次標記 {tagged} 首" + (f"，仍有 {still} 首未標記（下次 sync 會重試）" if still else ""))
    return tagged


# ═══════════════════════════════════════════
# 4. 快取讀寫
# ═══════════════════════════════════════════

def sheet_mode():
    """有 spreadsheetId（環境變數或 sheet.json）就代表 Sheet 是唯一真相。"""
    return _sheet_id() is not None


def _read_cache():
    if not TAGS_FILE.exists():
        return {}
    with open(TAGS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _write_cache(songs):
    with open(TAGS_FILE, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=1)


def load_tags(offline=False):
    if not sheet_mode() or offline:
        if sheet_mode() and offline:
            print("📄 離線模式：讀本地快取（可能不是 Sheet 的最新狀態）")
        return _read_cache()

    header, rows = read_sheet()
    songs, new_tags = table_to_songs(header, rows)
    if new_tags:
        # Sheet 是真相，所以它定義的標籤就是正式標籤 —— 但打錯字也長這樣，講清楚
        register_new_tags(new_tags)
        print("🆕 Sheet 裡有新標籤，已登記：")
        for cat, tags in new_tags.items():
            print(f"     {cat}：{'、'.join(sorted(tags))}")
        print("     （若是打錯字，請到 Sheet 改掉，並從 custom_tags.json 移除）")
    _write_cache(songs)
    return songs


def save_tags(songs, force=False):
    _write_cache(songs)
    if sheet_mode():
        write_sheet(songs, force=force)
        print(f"💾 已寫回 Sheet（{len(songs)} 首），本地快取同步更新")
    else:
        print(f"💾 已寫入 {TAGS_FILE.name}（{len(songs)} 首）")


# ═══════════════════════════════════════════
# 5. 篩選與統計
# ═══════════════════════════════════════════

def filter_songs(songs, filters):
    """跨類別 AND、同類別 OR。"""
    if not filters:
        return list(songs.values())
    by_cat = {}
    for f in filters:
        for cat, tags in TAG_CATEGORIES.items():
            if f in tags:
                by_cat.setdefault(cat, []).append(f)
    out = []
    for s in songs.values():
        st = set(s.get("tags", []))
        if all(st & set(group) for group in by_cat.values()):
            out.append(s)
    return out


def print_stats(songs):
    count = Counter(t for s in songs.values() for t in s.get("tags", []))
    untagged = sum(1 for s in songs.values() if not s.get("tags"))
    print(f"\n📊 共 {len(songs)} 首" + (f"（{untagged} 首未標記）" if untagged else ""))
    for cat, tags in TAG_CATEGORIES.items():
        rows = [(t, count[t]) for t in tags if count[t]]
        if rows:
            print(f"\n  {cat}")
            for t, n in sorted(rows, key=lambda r: -r[1]):
                bar = "█" * max(1, round(n / max(count.values()) * 34))
                print(f"    {t:<8}{n:>5}  {bar}")


# ═══════════════════════════════════════════
# 6. 主流程
# ═══════════════════════════════════════════

def cmd_sync(args):
    cache = load_tags()
    yt = get_youtube()
    fresh = fetch_library(yt)

    # 保留快取中已有的標籤（含手動修正），只更新來源清單
    for vid, song in fresh.items():
        if vid in cache and cache[vid].get("tags"):
            song["tags"] = cache[vid]["tags"]

    gone = set(cache) - set(fresh)
    if gone:
        print(f"   （{len(gone)} 首已不在媒體庫中，從快取移除）")

    provider = getattr(args, "ai", None)
    tag_songs(fresh, provider=provider)
    save_tags(fresh, force=args.force)
    print_stats(fresh)


def cmd_stats(args):
    print_stats(load_tags(offline=args.offline))


def cmd_list(args):
    songs = load_tags(offline=args.offline)
    hits = filter_songs(songs, args.filters or [])
    label = "、".join(args.filters) if args.filters else "全部"
    print(f"\n篩選「{label}」→ {len(hits)} 首\n")
    for i, s in enumerate(hits[:args.limit], 1):
        print(f"  {i:3}. {s['title'][:56]}")
        print(f"       [{'、'.join(s.get('tags', []))}]")
    if len(hits) > args.limit:
        print(f"\n  ...另外還有 {len(hits) - args.limit} 首（--limit 可調）")





# ═══════════════════════════════════════════
# 8. 手動調整標籤
# ═══════════════════════════════════════════

def cmd_edit(args):
    songs = load_tags()

    adds = [t.lstrip("+") for t in args.changes if t.startswith("+")]
    dels = [t.lstrip("-") for t in args.changes if t.startswith("-")]
    bad = [t for t in adds if t not in ALL_TAGS]
    if bad:
        sys.exit(f"未知標籤 {bad}\n可用標籤：{'、'.join(ALL_TAGS)}\n"
                 f"想新增自己的標籤請編輯 {CUSTOM_FILE.name}")

    if args.id:
        hits = [(v, s) for v, s in songs.items() if v in args.id]
    else:
        q = args.query.lower()
        hits = [(v, s) for v, s in songs.items()
                if q in s["title"].lower() or q in s.get("channel", "").lower()]

    if not hits:
        sys.exit("沒有符合的曲目")

    print(f"\n符合 {len(hits)} 首：\n")
    for v, s in hits:
        print(f"  {s['title'][:62]}")
        print(f"    現有：{'、'.join(s.get('tags', [])) or '（未標記）'}")

    if not adds and not dels:
        print("\n（沒有指定要改的標籤，只列出結果）")
        return

    print(f"\n將要：" + ("　新增 " + "、".join(adds) if adds else "")
          + ("　移除 " + "、".join(dels) if dels else ""))
    if not args.yes and input("\n確定套用？(y/N) ").strip().lower() != "y":
        print("取消")
        return

    warnings = []
    for v, s in hits:
        tags = [t for t in s.get("tags", []) if t not in dels]
        for t in adds:
            if t not in tags:
                tags.append(t)
        s["tags"] = tags
        for cat, members in SINGLE_PICK.items():
            n = sum(1 for t in tags if t in members)
            if n != 1 and NON_MUSIC not in tags:
                warnings.append(f"「{s['title'][:34]}」的{cat}標籤有 {n} 個，應為 1")

    save_tags(songs)
    print("\n✅ 標籤已儲存！若使用 Google Sheet，手機端網頁重新整理即可生效。")


# ═══════════════════════════════════════════
# 9. 表格來回（CSV / Google Sheets 共用）
# ═══════════════════════════════════════════

FIXED_COLS = ["videoId", "歌名", "歌手/原唱", "頻道"]
INFO_COLS = ["來源清單", "更新時間"]


def table_columns():
    """欄位順序：固定欄 → 每個標籤分類一欄 → 非音樂 → 唯讀資訊欄。"""
    return FIXED_COLS + list(TAG_CATEGORIES.keys()) + [NON_MUSIC] + INFO_COLS


def songs_to_rows(songs):
    cats = list(TAG_CATEGORIES.keys())
    rows = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    for vid, s in songs.items():
        tags = set(s.get("tags", []))
        row = [
            vid,
            s.get("title", ""),
            s.get("artist", "") or s.get("channel", ""),
            s.get("channel", ""),
        ]
        for cat in cats:
            row.append("、".join(t for t in TAG_CATEGORIES[cat] if t in tags))
        row.append("Y" if NON_MUSIC in tags else "")
        row.append("、".join(s.get("sources", [])))
        row.append(now_str)
        rows.append(row)
    return rows


def table_to_songs(header, rows):
    """把整張表重建成 songs（Sheet 為真相時的讀取路徑）。回傳 (songs, 新標籤)。"""
    idx = {name: i for i, name in enumerate(header)}
    if "videoId" not in idx:
        sys.exit("表格缺少 videoId 欄，無法解析")

    cats = [c for c in TAG_CATEGORIES if c in idx]
    songs, new_tags = {}, {}

    for row in rows:
        def cell(name):
            i = idx.get(name)
            return (row[i].strip() if i is not None and i < len(row) else "")

        vid = cell("videoId")
        if not vid:
            continue

        if cell(NON_MUSIC).upper() == "Y":
            tags = [NON_MUSIC]
        else:
            tags = []
            for cat in cats:
                for raw in cell(cat).replace(",", "、").split("、"):
                    t = raw.strip()
                    if not t:
                        continue
                    if t not in TAG_CATEGORIES[cat]:
                        new_tags.setdefault(cat, set()).add(t)
                    if t not in tags:
                        tags.append(t)

        artist = cell("歌手/原唱") or cell("原唱") or cell("歌手")
        songs[vid] = {
            "videoId": vid,
            "title": cell("歌名"),
            "artist": artist,
            "channel": cell("頻道"),
            "sources": [x for x in cell("來源清單").split("、") if x],
            "tags": tags,
        }
    return songs, new_tags


def rows_to_songs(header, rows, songs, allow_new):
    """把表格內容合併回 songs。回傳 (改動數, 新標籤, 警告)。"""
    idx = {name: i for i, name in enumerate(header)}
    if "videoId" not in idx:
        sys.exit("表格缺少 videoId 欄，無法比對曲目")

    cats = [c for c in TAG_CATEGORIES if c in idx]
    changed, new_tags, warnings = 0, {}, []

    for row in rows:
        def cell(name):
            i = idx.get(name)
            return (row[i].strip() if i is not None and i < len(row) else "")

        vid = cell("videoId")
        if not vid:
            continue
        if vid not in songs:
            warnings.append(f"表格有 {vid}，但媒體庫裡沒有這首（略過；曲目只能由 sync 加入）")
            continue

        if cell(NON_MUSIC).upper() == "Y":
            tags = [NON_MUSIC]
        else:
            tags = []
            for cat in cats:
                for raw in cell(cat).replace(",", "、").split("、"):
                    t = raw.strip()
                    if not t:
                        continue
                    if t not in TAG_CATEGORIES[cat]:
                        new_tags.setdefault(cat, set()).add(t)
                    if t not in tags:
                        tags.append(t)

        before = songs[vid].get("tags", [])
        if not allow_new:
            tags = [t for t in tags if t in ALL_TAGS]
        # 標籤順序沒有語意，用集合比較；否則匯出再匯入會把全部曲目誤判為已改動
        if set(tags) != set(before):
            songs[vid]["tags"] = tags
            changed += 1

    # 檢查語言／年代的「恰好一個」
    for vid, s in songs.items():
        tags = s.get("tags", [])
        if not tags or NON_MUSIC in tags:
            continue
        for cat, members in SINGLE_PICK.items():
            n = sum(1 for t in tags if t in members)
            if n != 1:
                warnings.append(f"「{s['title'][:34]}」的{cat}有 {n} 個，應為 1")

    return changed, new_tags, warnings


def register_new_tags(new_tags):
    """把表格裡出現的新標籤寫進 custom_tags.json，之後就成為正式標籤。"""
    existing = {}
    if CUSTOM_FILE.exists():
        existing = json.loads(CUSTOM_FILE.read_text(encoding="utf-8"))
    for cat, tags in new_tags.items():
        cur = existing.setdefault(cat, [])
        for t in sorted(tags):
            if t not in cur:
                cur.append(t)
    CUSTOM_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_export(args):
    songs = load_tags()
    path = Path(args.out) if args.out else CSV_FILE
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(table_columns())
        w.writerows(songs_to_rows(songs))
    print(f"📤 已匯出 {path.name}（{len(songs)} 列）")
    print("   同一分類多個標籤用「、」分隔；非音樂欄填 Y 就會從點唱機排除。")
    print("   videoId 欄是比對用的鍵，請不要改動。")


def cmd_import(args):
    songs = load_tags()
    path = Path(args.file) if args.file else CSV_FILE
    if not path.exists():
        sys.exit(f"找不到 {path}")

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        sys.exit("表格是空的")

    header, body = rows[0], rows[1:]
    # 先試跑一次，看看有沒有新標籤要你確認
    probe = json.loads(json.dumps(songs))
    changed, new_tags, _ = rows_to_songs(header, body, probe, allow_new=True)

    if new_tags:
        print("\n表格裡出現這些新標籤：")
        for cat, tags in new_tags.items():
            print(f"   {cat}：{'、'.join(sorted(tags))}")
        print("   （打錯字也會長這樣，請確認一下）")
        if not args.yes and input("\n要把它們登記為正式標籤嗎？(y/N) ").strip().lower() != "y":
            print("→ 不登記，這些標籤會被忽略，其餘改動照常套用")
            new_tags = {}
            changed, _, warnings = rows_to_songs(header, body, songs, allow_new=False)
        else:
            register_new_tags(new_tags)
            print(f"→ 已寫入 {CUSTOM_FILE.name}，重跑本指令即可套用")
            return
    else:
        changed, _, warnings = rows_to_songs(header, body, songs, allow_new=True)

    if not changed:
        print("沒有任何改動")
        return

    save_tags(songs)
    print(f"📥 更新 {changed} 首")
    for w in warnings[:12]:
        print(f"⚠️  {w}")
    if len(warnings) > 12:
        print(f"⚠️  另有 {len(warnings) - 12} 筆警告")
    print("\n改動已生效，手機網頁下次開啟就是最新狀態")


# ═══════════════════════════════════════════
# 10. Google Sheets 來回
# ═══════════════════════════════════════════

def _sheet_id():
    env = os.environ.get("MUSIC_TOOL_SHEET_ID")
    if env:
        return env
    if SHEET_ID_FILE.exists():
        return json.loads(SHEET_ID_FILE.read_text(encoding="utf-8")).get("spreadsheetId")
    return None


def _first_tab(svc, sid):
    """工作表名稱會隨帳號語言不同（Sheet1／工作表1），所以問一次而不是寫死。"""
    meta = svc.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
    props = meta["sheets"][0]["properties"]
    return props["title"], props["sheetId"]


def read_sheet(sid=None):
    sid = sid or _sheet_id()
    if not sid:
        sys.exit("還沒有 Sheet，請先跑：python3 music_tool.py sheet-init")
    svc = get_sheets()
    tab, _ = _first_tab(svc, sid)
    values = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=tab).execute().get("values", [])
    if len(values) < 2:
        sys.exit("Sheet 沒有資料列")
    return values[0], values[1:]


SHRINK_GUARD = 0.5   # 新資料少於現有的一半就擋下來


def write_sheet(songs, sid=None, force=False):
    """整張覆寫。728 列一次寫完是一個 API 呼叫，比逐格更新簡單也不會有半套狀態。"""
    sid = sid or _sheet_id()
    svc = get_sheets()
    tab, tab_id = _first_tab(svc, sid)
    rows = [table_columns()] + songs_to_rows(songs)

    # Google 的 scope 無法表達「可寫不可刪」，所以把守門放在這裡：
    # 任何會讓資料量腰斬的覆寫都先擋下，避免程式出錯或誤操作一次抹掉整張表。
    existing = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{tab}!A:A").execute().get("values", [])
    old_n = max(0, len(existing) - 1)
    new_n = len(rows) - 1
    if not force and old_n >= 20 and new_n < old_n * SHRINK_GUARD:
        sys.exit(
            f"\n⛔ 擋下這次覆寫：Sheet 現有 {old_n} 首，要寫入的只有 {new_n} 首。\n"
            f"   資料量腰斬通常代表出錯了（讀錯檔、sync 只抓到一部分…）。\n"
            f"   確認無誤請加 --force；誤刪可用 Sheet 的「版本紀錄」還原。"
        )

    svc.spreadsheets().values().clear(spreadsheetId=sid, range=tab, body={}).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"{tab}!A1",
        valueInputOption="RAW", body={"values": rows},
    ).execute()
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": tab_id,
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    }]}).execute()
    return sid


def cmd_sheet_init(args):
    """把目前的本地資料搬上 Sheet，之後 Sheet 就是唯一真相。"""
    if sheet_mode() and not args.force:
        sid = _sheet_id()
        sys.exit(f"已經在 Sheet 模式了：\n"
                 f"  https://docs.google.com/spreadsheets/d/{sid}/edit\n"
                 f"要重建請加 --force（會以本地快取覆寫整張 Sheet）")

    songs = _read_cache()
    if not songs:
        sys.exit("本地沒有資料，請先跑 sync")

    svc = get_sheets()
    sid = args.id or _sheet_id()
    if not sid:
        sid = svc.spreadsheets().create(
            body={"properties": {"title": "心情點唱機 標籤表"}}
        ).execute()["spreadsheetId"]
        print("📗 已建立新 Sheet")

    SHEET_ID_FILE.write_text(
        json.dumps({"spreadsheetId": sid}, indent=1), encoding="utf-8")
    write_sheet(songs, sid, force=args.force)

    print(f"✅ 已搬上 Sheet（{len(songs)} 首），從現在起 Sheet 就是唯一真相")
    print(f"   https://docs.google.com/spreadsheets/d/{sid}/edit")
    print(f"   手機用 Google Sheets app 開同一份即可編輯")
    print(f"   本地 {TAGS_FILE.name} 之後只是快取，會被 Sheet 覆寫，不會回寫")


def cmd_sheet_info(args):
    sid = _sheet_id()
    if not sid:
        print("目前是本地模式（沒有 sheet.json）")
        print(f"主資料：{TAGS_FILE.name}")
        print("\n要改用 Sheet 當共用資料庫：python3 music_tool.py sheet-init")
        return

    print(f"Sheet 模式")
    print(f"  spreadsheetId : {sid}")
    print(f"  網址          : https://docs.google.com/spreadsheets/d/{sid}/edit")
    src = ("環境變數 MUSIC_TOOL_SHEET_ID"
           if os.environ.get("MUSIC_TOOL_SHEET_ID") else SHEET_ID_FILE.name)
    print(f"  ID 來源       : {src}")
    print(f"  本地快取      : {TAGS_FILE.name}"
          + ("（存在）" if TAGS_FILE.exists() else "（尚未產生）"))
    # 印 token 實際擁有的 scope，而不是設定要求的 —— 兩者可能不同
    # （改了 MUSIC_TOOL_SHEET_SCOPE 但沒刪 token 時，舊 token 仍然有效）
    want = SHEET_SCOPES[0].rsplit("/", 1)[1]
    if SHEET_CREDS_FILE.exists():
        with open(SHEET_CREDS_FILE, "rb") as f:
            have = [x.rsplit("/", 1)[1] for x in (pickle.load(f).scopes or [])]
        print(f"  token 實際範圍: {'、'.join(have) or '未知'}")
        if want not in have:
            print(f"  ⚠️  設定要求 {want}，但 token 是上面那個。"
                  f"要換範圍請刪掉 {SHEET_CREDS_FILE.name} 重新授權")
    else:
        print(f"  授權範圍      : {want}（尚未授權）")

    if args.check:
        svc = get_sheets()
        meta = svc.spreadsheets().get(
            spreadsheetId=sid, fields="properties.title,sheets.properties").execute()
        tab = meta["sheets"][0]["properties"]["title"]
        n = len(svc.spreadsheets().values().get(
            spreadsheetId=sid, range=f"{tab}!A:A").execute().get("values", []))
        print(f"\n  ✅ 連線正常")
        print(f"  檔名          : {meta['properties']['title']}")
        print(f"  工作表        : {tab}")
        print(f"  資料列數      : {max(0, n - 1)} 首")


def cmd_push_sheet(args):
    svc = get_sheets()
    rows = [table_columns()] + songs_to_rows(load_tags())
    sid = args.id or _sheet_id()

    if not sid:
        created = svc.spreadsheets().create(
            body={"properties": {"title": "心情點唱機 標籤表"}}
        ).execute()
        sid = created["spreadsheetId"]
        SHEET_ID_FILE.write_text(
            json.dumps({"spreadsheetId": sid}, indent=1), encoding="utf-8")
        print(f"📗 已建立新試算表並記在 {SHEET_ID_FILE.name}")

    tab, tab_id = _first_tab(svc, sid)
    svc.spreadsheets().values().clear(spreadsheetId=sid, range=tab, body={}).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"{tab}!A1",
        valueInputOption="RAW", body={"values": rows},
    ).execute()

    # 凍結標題列，手機上滑動時欄位名不會跑掉
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": tab_id,
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    }]}).execute()

    print(f"📤 已推送 {len(rows) - 1} 列")
    print(f"   https://docs.google.com/spreadsheets/d/{sid}/edit")
    print("   手機用 Google Sheets app 開同一份即可編輯，Google 會自動同步。")
    print("   改完回這裡跑：python3 music_tool.py pull-sheet")


def cmd_pull_sheet(args):
    sid = args.id or _sheet_id()
    if not sid:
        sys.exit("還沒有 Sheet，請先跑：python3 music_tool.py sheet-init")

    svc = get_sheets()
    tab, _ = _first_tab(svc, sid)
    values = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=tab).execute().get("values", [])
    if len(values) < 2:
        sys.exit("試算表沒有資料列")

    header, body = values[0], values[1:]
    songs = load_tags()

    probe = json.loads(json.dumps(songs))
    changed, new_tags, _ = rows_to_songs(header, body, probe, allow_new=True)

    if new_tags:
        print("\n試算表裡出現這些新標籤：")
        for cat, tags in new_tags.items():
            print(f"   {cat}：{'、'.join(sorted(tags))}")
        print("   （打錯字也會長這樣，請確認一下）")
        if not args.yes and input("\n要登記為正式標籤嗎？(y/N) ").strip().lower() != "y":
            print("→ 不登記，這些標籤會被忽略，其餘改動照常套用")
            changed, _, warnings = rows_to_songs(header, body, songs, allow_new=False)
        else:
            register_new_tags(new_tags)
            print(f"→ 已寫入 {CUSTOM_FILE.name}，重跑本指令即可套用")
            return
    else:
        changed, _, warnings = rows_to_songs(header, body, songs, allow_new=True)

    if not changed:
        print("沒有任何改動")
        return

    save_tags(songs)
    print(f"📥 更新 {changed} 首")
    for w in warnings[:12]:
        print(f"⚠️  {w}")
    if len(warnings) > 12:
        print(f"⚠️  另有 {len(warnings) - 12} 筆警告")
    print("\n改動已生效，手機網頁下次開啟就是最新狀態")


def cmd_check_security(args):
    """資安查驗：檢查是否有任何敏感檔案或金鑰被追蹤，或有外洩風險"""
    print("\n🔍 正在進行 GitHub Pages 資安防護查驗...")
    issues = []

    # 1. 檢查本機機密與隱私檔案
    critical_files = [
        ".env", "token.pickle", "token_sheets.pickle", "client_secret.json",
        "sheet.json", "song_tags.json", "tags.csv", "LOCAL.md", "mood.html"
    ]
    print("\n  [1/3] 本機檔案隔離狀態：")
    for fn in critical_files:
        p = HERE / fn
        if p.exists():
            print(f"    • {fn:<24} [本機存在，需受 .gitignore 阻擋]")
        else:
            print(f"    • {fn:<24} [本機不存在]")

    # 2. 檢查 index.html 是否包含敏感字串
    print("\n  [2/3] index.html 前端外殼安全性：")
    if INDEX_FILE.exists():
        content = INDEX_FILE.read_text(encoding="utf-8")
        suspicious = []
        if "AIzaSy" in content:
            suspicious.append("可能含有 Google API Key")
        if "sk-ant-" in content or "sk-proj-" in content:
            suspicious.append("可能含有 Anthropic/OpenAI API Key")
        sid = _sheet_id()
        if sid and sid in content:
            suspicious.append("含有個人 Google Sheet ID")
        if suspicious:
            issues.append(f"index.html 含有潛在敏感字串: {suspicious}")
            print(f"    ❌ 警告：{suspicious}")
        else:
            print("    ✅ index.html 經掃描：完全不含任何金鑰、密鑰或個人試算表 ID（安全）")

    # 3. 檢查 .gitignore 防護規則
    print("\n  [3/3] .gitignore 阻擋規則檢查：")
    gi = HERE / ".gitignore"
    if gi.exists():
        git_text = gi.read_text(encoding="utf-8")
        must_have = [".env", "*.pickle", "client_secret.json", "sheet.json", "song_tags.json", "tags.csv", "mood.html"]
        missing_ignores = [f for f in must_have if f not in git_text]
        if missing_ignores:
            issues.append(f".gitignore 缺少防護項目: {missing_ignores}")
            print(f"    ❌ 缺少規則: {missing_ignores}")
        else:
            print("    ✅ .gitignore 規則完整：所有憑證、Token 與個人隱私歌單皆受嚴格阻擋")

    print("\n  ─────────────────────────────────────────────────────────────")
    if not issues:
        print("  🎉 資安查驗通過！專案符合 GitHub Pages 零機密外流標準，可安心部署！\n")
    else:
        print("  ⚠️  發現資安風險，請依上述提示修正後再推送到 GitHub！\n")


def main():
    p = argparse.ArgumentParser(description="YouTube Music 心情歌單工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sync", help="抓取媒體庫並標記新歌")
    s.add_argument("--ai", choices=["gemini", "claude"], default=None,
                   help="指定 AI Provider（預設依環境變數自動偵測，推薦 gemini）")
    s.add_argument("--effort", default="medium",
                   choices=["low", "medium", "high", "xhigh", "max"])
    s.add_argument("--force", action="store_true",
                   help="媒體庫真的大幅縮減時，跳過資料腰斬守門")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("check-security", help="檢查機密與個資是否確實隔離，確保可安全推送至 GitHub")
    s.set_defaults(func=cmd_check_security)

    s = sub.add_parser("edit", help="手動調整標籤，例：edit 周杰倫 +睡前 -派對")
    s.add_argument("query", nargs="?", default="", help="歌名或頻道關鍵字")
    s.add_argument("changes", nargs="*", default=[], help="+標籤 / -標籤")
    s.add_argument("--id", nargs="*", default=None, help="改用 videoId 精準指定")
    s.add_argument("--yes", "-y", action="store_true", help="跳過確認")
    s.set_defaults(func=cmd_edit)

    s = sub.add_parser("export", help="匯出 CSV 供 Sheets／Excel 編輯")
    s.add_argument("--out", help="輸出路徑（預設 tags.csv）")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("import", help="從 CSV 匯入標籤改動")
    s.add_argument("file", nargs="?", help="CSV 路徑（預設 tags.csv）")
    s.add_argument("--yes", "-y", action="store_true", help="自動登記新標籤")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("sheet-info", help="顯示目前用的是哪一份 Sheet")
    s.add_argument("--check", action="store_true", help="連線確認並回報列數")
    s.set_defaults(func=cmd_sheet_info)

    s = sub.add_parser("sheet-init", help="把本地資料搬上 Sheet，之後 Sheet 為唯一真相")
    s.add_argument("--id", help="沿用既有試算表 ID")
    s.add_argument("--force", action="store_true", help="已在 Sheet 模式時強制重建")
    s.set_defaults(func=cmd_sheet_init)

    s = sub.add_parser("push-sheet", help="（進階）以本地快取整張覆寫 Sheet")
    s.add_argument("--id", help="指定試算表 ID（預設用 sheet.json 記住的）")
    s.set_defaults(func=cmd_push_sheet)

    s = sub.add_parser("pull-sheet", help="從 Google Sheets 拉回標籤改動")
    s.add_argument("--id", help="指定試算表 ID")
    s.add_argument("--yes", "-y", action="store_true", help="自動登記新標籤")
    s.set_defaults(func=cmd_pull_sheet)

    s = sub.add_parser("stats", help="標籤分佈統計")
    s.add_argument("--offline", action="store_true", help="用本地快取，不讀 Sheet")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("list", help="終端機預覽篩選結果")
    s.add_argument("-f", "--filters", nargs="*", help="例：中文 放鬆")
    s.add_argument("--limit", type=int, default=30)
    s.add_argument("--offline", action="store_true", help="用本地快取，不讀 Sheet")
    s.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
