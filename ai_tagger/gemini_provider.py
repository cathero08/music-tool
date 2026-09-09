import os
import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Tuple
from .base import SYSTEM_PROMPT, TAG_SCHEMA, clean_youtube_title

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

class GeminiTagger:
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or GEMINI_MODEL
        if not self.api_key:
            raise ValueError(
                "\n未設定 GEMINI_API_KEY。\n"
                "取得方式（100% 免費、免綁信用卡）：\n"
                "1. 前往 https://aistudio.google.com/ 登入 Google 帳號\n"
                "2. 點擊「Get API key」→「Create API key」\n"
                "3. 於終端機執行 export GEMINI_API_KEY=AIzaSy...\n"
                "   或將其寫入專案的 .env 檔案中\n"
            )

    def tag_batch(self, batch: List[Tuple[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """標記單個批次的歌曲（預設 20~25 首）"""
        listing_lines = []
        for i, (_, s) in enumerate(batch):
            cleaned = clean_youtube_title(s.get("title", ""))
            channel = s.get("channel", "")
            listing_lines.append(f"{i}. {cleaned} - {channel}")
        
        user_content = f"為以下 {len(batch)} 首 YouTube 音樂進行屬性分類標記：\n\n" + "\n".join(listing_lines)
        
        # 轉換 TAG_SCHEMA 為 Gemini 接受的 OpenAPI 結構
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_content}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": TAG_SCHEMA
            }
        }

        url = API_ENDPOINT.format(model=self.model, key=self.api_key)
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            # 若 gemini-2.5-flash 遇配額或名稱變更，自動 fallback 到 gemini-1.5-flash
            if e.code == 404 and "gemini-2.5" in self.model:
                print("   ⚠️  找不到 gemini-2.5-flash，切換為 gemini-1.5-flash 重試...")
                self.model = "gemini-1.5-flash"
                return self.tag_batch(batch)
            raise RuntimeError(f"Gemini API 呼叫失敗 (HTTP {e.code}): {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"Gemini 連線異常: {e}") from e

        # 解析 Gemini 回傳之 JSON
        candidates = resp_data.get("candidates", [])
        if not candidates:
            return []
            
        part_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not part_text:
            return []

        try:
            data = json.loads(part_text)
            return data.get("songs", [])
        except json.JSONDecodeError as e:
            print(f"   ⚠️  Gemini 回傳內容非標準 JSON: {e}")
            return []
