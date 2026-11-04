"""Provider interface. The pipeline only ever talks to this, so a model can be swapped
(local Ollama for data that must not leave the machine, a cloud API otherwise) without
changing any governance controls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(Protocol):
    name: str
    model: str
    data_leaves_machine: bool

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> Completion: ...


class ProviderError(RuntimeError):
    pass
