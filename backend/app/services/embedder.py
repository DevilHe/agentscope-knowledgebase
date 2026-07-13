from agentscope.credential import OllamaCredential
from agentscope.embedding import OllamaEmbeddingModel

from app.config import settings

_embedder: OllamaEmbeddingModel | None = None


def get_embedder() -> OllamaEmbeddingModel:
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbeddingModel(
            credential=OllamaCredential(host=settings.ollama_base_url),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return _embedder


async def embed_texts(texts: list[str]) -> list[list[float]]:
    embedder = get_embedder()
    response = await embedder(texts)
    return response.embeddings
