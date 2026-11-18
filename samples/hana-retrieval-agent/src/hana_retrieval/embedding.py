"""The HANA path uses the selected AI Core embedding model without fallback."""

import os

from hana_retrieval.repository import RetrievalError, validate_vector

# Configure approved AI Core credentials through the SDK before the HANA path.
MODEL = "text-embedding-3-small"
TRANSPORT_TIMEOUT_SECONDS = 20.0


def embed(text, dimension):
    if not isinstance(text, str) or not 1 <= len(text) <= 2000:
        raise ValueError("query must contain 1-2000 characters")
    try:
        from gen_ai_hub.proxy.native.openai import OpenAI

        client = OpenAI(timeout=TRANSPORT_TIMEOUT_SECONDS, max_retries=0)
        try:
            result = client.embeddings.create(model=MODEL, input=text)
            vector = result.data[0].embedding
        finally:
            client.close()
    except Exception:
        raise RetrievalError("AI Core embedding request failed") from None
    return validate_vector(vector, dimension)


def dimension():
    return int(os.environ["EMBEDDING_DIMENSION"])
