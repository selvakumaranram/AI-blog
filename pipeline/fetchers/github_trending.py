import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from pipeline import config
from pipeline.models import Article

logger = logging.getLogger(__name__)


def fetch_github_trending(
    query: str = config.GITHUB_SEARCH_QUERY,
    min_stars: int = config.GITHUB_MIN_STARS,
    lookback_days: int = config.GITHUB_LOOKBACK_DAYS,
    limit: int = config.GITHUB_RESULT_LIMIT,
) -> list[Article]:
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    q = f"{query} stars:>{min_stars} pushed:>{since}"
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            config.GITHUB_SEARCH_URL,
            params={"q": q, "sort": "stars", "order": "desc", "per_page": limit},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return [_repo_to_article(r) for r in resp.json().get("items", [])]
    except Exception as e:
        logger.warning("github_fetch_failed query=%s error=%s", q, e)
        return []


def _repo_to_article(repo: dict) -> Article:
    return Article(
        title=repo["full_name"],
        source_url=repo["html_url"],
        source_name="GitHub Trending",
        published_at=datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00")),
        fetched_at=datetime.now(timezone.utc),
        source_excerpt=(repo.get("description") or "")[:500],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = fetch_github_trending()
    print(f"Fetched {len(result)} trending repos")
    for a in result:
        print(f"  {a.title} ({a.source_url})")
