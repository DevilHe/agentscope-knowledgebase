from agentscope.rag import QdrantStore

from app.config import settings

_store: QdrantStore | None = None


def get_vector_store() -> QdrantStore:
    global _store
    if _store is None:
        _store = QdrantStore(url=settings.qdrant_url, distance="Cosine")
    return _store
