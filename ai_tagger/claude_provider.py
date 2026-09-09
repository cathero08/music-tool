import os
import json
from typing import List, Dict, Any, Tuple
from .base import SYSTEM_PROMPT, clean_youtube_title

CLAUDE_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

class ClaudeTagger:
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or CLAUDE_MODEL
        if not self.api_key:
            raise ValueError(
                "\n未設定 ANTHROPIC_API_KEY。\n"
                "請先 export ANTHROPIC_API_KEY=sk-ant-...\n"
                "或改用免費的 Google Gemini（於 .env 設定 GEMINI_API_KEY）\n"
            )
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise RuntimeError("未安裝 anthropic 套件，請執行 pip install anthropic")

    def tag_batch(self, batch: List[Tuple[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
        listing_lines = []
        for i, (_, s) in enumerate(batch):
            cleaned = clean_youtube_title(s.get("title", ""))
            channel = s.get("channel", "")
            listing_lines.append(f"{i}. {cleaned} - {channel}")

        user_content = f"為以下 {len(batch)} 首 YouTube 音樂進行屬性分類標記：\n\n" + "\n".join(listing_lines)

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
            # 擷取 JSON 字串區塊
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = text[start_idx:end_idx + 1]
                data = json.loads(json_str)
                return data.get("songs", [])
            return []
        except Exception as e:
            print(f"   ⚠️  Claude 標記失敗: {e}")
            return []
