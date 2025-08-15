from __future__ import annotations
import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

load_dotenv()


class LLMClient:
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self._client = OpenAI(api_key=self.api_key) if OpenAI else None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        if not self._client:
            return ""  # Offline fallback
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        # Only include temperature if explicitly provided to avoid model constraints
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            params["temperature"] = kwargs["temperature"]
        # Newer models expect max_completion_tokens
        if "max_completion_tokens" in kwargs:
            params["max_completion_tokens"] = kwargs["max_completion_tokens"]
        elif "max_tokens" in kwargs:
            params["max_completion_tokens"] = kwargs["max_tokens"]
        else:
            params["max_completion_tokens"] = 1200

        resp = self._client.chat.completions.create(**params)
        return resp.choices[0].message.content or ""

