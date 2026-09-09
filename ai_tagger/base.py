import re
import os
from typing import Optional

# 標籤分類定義
LANGUAGES = ["中文", "英文", "日文", "韓文", "粵語", "純音樂", "其他"]
VOCALS = ["男歌手", "女歌手", "男女合唱", "樂團/組合", "純音樂"]
DECADES = ["70s以前", "80s", "90s", "2000s", "2010s", "2020s"]
GENRES = ["流行", "搖滾", "爵士", "Indie", "電子", "R&B", "古典", "嘻哈/饒舌", "民謠", "ACG"]
MOODS = ["放鬆", "嗨歌", "悲傷", "浪漫", "振奮", "療癒", "孤獨"]
SCENES = ["開車", "工作", "運動", "睡前", "派對", "通勤"]
NON_MUSIC = "非音樂"

TAG_CATEGORIES = {
    "語言": LANGUAGES,
    "男女歌手": VOCALS,
    "年代": DECADES,
    "曲風": GENRES,
    "心情": MOODS,
    "情境": SCENES,
}

# 要求恰好單選一個值的分類
SINGLE_PICK = {
    "語言": LANGUAGES,
    "男女歌手": VOCALS,
    "年代": DECADES,
}

ALL_TAGS = [t for tags in TAG_CATEGORIES.values() for t in tags] + [NON_MUSIC]

# 標題雜訊清洗正則
NOISE_PATTERNS = [
    r"\[\s*(?:Official\s+)?(?:Music\s+)?(?:Video|MV|Audio|Lyric|Lyrics|HD|4K|1080[pP])\s*\]",
    r"\(\s*(?:Official\s+)?(?:Music\s+)?(?:Video|MV|Audio|Lyric|Lyrics|HD|4K|1080[pP])\s*\)",
    r"【\s*(?:Official\s+)?(?:Music\s+)?(?:Video|MV|Audio|歌詞|繁中字|官方|高音質)\s*】",
    r"（\s*(?:Official\s+)?(?:MV|歌詞|官方)\s*）",
    r"\s*[-/|]\s*Official\s+(?:Music\s+)?Video",
    r"\bOfficial\s+(?:Music\s+)?Video\b",
]

def clean_youtube_title(title: str) -> str:
    """去除 YouTube 影片標題常見的雜訊（如 [Official MV]、歌詞、畫質標記）"""
    res = title
    for pat in NOISE_PATTERNS:
        res = re.sub(pat, "", res, flags=re.IGNORECASE)
    # 壓縮連續空白
    res = re.sub(r"\s+", " ", res).strip()
    return res or title

SYSTEM_PROMPT = """你是專業音樂分類與元數據助手，負責為使用者的 YouTube 音樂庫進行屬性分類與結構化標籤。

輸入資料為：每行「索引. 標題 - 頻道名稱」。
注意 YouTube 標題往往混雜上傳頻道、翻唱資訊或非音樂影片：
1. **先判斷是否為音樂 (non_music)**：
   - 包含遊戲實況、教學、Vlog、開箱、車評、新聞、Podcast、演講、純笑話等非音樂主體的內容，一律標記 non_music = true。
   - MV、Live 現場、翻唱 (Cover)、原聲帶 (OST)、演奏曲皆屬於音樂 (non_music = false)。
2. **提取原曲資訊（不要被翻唱或上傳頻道帶走）**：
   - 若為翻唱（例：「陳綺貞 魚 cover - 163braces」），請解析出原曲歌名（魚）與原唱歌手（陳綺貞）。
   - 若為唱片公司上傳（例：「滾石唱片」），頻道名是上傳者而非歌手，請從標題中解析出真正歌手與歌名。
3. **分類欄位規範**：
   - language (語言)：恰選 1 個（中文 / 英文 / 日文 / 韓文 / 粵語 / 純音樂 / 其他）。純器樂請選「純音樂」。
   - vocal_gender (男女歌手/編制)：恰選 1 個（男歌手 / 女歌手 / 男女合唱 / 樂團/組合 / 純音樂）。無人聲器樂請選「純音樂」。
   - decade (年代)：恰選 1 個（70s以前 / 80s / 90s / 2000s / 2010s / 2020s）。依原曲發行年份判定，1980 前選「70s以前」。
   - year (年份)：原曲確切發行年份（4位數如 2004，若無法確定可填空字串 ""）。
   - genres (風格/曲風)：選 1-2 個貼切值（流行 / 搖滾 / 爵士 / Indie / 電子 / R&B / 古典 / 嘻哈/饒舌 / 民謠 / ACG）。
   - moods (心情)：選 1-3 個貼切值（放鬆 / 嗨歌 / 悲傷 / 浪漫 / 振奮 / 療癒 / 孤獨）。
   - scenes (情境)：選 1-3 個貼切值（開車 / 工作 / 運動 / 睡前 / 派對 / 通勤）。
"""

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "songs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer", "description": "索引，從 0 開始"},
                    "non_music": {
                        "type": "boolean",
                        "description": "非音樂內容（實況、教學、Vlog、新聞）為 true",
                    },
                    "title": {"type": "string", "description": "原曲正式歌名"},
                    "artist": {"type": "string", "description": "原唱歌手或樂團名稱"},
                    "language": {"type": "string", "enum": LANGUAGES},
                    "vocal_gender": {"type": "string", "enum": VOCALS},
                    "decade": {"type": "string", "enum": DECADES},
                    "year": {"type": "string", "description": "發行年份如 2004"},
                    "genres": {"type": "array", "items": {"type": "string", "enum": GENRES}},
                    "moods": {"type": "array", "items": {"type": "string", "enum": MOODS}},
                    "scenes": {"type": "array", "items": {"type": "string", "enum": SCENES}},
                },
                "required": [
                    "i", "non_music", "title", "artist",
                    "language", "vocal_gender", "decade", "genres", "moods", "scenes"
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["songs"],
    "additionalProperties": False,
}

def get_tagger(provider: Optional[str] = None):
    """根據環境變數或參數取得 AI Tagger 實例"""
    prov = (provider or os.environ.get("AI_PROVIDER") or "").lower()
    
    if not prov:
        if os.environ.get("GEMINI_API_KEY"):
            prov = "gemini"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            prov = "claude"
        else:
            prov = "gemini"  # 預設使用 Gemini

    if prov == "gemini":
        from .gemini_provider import GeminiTagger
        return GeminiTagger()
    elif prov == "claude":
        from .claude_provider import ClaudeTagger
        return ClaudeTagger()
    else:
        raise ValueError(f"不支援的 AI Provider: {prov}（支援: gemini, claude）")
