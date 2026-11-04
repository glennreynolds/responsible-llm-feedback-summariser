from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import Completion, ProviderError


class OllamaProvider:
    """Local model via Ollama (https://ollama.com). Nothing leaves the machine."""

    name = "ollama"
    data_leaves_machine = False

    def __init__(self, model: str | None = None, host: str | None = None, timeout: int = 600):
        self.model = model or os.environ.get("HI_OLLAMA_MODEL", "llama3.1")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout = timeout

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> Completion:
        body = json.dumps({
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(f"{self.host}/api/chat", data=body,
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, ConnectionError) as e:
            raise ProviderError(f"Could not reach Ollama at {self.host}: {e}") from e
        return Completion(data.get("message", {}).get("content", ""), self.name, self.model,
                          data.get("prompt_eval_count"), data.get("eval_count"))
