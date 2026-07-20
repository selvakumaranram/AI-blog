"""One-time script: migrate existing content/*.md files into the articles Postgres table.

Run from the repo root: python -m scripts.migrate_markdown_to_db
Safe to re-run: skips any row whose canonical_url already exists in the table.
"""
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy.exc import IntegrityError

from pipeline.config import CONTENT_DIR
from pipeline.db import ArticleRecord, get_session_factory, init_db
from pipeline.dedupe import canonicalize_url


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, fm_block, _ = text.split("---", 2)
    return yaml.safe_load(fm_block) or {}


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def migrate() -> None:
    init_db()
    session_factory = get_session_factory()
    files = sorted(CONTENT_DIR.glob("**/*.md"))
    print(f"Found {len(files)} markdown files under {CONTENT_DIR}")

    migrated, skipped = 0, 0
    for path in files:
        fm = _read_frontmatter(path)
        record = ArticleRecord(
            slug=fm["slug"],
            canonical_url=canonicalize_url(fm["source_url"]),
            source_url=fm["source_url"],
            source_name=fm["source_name"],
            title=fm["title"],
            published_at=_parse_timestamp(fm["published_at"]),
            fetched_at=_parse_timestamp(fm["fetched_at"]),
            category=fm["category"],
            summary=fm["summary"],
            why_it_matters=fm["why_it_matters"],
            importance=fm.get("importance"),
            sources_count=fm.get("sources_count", 1),
            essential=fm.get("essential", False),
        )
        with session_factory() as session:
            session.add(record)
            try:
                session.commit()
                migrated += 1
            except IntegrityError:
                session.rollback()
                skipped += 1

    print(f"Migrated {migrated}, skipped {skipped} (already present)")


if __name__ == "__main__":
    migrate()
