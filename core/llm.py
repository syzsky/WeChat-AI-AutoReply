"""OpenAI 兼容 LLM 客户端（游戏内聊天自动回复 / 简单决策）。

沿用上游项目的多引擎思路，但只保留 openai_chat 一种传输，
任何 OpenAI 兼容网关（小米 mimo / DeepSeek / 自建 one-api）都能直接接。
"""
import time

import requests


class LLMClient:
    def __init__(self, api_key: str, api_base: str, model: str,
                 temperature: float = 0.7, timeout: int = 30,
                 max_retries: int = 2, system_prompt: str = ""):
        self.api_key = (api_key or "").strip()
        self.api_base = (api_base or "").rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self.system_prompt = system_prompt

    @classmethod
    def from_config(cls, cfg: dict):
        section = (cfg or {}).get("llm", {}) or {}
        return cls(
            api_key=section.get("api_key", ""),
            api_base=section.get("api_base", "https://api.deepseek.com/v1"),
            model=section.get("model", "deepseek-chat"),
            temperature=float(section.get("temperature", 0.7)),
            timeout=int(section.get("timeout", 30)),
            system_prompt=section.get("system_prompt", ""),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.api_base and self.model)

    def chat(self, user_text: str, history=None, max_tokens: int = 300) -> str:
        """单轮对话；history 为 [{'role','content'}, ...]。失败返回空串。"""
        if not self.enabled:
            return ""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        for m in (history or [])[-10:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(f"{self.api_base}/chat/completions",
                                  json=payload, headers=headers, timeout=self.timeout)
                if r.status_code == 200:
                    data = r.json()
                    msg = data["choices"][0]["message"]
                    return (msg.get("content") or "").strip()
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.2 * (attempt + 1))
                    continue
                return ""
            except Exception:
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return ""
        return ""
