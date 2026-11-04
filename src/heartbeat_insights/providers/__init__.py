from .base import Completion, LLMProvider, ProviderError
from .mock_provider import MockBiasedProvider, MockProvider


def get_provider(name: str, model: str | None = None) -> LLMProvider:
    name = name.lower()
    if name == "mock":
        return MockProvider()
    if name == "mock-biased":
        return MockBiasedProvider()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)
    if name == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(model=model)
    raise ValueError(f"Unknown provider '{name}'. Choose mock, mock-biased, anthropic or ollama.")


__all__ = ["Completion", "LLMProvider", "ProviderError", "get_provider", "MockProvider", "MockBiasedProvider"]
