import logging
from datetime import datetime, timezone

import requests

from pipeline import config
from pipeline.models import Article

logger = logging.getLogger(__name__)


def fetch_hackernews(
    keywords: list[str] | None = None,
    min_points: int = config.HN_MIN_POINTS,
) -> list[Article]:
    """Query the Algolia HN Search API per keyword, dedupe hits by objectID, map to Article."""
    keywords = keywords if keywords is not None else config.HN_KEYWORDS
    seen_ids: set[str] = set()
    articles: list[Article] = []
    for kw in keywords:
        try:
            resp = requests.get(
                config.HN_SEARCH_URL,
                params={
                    "query": kw,
                    "tags": "story",
                    "numericFilters": f"points>={min_points}",
                },
                timeout=10,
            )
            resp.raise_for_status()
            for hit in resp.json().get("hits", []):
                if hit["objectID"] in seen_ids:
                    continue
                seen_ids.add(hit["objectID"])
                article = _hit_to_article(hit)
                if article is not None:
                    articles.append(article)
        except Exception as e:
            logger.warning("hn_fetch_failed keyword=%s error=%s", kw, e)
            continue
    return articles


def _hit_to_article(hit: dict) -> Article | None:
    url = hit.get("url")
    if not url:
        # Ask HN / Show HN text-only posts have no external source_url — schema requires one.
        return None
    return Article(
        title=hit["title"],
        source_url=url,
        source_name="Hacker News",
        published_at=datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        source_excerpt="",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = fetch_hackernews()
    print(f"Fetched {len(result)} HN stories")
    for a in result[:10]:
        print(f"  {a.title} ({a.source_url})")
