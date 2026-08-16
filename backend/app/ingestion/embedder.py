"""OpenAI-backed `Embedder` (implementation.md §5). Real adapter for `text-embedding-3-small`.

No dedicated contract test — the fake (`tests/fakes/embedder.py`) is exercised directly
by `tests/integration/test_ingestion_pipeline.py`; this class is wired only in production
and by `@pytest.mark.integration` runs of the pipeline against real services.
"""

from collections.abc import Sequence

from openai import OpenAI

MODEL_NAME = "text-embedding-3-small"


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = MODEL_NAME) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=list(texts))
        return [item.embedding for item in response.data]
