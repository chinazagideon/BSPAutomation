"""Knowledge Base Bounded Context."""

from app.contexts.knowledge.models import KnowledgeEntry
from app.contexts.knowledge.services import KnowledgeService
from app.contexts.knowledge.providers import KnowledgeSliceProvider
from app.contexts.knowledge.router import router

__all__ = [
    "KnowledgeEntry",
    "KnowledgeService",
    "KnowledgeSliceProvider",
    "router",
]
