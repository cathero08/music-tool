#!/usr/bin/env python3
"""
人工／Claude Code 標記流程 —— 不需要 ANTHROPIC_API_KEY。

  python3 manual_tag.py dump [批次大小]   取出下一批未標記曲目，同時寫下 .batch.json
  python3 manual_tag.py apply <tags.json>  把標記結果合併回 song_tags.json

tags.json 格式：{"0": ["中文","2000s","放鬆","流行","睡前"], "1": [...]}
索引對應 dump 印出的編號；實際的 videoId 由 .batch.json 保存，
所以就算中途 song_tags.json 變動也不會對錯歌。
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
TAGS_FILE = HERE / "song_tags.json"
BATCH_FILE = HERE / ".batch.json"

sys.path.insert(0, str(HERE))
from music_tool import (LANGUAGES, DECADES, ALL_TAGS, NON_MUSIC,
                        load_tags, save_tags, sheet_mode)


def load():
    # 走 music_tool 的讀寫層，Sheet 模式下才不會拿到過期的本地快取
    return load_tags()


def cmd_dump(size):
    songs = load()
    todo = [(v, s) for v, s in songs.items() if not s.get("tags")]
    batch = todo[:size]
    if not batch:
        print("全部標記完成，沒有待處理曲目。")
        return

    BATCH_FILE.write_text(json.dumps([v for v, _ in batch]), encoding="utf-8")
    done = len(songs) - len(todo)
    print(f"# 進度 {done}/{len(songs)}　本批 {len(batch)} 首　剩餘 {len(todo) - len(batch)} 首")
    for i, (_, s) in enumerate(batch):
        ch = s.get("channel", "")
        print(f'{i}\t{s["title"]}\t—\t{ch}')


def cmd_apply(path):
    songs = load()
    ids = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    incoming = json.loads(Path(path).read_text(encoding="utf-8"))

    applied = 0
    problems = []
    for key, tags in incoming.items():
        try:
            idx = int(key)
        except ValueError:
            problems.append(f"索引 {key!r} 不是數字")
            continue
        if not (0 <= idx < len(ids)):
            problems.append(f"索引 {idx} 超出本批範圍（0-{len(ids)-1}）")
            continue

        clean = [t for t in dict.fromkeys(tags) if t in ALL_TAGS]
        unknown = set(tags) - set(ALL_TAGS)
        if unknown:
            problems.append(f"[{idx}] 未知標籤 {sorted(unknown)}")
        if NON_MUSIC in clean:
            # 非音樂只需要這一個標記，不必有語言與年代
            songs[ids[idx]]["tags"] = [NON_MUSIC]
            applied += 1
            continue
        n_lang = sum(1 for t in clean if t in LANGUAGES)
        n_dec = sum(1 for t in clean if t in DECADES)
        if n_lang != 1:
            problems.append(f"[{idx}] 語言標籤 {n_lang} 個，應為 1")
        if n_dec != 1:
            problems.append(f"[{idx}] 年代標籤 {n_dec} 個，應為 1")

        songs[ids[idx]]["tags"] = clean
        applied += 1

    missing = [i for i in range(len(ids)) if str(i) not in incoming]

    save_tags(songs)

    still = sum(1 for s in songs.values() if not s.get("tags"))
    print(f"✅ 寫入 {applied} 首　|　全庫剩 {still} 首未標記"
          + ("（來源：Sheet）" if sheet_mode() else ""))
    if missing:
        print(f"⚠️  本批漏標索引：{missing}")
    for p in problems:
        print(f"⚠️  {p}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "dump":
        cmd_dump(int(sys.argv[2]) if len(sys.argv) > 2 else 120)
    elif sys.argv[1] == "apply":
        cmd_apply(sys.argv[2])
    else:
        sys.exit(__doc__)
