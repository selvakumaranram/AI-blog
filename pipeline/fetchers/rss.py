import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from pipeline import config
from pipeline.models import Article

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "AIPulseBot/0.1"}


def fetch_feed(name: str, url: str) -> list[Article]:
    """Fetch+parse one feed. Never raises — returns [] and logs a warning on failure."""
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"unparseable feed: {parsed.get('bozo_exception')}")
        cutoff = datetime.now(timezone.utc) - timedelta(days=config.RSS_LOOKBACK_DAYS)
        articles = []
        for entry in parsed.entries:
            article = _entry_to_article(entry, name)
            if article is not None and article.published_at >= cutoff:
                articles.append(article)
        return articles
    except Exception as e:
        logger.warning("rss_fetch_failed source=%s url=%s error=%s", name, url, e)
        return []


def _entry_to_article(entry, source_name: str) -> Article | None:
    if not entry.get("title") or not entry.get("link"):
        return None
    published = _parse_time(entry.get("published_parsed") or entry.get("updated_parsed"))
    return Article(
        title=entry.title.strip(),
        source_url=entry.link,
        source_name=source_name,
        published_at=published or datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        source_excerpt=entry.get("summary", "")[:500],
    )


def _parse_time(struct_time) -> datetime | None:
    if not struct_time:
        return None
    return datetime(*struct_time[:6], tzinfo=timezone.utc)


def fetch_all_rss(feeds: list[dict[str, str]] | None = None) -> list[Article]:
    feeds = feeds if feeds is not None else config.RSS_FEEDS
    articles = []
    for feed in feeds:
        articles.extend(fetch_feed(feed["name"], feed["url"]))
    return articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = fetch_all_rss()
    print(f"Fetched {len(result)} articles from {len(config.RSS_FEEDS)} feeds")
    for a in result[:10]:
        print(f"  [{a.source_name}] {a.title}")
