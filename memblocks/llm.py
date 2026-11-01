"""极简 LLM 客户端：OpenAI 兼容 /chat/completions，只用标准库。"""
import json
import os
import urllib.error
import urllib.request

DEFAULTS = {
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "api_key": "",
}


def config(store):
    cfg = store.config_get().get("llm") or {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if v})
    if not out.get("api_key"):
        out["api_key"] = os.environ.get("DEEPSEEK_API_KEY", "")
    return out


class LLM:
    def __init__(self, base_url, api_key, model, timeout=60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, messages, temperature=0.2, max_tokens=800):
        """返回 (文本, usage字典)。"""
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Authorization": "Bearer " + self.api_key,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode())
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return text, usage
