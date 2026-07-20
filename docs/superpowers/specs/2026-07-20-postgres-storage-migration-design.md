# Postgres storage migration — design

## Context

Phase 1's pipeline (`pipeline/`) currently publishes articles as markdown files under `content/YYYY-MM-DD/slug.md`, matching the README's "start with markdown, move to Supabase Postgres later" plan. After a day of test/dev runs, 145 files accumulated, prompting the question of whether markdown will keep scaling — and whether to make the planned Postgres move now rather than later. This spec covers that move: fully replacing markdown as the pipeline's storage, backed by an existing Supabase Postgres project the user already has.

Intended outcome: `publish.py` writes to Postgres instead of `content/`; the 145 existing markdown files are migrated into the new table via a one-time script (no re-fetching/re-summarizing, no wasted Gemini calls); `content/` is retired once migration is verified. No other pipeline stage (fetchers, dedupe, summarize, main's orchestration order) changes.

## Schema

One table, `articles`:

```sql
id             SERIAL PRIMARY KEY
slug           VARCHAR UNIQUE NOT NULL
canonical_url  VARCHAR UNIQUE NOT NULL  -- canonicalize_url(source_url), computed at insert time
source_url     VARCHAR NOT NULL
source_name    VARCHAR NOT NULL
title          VARCHAR NOT NULL
published_at   TIMESTAMPTZ NOT NULL
fetched_at     TIMESTAMPTZ NOT NULL
category       VARCHAR NOT NULL         -- validated by Python's Category enum, not a DB enum type
summary        TEXT NOT NULL
why_it_matters TEXT NOT NULL
importance     INTEGER NULL             -- Phase 3 (ranker) populates this later
sources_count  INTEGER NOT NULL DEFAULT 1
essential      BOOLEAN NOT NULL DEFAULT FALSE
```

`canonical_url` is indexed/unique specifically so the idempotency check (`load_published_canonical_urls`) becomes one indexed `SELECT`, rather than the current approach of globbing and re-canonicalizing every markdown file's frontmatter on every run. A DB-level enum type is deliberately avoided for `category` — with only a create-table script (no Alembic), altering a Postgres enum later would require manual `ALTER TYPE` work, whereas a plain `VARCHAR` validated in Python costs nothing to extend.

## New / changed modules

- **`pipeline/db.py`** (new) — SQLAlchemy engine built from the `DATABASE_URL` env var, a declarative ORM model `ArticleRecord` for the `articles` table (named distinctly from `models.Article`, the dataclass every pipeline stage already passes around, to avoid confusion between "in-flight article" and "persisted row"), and `init_db()` which runs `Base.metadata.create_all(engine)` to create the table if it doesn't exist yet.
- **`pipeline/publish.py`** (rewritten) — `publish_article(article, existing_urls)` now builds an `ArticleRecord` from the `Article` dataclass and inserts it via a SQLAlchemy session, instead of writing a markdown file. `load_published_canonical_urls()` now runs `SELECT canonical_url FROM articles` instead of globbing `content/**/*.md`. The markdown-specific helpers (`to_markdown`, `article_content_path`) are removed — no longer needed once nothing renders to a file. `generate_slug()` is unchanged.
- **`scripts/migrate_markdown_to_db.py`** (new, one-time use) — reads every `content/**/*.md`, parses its YAML frontmatter (same parsing shape `load_published_canonical_urls()` used to use), and inserts each as an `ArticleRecord`, skipping rows that would violate the `canonical_url` unique constraint (defends against being re-run accidentally). Not part of the ongoing pipeline; not invoked by `main.py`.
- **`requirements.txt`** — add `sqlalchemy` and `psycopg[binary]` (the Postgres driver SQLAlchemy needs underneath; `[binary]` avoids requiring local Postgres headers/a C compiler).
- **`.env.example`** — add `DATABASE_URL` (SQLAlchemy-style Postgres URI, e.g. `postgresql+psycopg://user:pass@host:port/dbname`), sourced from the user's existing Supabase project's dashboard (Database → Connection string). Whether the direct-connection or session-pooler variant is needed will be confirmed empirically during implementation.

**Unchanged:** `pipeline/fetchers/*`, `pipeline/dedupe.py`, `pipeline/summarize.py`, `pipeline/models.py`, and `pipeline/main.py`'s orchestration order (fetch → dedupe → filter-already-published → summarize → publish). The storage swap is isolated entirely to how `main.py`'s existing calls into `publish.py` are implemented underneath — no caller-facing signature changes.

## Testing

Consistent with how this pipeline has treated I/O-heavy stages throughout (fetchers and `summarize.py` are smoke-tested manually against real services, not mocked): `generate_slug()` remains unit-tested (still a pure function). `publish_article()` and `load_published_canonical_urls()` are not unit-tested against a mocked/in-memory DB — verified manually against the real Supabase project instead, since Postgres-specific behavior (unique constraints, timestamptz handling) is exactly what a SQLite-backed test double would risk papering over.

## Migration & cleanup sequence

1. Add `DATABASE_URL` to `.env` (user-provided).
2. Run `init_db()` once to create the `articles` table.
3. Run `scripts/migrate_markdown_to_db.py` to backfill the 145 existing articles.
4. Verify row count and spot-check a few rows against their source markdown files.
5. Run the pipeline once more (`python -m pipeline.main`) to confirm new articles insert correctly and idempotency holds (re-running publishes 0 dupes) against the DB instead of the filesystem.
6. Once verified, remove `content/` (fully superseded) — flagged as reversible/confirmable at that point, not assumed.

## Out of scope

- Alembic / versioned migrations (explicitly deferred — a single create-table script is enough for one table right now).
- Any change to the site (Phase 2 doesn't exist yet) or the ranker (Phase 3).
- Dual-writing markdown alongside Postgres (explicitly rejected in favor of one source of truth).
