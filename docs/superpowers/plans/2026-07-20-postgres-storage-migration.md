# Postgres Storage Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace markdown-file storage (`content/*.md`) with a Postgres `articles` table on the user's existing Supabase project, migrating the 145 already-published articles in the process.

**Architecture:** A new `pipeline/db.py` owns the SQLAlchemy engine and an `ArticleRecord` ORM model for the `articles` table. `pipeline/publish.py` is rewritten so `publish_article()` inserts a row instead of writing a file, and `load_published_canonical_urls()` queries the table instead of globbing `content/`. A one-time `scripts/migrate_markdown_to_db.py` backfills the existing 145 files. No other pipeline module (fetchers, `dedupe.py`, `summarize.py`, `main.py`'s orchestration) changes.

**Tech Stack:** SQLAlchemy 2.x (plain ORM, no Alembic), psycopg 3 (`psycopg[binary]`) as the Postgres driver, Supabase Postgres (user-provided connection string).

## Global Constraints

- No Alembic — schema is created once via `Base.metadata.create_all()`, per the approved spec.
- `category` is stored as `VARCHAR`, validated by Python's existing `Category` enum — not a Postgres enum type (spec: avoids needing migration tooling to ever change it).
- `canonical_url` (computed via the existing `dedupe.canonicalize_url()`) is the unique idempotency key — not raw `source_url`.
- No dual-write. Markdown output is fully removed from `publish.py`, not kept alongside Postgres.
- This repository has no `.git` initialized (confirmed earlier in this project) — **skip all git commit steps**. Each task's "commit" step is replaced with "confirm the deliverable works," nothing is committed to version control by this plan.
- DB-backed functions (`publish_article`, `load_published_canonical_urls`) are verified manually against the real Supabase project, not mocked — matching this codebase's existing precedent for I/O-heavy stages (fetchers, `summarize.py`).

## Prerequisite (blocks Task 1's verification step)

The user must provide their Supabase Postgres connection string (Supabase dashboard → Project Settings → Database → Connection string → URI). This plan cannot obtain it — whoever executes Task 1 must have this value in hand (or pause and ask the user for it) before running Task 1's Step 5 verification.

---

### Task 1: Add DB dependencies and DATABASE_URL config

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `sqlalchemy` and `psycopg` importable in the environment; `DATABASE_URL` readable via `os.environ.get("DATABASE_URL")` once `.env` is filled in and `pipeline.config` (which calls `load_dotenv()`) has been imported.

- [ ] **Step 1: Add the two new dependencies to `requirements.txt`**

Append to the existing file (current content is `feedparser`, `requests`, `google-genai`, `python-dotenv`, `PyYAML`, `pytest` — leave those lines untouched, add these two after them):

```
sqlalchemy>=2.0,<3
psycopg[binary]>=3.1,<4
```

- [ ] **Step 2: Add `DATABASE_URL` to `.env.example`**

Append to the existing file (leave `GEMINI_API_KEY`, `GEMINI_MODEL`, `GITHUB_TOKEN` untouched), with a comment explaining where to get it:

```

# Required — Postgres connection string from your Supabase project.
# Supabase dashboard -> Project Settings -> Database -> Connection string -> URI.
# Must use the "postgresql+psycopg://" scheme (not "postgresql://") so SQLAlchemy
# picks the psycopg 3 driver.
DATABASE_URL=
```

- [ ] **Step 3: Install the new dependencies**

Run: `python -m pip install -r requirements.txt`
Expected: installs `sqlalchemy` and `psycopg`/`psycopg-binary` with no errors (existing packages already satisfied are skipped).

- [ ] **Step 4: Verify the imports work**

Run: `python -c "import sqlalchemy; import psycopg; print('sqlalchemy', sqlalchemy.__version__, 'psycopg', psycopg.__version__)"`
Expected: prints both version strings, no `ImportError`.

- [ ] **Step 5: Obtain the connection string and add it to `.env`**

Ask the user for their Supabase connection string if it hasn't already been provided. Add it to `D:\AI-Blog\.env` (create this file by copying `.env.example` if it doesn't already exist — it won't, since `.env` was only ever created earlier for the Gemini/GitHub keys) as:

```
DATABASE_URL=postgresql+psycopg://<their-actual-connection-string-details>
```

If the string they give you starts with `postgresql://` (Supabase's dashboard shows it this way by default), rewrite the scheme to `postgresql+psycopg://` — SQLAlchemy needs the driver name in the URL to pick psycopg 3 instead of defaulting to psycopg2 (which isn't installed).

Then verify connectivity: `python -c "import pipeline.config, os, sqlalchemy; engine = sqlalchemy.create_engine(os.environ['DATABASE_URL']); conn = engine.connect(); print(conn.execute(sqlalchemy.text('SELECT 1')).scalar()); conn.close()"`
Expected: prints `1`. If it errors with an SSL or hostname issue, try the "Session pooler" connection string variant from the same Supabase dashboard page instead of the direct connection string, and use that instead.

---

### Task 2: `pipeline/db.py` — engine, ORM model, schema creation

**Files:**
- Create: `pipeline/db.py`

**Interfaces:**
- Consumes: `DATABASE_URL` env var (via `pipeline.config`'s `load_dotenv()`)
- Produces:
  - `ArticleRecord` — SQLAlchemy declarative model, columns: `id, slug, canonical_url, source_url, source_name, title, published_at, fetched_at, category, summary, why_it_matters, importance, sources_count, essential` (types per the spec's schema)
  - `get_engine() -> sqlalchemy.Engine`
  - `get_session_factory(engine: sqlalchemy.Engine | None = None) -> sqlalchemy.orm.sessionmaker`
  - `init_db(engine: sqlalchemy.Engine | None = None) -> None` — creates the `articles` table if it doesn't exist

- [ ] **Step 1: Write `pipeline/db.py`**

```python
import os

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from pipeline import config  # noqa: F401 -- import triggers config's load_dotenv()

Base = declarative_base()


class ArticleRecord(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    canonical_url = Column(String, unique=True, nullable=False)
    source_url = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    category = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    why_it_matters = Column(Text, nullable=False)
    importance = Column(Integer, nullable=True)
    sources_count = Column(Integer, nullable=False, default=1)
    essential = Column(Boolean, nullable=False, default=False)


def get_engine():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")
    return create_engine(database_url)


def get_session_factory(engine=None):
    engine = engine or get_engine()
    return sessionmaker(bind=engine)


def init_db(engine=None):
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
```

- [ ] **Step 2: Run it to create the table**

Run: `python -c "from pipeline.db import init_db; init_db(); print('done')"`
Expected: prints `done`, no errors.

- [ ] **Step 3: Verify the table exists with the right columns**

Run: `python -c "from pipeline.db import get_engine; import sqlalchemy; insp = sqlalchemy.inspect(get_engine()); print(sorted(c['name'] for c in insp.get_columns('articles')))"`
Expected: `['canonical_url', 'category', 'essential', 'fetched_at', 'id', 'importance', 'published_at', 'slug', 'source_name', 'source_url', 'sources_count', 'summary', 'title', 'why_it_matters']`

- [ ] **Step 4: Confirm the deliverable works (no git commit — see Global Constraints)**

`pipeline/db.py` is complete: engine, session factory, and `ArticleRecord` model are usable by Task 3.

---

### Task 3: Rewrite `pipeline/publish.py` to persist to Postgres

**Files:**
- Modify: `pipeline/publish.py` (full replacement of file contents)
- Test: `tests/test_publish.py` (no changes needed — see Step 4)

**Interfaces:**
- Consumes: `ArticleRecord`, `get_session_factory` from `pipeline.db` (Task 2); `canonicalize_url` from `pipeline.dedupe` (existing); `Article` from `pipeline.models` (existing)
- Produces:
  - `generate_slug(title: str) -> str` — unchanged signature/behavior from the markdown version
  - `load_published_canonical_urls(session_factory=None) -> set[str]`
  - `publish_article(article: Article, session_factory=None, existing_urls: set[str] | None = None) -> str | None` — returns the published slug on success, `None` if skipped (incomplete article, already published, or unresolvable slug collision). **Note the signature changed slightly from the markdown version**: it used to return a `Path | None`; it now returns `str | None` (the slug). `pipeline/main.py` only checks truthiness of the return value (`if publish.publish_article(...):`), so this doesn't require a `main.py` change — but confirm that in Step 5.

- [ ] **Step 1: Replace the contents of `pipeline/publish.py`**

```python
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
```

- [ ] **Step 2: Manually verify `publish_article` against the real Supabase DB**

Run:
```
python -c "
from datetime import datetime, timezone
from pipeline.models import Article, Category
from pipeline.publish import publish_article, load_published_canonical_urls
from pipeline.db import get_session_factory, ArticleRecord

article = Article(
    title='Test Article For Migration Verification',
    source_url='https://example.com/test-article-verification',
    source_name='Test Source',
    published_at=datetime.now(timezone.utc),
    fetched_at=datetime.now(timezone.utc),
    category=Category.TOOLS,
    summary='One. Two. Three.',
    why_it_matters='One. Two.',
)
slug = publish_article(article)
print('published slug:', slug)

urls = load_published_canonical_urls()
print('in canonical set:', 'https://example.com/test-article-verification' in urls)
"
```
Expected: prints `published slug: test-article-for-migration-verification` and `in canonical set: True`.

- [ ] **Step 3: Verify idempotency (re-publishing the same canonical URL is skipped)**

Run:
```
python -c "
from datetime import datetime, timezone
from pipeline.models import Article, Category
from pipeline.publish import publish_article, load_published_canonical_urls

article = Article(
    title='Test Article For Migration Verification (reworded)',
    source_url='https://example.com/test-article-verification',
    source_name='Test Source',
    published_at=datetime.now(timezone.utc),
    fetched_at=datetime.now(timezone.utc),
    category=Category.TOOLS,
    summary='One. Two. Three.',
    why_it_matters='One. Two.',
)
existing = load_published_canonical_urls()
result = publish_article(article, existing_urls=existing)
print('result (should be None):', result)
"
```
Expected: prints `result (should be None): None`.

- [ ] **Step 4: Clean up the test row, then run the existing test suite**

Run: `python -c "from pipeline.db import get_session_factory, ArticleRecord; sf = get_session_factory();  s = sf(); s.query(ArticleRecord).filter(ArticleRecord.canonical_url == 'https://example.com/test-article-verification').delete(); s.commit(); s.close(); print('cleaned up')"`
Expected: prints `cleaned up`.

Then run: `python -m pytest -q`
Expected: all existing tests pass unchanged (`tests/test_publish.py` only tests `generate_slug`, which didn't change; `tests/test_dedupe.py` doesn't touch `publish.py` at all). No new test file is needed for this task per the spec's testing approach (DB I/O verified manually, not mocked).

- [ ] **Step 5: Confirm `pipeline/main.py` doesn't need changes**

Open `pipeline/main.py` and confirm the only two call sites are `publish.load_published_canonical_urls()` (no args — still valid, `session_factory` defaults) and `if publish.publish_article(article, existing_urls=already_published): published_count += 1` (only checks truthiness — still valid since a slug string is truthy and `None` is falsy). No edit needed. If for any reason the call sites differ from this, update them to match this exact pattern before moving on.

---

### Task 4: One-time migration script for the 145 existing markdown files

**Files:**
- Create: `scripts/__init__.py` (empty — makes `scripts` a package so it can be run with `python -m scripts.migrate_markdown_to_db` from the repo root, consistent with how every other module in this project is invoked)
- Create: `scripts/migrate_markdown_to_db.py`

**Interfaces:**
- Consumes: `ArticleRecord`, `get_session_factory`, `init_db` from `pipeline.db` (Task 2); `canonicalize_url` from `pipeline.dedupe`; `CONTENT_DIR` from `pipeline.config`
- Produces: a populated `articles` table; no importable interface (this script is not called by any other code, including `pipeline/main.py`)

- [ ] **Step 1: Create `scripts/__init__.py`**

Empty file (0 bytes).

- [ ] **Step 2: Write `scripts/migrate_markdown_to_db.py`**

```python
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
```

- [ ] **Step 3: Run the migration**

Run: `python -m scripts.migrate_markdown_to_db`
Expected: `Found 145 markdown files under content` followed by `Migrated 145, skipped 0 (already present)`. (If Task 3's verification test row wasn't fully cleaned up, or this is a re-run, some may show as skipped instead — that's the intended safe-re-run behavior, not a failure.)

- [ ] **Step 4: Verify the row count in Postgres matches**

Run: `python -c "from pipeline.db import get_session_factory, ArticleRecord; sf = get_session_factory(); s = sf(); print(s.query(ArticleRecord).count()); s.close()"`
Expected: `145`

- [ ] **Step 5: Spot-check a few rows against their source markdown files**

Run:
```
python -c "
from pipeline.db import get_session_factory, ArticleRecord
sf = get_session_factory()
s = sf()
for row in s.query(ArticleRecord).limit(3):
    print(row.slug, '|', row.title, '|', row.category, '|', row.sources_count)
s.close()
"
```
Expected: 3 rows print with non-empty titles and valid categories (one of `video-gen, image-gen, coding, research, tools, industry`) — manually cross-check one or two against the corresponding file under `content/2026-07-20/<slug>.md` to confirm the title/category match.

---

### Task 5: End-to-end pipeline verification against Postgres, then retire `content/`

**Files:**
- None created/modified — this task only runs and verifies existing code.

**Interfaces:**
- Consumes: everything from Tasks 1-4
- Produces: confirmation that the full pipeline works against Postgres; `content/` removed

- [ ] **Step 1: Run the full pipeline once more**

Run: `python -m pipeline.main`
Expected: the printed summary line shows `already_published_skipped` close to the current row count (145, or 145 plus whatever new articles have appeared since the last fetch — matching the same idempotency behavior already verified against markdown in Phase 1) and 0 or a small number of newly published articles, with `failed=0`.

- [ ] **Step 2: Verify the new row count**

Run: `python -c "from pipeline.db import get_session_factory, ArticleRecord; sf = get_session_factory(); s = sf(); print(s.query(ArticleRecord).count()); s.close()"`
Expected: matches `145 + <newly published count from Step 1's printed summary>`.

- [ ] **Step 3: Re-run immediately to confirm idempotency against Postgres**

Run: `python -m pipeline.main`
Expected: the printed summary shows `0 new -> 0 published, 0 failed` (or very close to 0, allowing for any genuinely new article that appeared in the few seconds between runs, same caveat as the original markdown-based idempotency check).

- [ ] **Step 4: Remove `content/`**

Only after Steps 1-3 pass: run `rm -rf content/` (Windows: the working environment's Bash tool, `rm -rf content`). This directory is now fully superseded by the `articles` table.

- [ ] **Step 5: Confirm the deliverable works (no git commit — see Global Constraints)**

The pipeline now reads/writes Postgres exclusively; `content/` no longer exists; the 145 pre-migration articles plus anything published in this task's Step 1 are all present in the `articles` table. Implementation complete.
