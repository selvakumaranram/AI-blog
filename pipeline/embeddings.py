import logging
import os
import time

from google import genai
from google.genai import errors

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
BATCH_SIZE = 100  # API hard limit: at most 100 texts per embed_content call
RATE_LIMIT_RETRY_SECONDS = 60  # free tier quota is per-minute; one retry after a minute
# is enough to clear it without an open-ended retry loop.


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def _embed_chunk(client: genai.Client, chunk: list[str]) -> list[list[float]]:
    try:
        resp = client.models.embed_content(model=EMBEDDING_MODEL, contents=chunk)
    except errors.ClientError as e:
        if e.code != 429:
            raise
        logger.warning("embedding_rate_limited, retrying once after %ss", RATE_LIMIT_RETRY_SECONDS)
        time.sleep(RATE_LIMIT_RETRY_SECONDS)
        resp = client.models.embed_content(model=EMBEDDING_MODEL, contents=chunk)
    return [e.values for e in resp.embeddings]


def embed_texts(texts: list[str], client: genai.Client | None = None) -> list[list[float]]:
    """Return one embedding vector per input text, in order. Raises on API/network failure
    (after one retry on a 429 rate-limit, since the free-tier quota is per-minute)."""
    if not texts:
        return []
    client = client or _get_client()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i : i + BATCH_SIZE]
        vectors.extend(_embed_chunk(client, chunk))
    return vectors
