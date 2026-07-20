import logging
import re
from datetime import timezone
from pathlib import Path

import yaml

from pipeline import config, dedupe
from pipeline.models import Article

logger = logging.getLogger(__name__)


def generate_slug(title: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return text[:80].rstrip("-") or "untitled"


def article_content_path(article: Article, content_dir: Path | None = None) -> Path:
    content_dir = content_dir if content_dir is not None else config.CONTENT_DIR
    date_str = article.fetched_at.strftime("%Y-%m-%d")
    return content_dir / date_str / f"{article.slug}.md"


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, fm_block, _ = text.split("---", 2)
    return yaml.safe_load(fm_block) or {}


def load_published_canonical_urls(content_dir: Path | None = None) -> set[str]:
    content_dir = content_dir if content_dir is not None else config.CONTENT_DIR
    urls: set[str] = set()
    for path in content_dir.glob("**/*.md"):
        try:
            fm = _read_frontmatter(path)
            source_url = fm.get("source_url")
            if source_url:
                urls.add(dedupe.canonicalize_url(source_url))
        except Exception as e:
            logger.warning("frontmatter_read_failed path=%s error=%s", path, e)
    return urls


def _iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_markdown(article: Article) -> str:
    frontmatter = {
        "title": article.title,
        "slug": article.slug,
        "source_url": article.source_url,
        "source_name": article.source_name,
        "published_at": _iso(article.published_at),
        "fetched_at": _iso(article.fetched_at),
        "category": article.category.value,
        "summary": article.summary,
        "why_it_matters": article.why_it_matters,
        "importance": article.importance,
        "sources_count": article.sources_count,
        "essential": article.essential,
    }
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    body = (
        f"{article.summary}\n\n"
        f"**Why it matters:** {article.why_it_matters}\n\n"
        f"[Read more at {article.source_name}]({article.source_url})\n"
    )
    return f"---\n{fm_yaml}---\n\n{body}"


def publish_article(
    article: Article,
    content_dir: Path | None = None,
    existing_urls: set[str] | None = None,
) -> Path | None:
    content_dir = content_dir if content_dir is not None else config.CONTENT_DIR
    if not article.source_url or article.category is None or not article.summary:
        logger.warning("publish_skipped_incomplete title=%s", article.title)
        return None
    canon = dedupe.canonicalize_url(article.source_url)
    if existing_urls is not None and canon in existing_urls:
        return None
    article.slug = article.slug or generate_slug(article.title)
    path = article_content_path(article, content_dir)
    if path.exists():
        path = path.with_stem(f"{path.stem}-{abs(hash(canon)) % 100000:05d}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_markdown(article), encoding="utf-8")
    return path
