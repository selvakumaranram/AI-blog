import logging
import math
import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pipeline import config, embeddings
from pipeline.models import Article

logger = logging.getLogger(__name__)

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "igshid",
    "_hsenc",
    "_hsmi",
}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    query_pairs = sorted((k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS)
    return urlunsplit(("https", netloc, path, urlencode(query_pairs), ""))


def _normalize_title(title: str) -> str:
    text = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(sorted(text.split()))


def titles_similar(a: str, b: str, threshold: float = config.TITLE_SIMILARITY_THRESHOLD) -> bool:
    return SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio() >= threshold


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _try_embed_titles(articles: list[Article], embed_fn) -> list[list[float]] | None:
    try:
        return embed_fn([a.title for a in articles])
    except Exception as e:
        logger.warning("embedding_failed_falling_back_to_title_similarity error=%s", e)
        return None


def _priority(article: Article) -> int:
    if article.source_name in config.SOURCE_PRIORITY:
        return config.SOURCE_PRIORITY.index(article.source_name)
    return len(config.SOURCE_PRIORITY)


def _merge_cluster(cluster: list[Article]) -> Article:
    primary = min(cluster, key=lambda a: (_priority(a), a.published_at))
    primary.sources_count = len(cluster)
    return primary


def deduplicate(articles: list[Article], embed_fn=embeddings.embed_texts) -> list[Article]:
    """Cluster articles covering the same story and merge each cluster into one.

    Primary signal: cosine similarity of title embeddings (catches independently-worded
    headlines about the same event across outlets). Falls back to stdlib fuzzy title
    matching if embeddings are unavailable (network/API failure) so one bad call doesn't
    break the run. Exact canonical-URL matches always merge regardless of either signal.
    """
    vectors = _try_embed_titles(articles, embed_fn) if articles else None
    clusters: list[list[Article]] = []
    cluster_vectors: list[list[float] | None] = []
    for i, article in enumerate(articles):
        canon = canonicalize_url(article.source_url)
        match_idx = None
        for ci, cluster in enumerate(clusters):
            rep = cluster[0]
            if canonicalize_url(rep.source_url) == canon:
                match_idx = ci
                break
            if vectors is not None:
                same_story = cosine_similarity(vectors[i], cluster_vectors[ci]) >= config.SEMANTIC_SIMILARITY_THRESHOLD
            else:
                same_story = titles_similar(rep.title, article.title)
            if same_story:
                match_idx = ci
                break
        if match_idx is not None:
            clusters[match_idx].append(article)
        else:
            clusters.append([article])
            cluster_vectors.append(vectors[i] if vectors is not None else None)
    return [_merge_cluster(c) for c in clusters]
