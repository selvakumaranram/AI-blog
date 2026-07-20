import logging
import re

from sqlalchemy.exc import IntegrityError

from pipeline import dedupe
from pipeline.db import ArticleRecord, get_session_factory
from pipeline.models import Article

logger = logging.getLogger(__name__)


def generate_slug(title: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return text[:80].rstrip("-") or "untitled"


def load_published_canonical_urls(session_factory=None) -> set[str]:
    session_factory = session_factory or get_session_factory()
    with session_factory() as session:
        rows = session.query(ArticleRecord.canonical_url).all()
        return {row[0] for row in rows}


def _record_from_article(article: Article, slug: str, canonical_url: str) -> ArticleRecord:
    return ArticleRecord(
        slug=slug,
        canonical_url=canonical_url,
        source_url=article.source_url,
        source_name=article.source_name,
        title=article.title,
        published_at=article.published_at,
        fetched_at=article.fetched_at,
        category=article.category.value,
        summary=article.summary,
        why_it_matters=article.why_it_matters,
        importance=article.importance,
        sources_count=article.sources_count,
        essential=article.essential,
    )


def publish_article(
    article: Article,
    session_factory=None,
    existing_urls: set[str] | None = None,
) -> str | None:
    if not article.source_url or article.category is None or not article.summary:
        logger.warning("publish_skipped_incomplete title=%s", article.title)
        return None
    canon = dedupe.canonicalize_url(article.source_url)
    if existing_urls is not None and canon in existing_urls:
        return None

    session_factory = session_factory or get_session_factory()
    base_slug = article.slug or generate_slug(article.title)
    for slug_attempt in (base_slug, f"{base_slug}-{abs(hash(canon)) % 100000:05d}"):
        record = _record_from_article(article, slug_attempt, canon)
        with session_factory() as session:
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                continue
            article.slug = slug_attempt
            return slug_attempt

    logger.warning("publish_failed_slug_collision title=%s", article.title)
    return None
