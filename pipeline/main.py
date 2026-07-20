import logging
import time

from pipeline import config, dedupe, publish, summarize
from pipeline.fetchers import github_trending, hackernews, rss
from pipeline.summarize import SummarizeError

logger = logging.getLogger(__name__)


def _safe_fetch(fn, label: str):
    try:
        return fn()
    except Exception as e:
        logger.error("fetch_stage_failed stage=%s error=%s", label, e)
        return []


def run() -> None:
    fetched = (
        _safe_fetch(rss.fetch_all_rss, "rss")
        + _safe_fetch(hackernews.fetch_hackernews, "hackernews")
        + _safe_fetch(github_trending.fetch_github_trending, "github_trending")
    )
    deduped = dedupe.deduplicate(fetched)
    already_published = publish.load_published_canonical_urls()
    new_articles = [
        a for a in deduped if dedupe.canonicalize_url(a.source_url) not in already_published
    ]

    published_count, failed_count = 0, 0
    for article in new_articles:
        try:
            summarize.summarize_article(article)
        except SummarizeError as e:
            logger.warning("summarize_failed title=%s error=%s", article.title, e)
            failed_count += 1
            continue
        finally:
            time.sleep(config.GEMINI_CALL_DELAY_SECONDS)
        try:
            if publish.publish_article(article, existing_urls=already_published):
                published_count += 1
        except Exception as e:
            logger.warning("publish_failed title=%s error=%s", article.title, e)
            failed_count += 1

    logger.info(
        "run_summary fetched=%s after_dedupe=%s already_published_skipped=%s "
        "new_candidates=%s published=%s failed=%s",
        len(fetched),
        len(deduped),
        len(deduped) - len(new_articles),
        len(new_articles),
        published_count,
        failed_count,
    )
    print(
        f"Fetched {len(fetched)} -> deduped {len(deduped)} -> "
        f"{len(new_articles)} new -> {published_count} published, {failed_count} failed"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
