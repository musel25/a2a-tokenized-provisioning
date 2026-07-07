"""agents — the brains. LLM judgment in exactly two slots (rule 1); backend chosen by
env (ADR-001); A2A SDK confined to a2a_adapter (ADR-002)."""

from .llm import LLMClient, LLMConfig, StructuredError, ollama_up

__all__ = ["LLMClient", "LLMConfig", "StructuredError", "ollama_up"]
