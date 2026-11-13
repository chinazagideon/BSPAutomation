"""Knowledge Base Bounded Context."""

from app.contexts.knowledge.models import KnowledgeEntry
from app.contexts.knowledge.services import KnowledgeService
from app.contexts.knowledge.router import router


def __getattr__(name: str):
    if name == "KnowledgeSliceProvider":
        from app.contexts.knowledge.providers import KnowledgeSliceProvider
        return KnowledgeSliceProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "KnowledgeEntry",
    "KnowledgeService",
    "KnowledgeSliceProvider",
    "router",
]

