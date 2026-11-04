from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import Completion, ProviderError


class AnthropicProvider:
    name = "anthropic"
    data_leaves_machine = True

    def __init__(self, model: str | None = None, api_key: str | None = None, timeout: int = 120):
        self.model = model or os.environ.get("HI_ANTHROPIC_MODEL", "claude-haiku-5-5")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> Completion:
        body = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            raise ProviderError(f"Anthropic API error {e.code}: {e.read().decode(errors='replace')[:500]}") from e
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        return Completion(text, self.name, data.get("model", self.model),
                          usage.get("input_tokens"), usage.get("output_tokens"))
