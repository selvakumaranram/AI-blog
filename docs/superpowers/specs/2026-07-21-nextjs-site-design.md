# Phase 2 — Next.js site design

## Context

The README's roadmap marks Phase 2 (the website) as next after Phase 1's pipeline. The pipeline currently publishes to a Supabase Postgres `articles` table (147 rows as of this writing) — no markdown files exist anymore (retired in the Postgres migration). This spec covers building the Next.js site that reads that table and renders it, per the README's already-decided architecture: Essential / Latest / category / individual-post pages, Next.js App Router, Tailwind CSS, hosted on Vercel.

Scope for this pass: build and run the site locally (`npm run dev`). The user already has a Vercel project and will handle the actual deployment/connection themselves — this spec does not cover deployment steps.

One real gap surfaced during brainstorming: the Essential page is specified as "ranked by importance score," but `importance` is `NULL` on every article today — the ranker that populates it is explicitly Phase 3 scope, not yet built. The user chose to ship Essential now using the one ranking signal that already exists (`sources_count`), computed into the schema's existing `essential` boolean column (currently hard-coded `False` everywhere) rather than having the site special-case `sources_count` directly — so the site's query stays stable once Phase 3 adds real importance scoring.

## Locked-in decisions

- Data access: direct Postgres connection from Next.js Server Components via a lightweight query library (`postgres`, the porsager package) — not Drizzle/Prisma, not the Supabase JS client. Mirrors the pipeline's own "direct Postgres, no extra abstraction" approach.
- Freshness: ISR with a 15-minute revalidation window (`export const revalidate = 900`) on every page — no webhook, no pipeline changes needed for freshness.
- Essential ranking (interim, pre-Phase-3): `essential = sources_count >= 3`, computed in the pipeline (`pipeline/publish.py`) at publish time, plus a one-time backfill of the 147 existing rows. The site queries `WHERE essential = true`, not `sources_count` directly.
- Package manager/scaffold: npm, TypeScript, Tailwind CSS, App Router, `src/` directory — consistent with the stack already recorded in `Readme.md` and decided earlier in this project.
- Deployment: out of scope for this spec. User connects the existing Vercel project to the repo themselves afterward.

## Pipeline-side addition (small, precedes the site work)

`pipeline/publish.py`'s `_record_from_article()` currently sets `essential=article.essential` where `article.essential` is always `False` (per `pipeline/models.py`'s Phase-1 design, which deliberately left it unpopulated). This changes to compute `essential = article.sources_count >= 3` at the point `_record_from_article` builds the `ArticleRecord` — a one-line, additive change, not a rewrite of anything else in `publish.py`.

A one-time backfill script (same pattern as `scripts/migrate_markdown_to_db.py`) updates the 147 already-published rows: `UPDATE articles SET essential = (sources_count >= 3)`.

## Site structure

```
site/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # root layout: header nav, footer, Tailwind globals
│   │   ├── page.tsx                # Essential page (/)
│   │   ├── globals.css
│   │   ├── latest/
│   │   │   └── page.tsx            # Latest page (/latest) -- chronological feed
│   │   ├── category/
│   │   │   └── [category]/
│   │   │       └── page.tsx        # /category/[category] -- filtered view
│   │   └── post/
│   │       └── [slug]/
│   │           └── page.tsx        # /post/[slug] -- individual story
│   ├── components/
│   │   ├── ArticleCard.tsx         # shared preview card: title, summary snippet, source, category badge, date
│   │   └── CategoryNav.tsx         # category filter links
│   └── lib/
│       ├── db.ts                   # postgres client, reads DATABASE_URL
│       ├── articles.ts             # getEssentialArticles / getLatestArticles / getArticlesByCategory / getArticleBySlug
│       └── types.ts                # Article TS type mirroring the Postgres articles table
├── .env.local                      # DATABASE_URL (Next.js's own env file, separate from the pipeline's .env)
├── package.json / tsconfig.json / next.config.ts / tailwind config -- standard create-next-app output
```

## Data layer (`site/lib/`)

`types.ts` mirrors the Postgres schema exactly (matching `pipeline/db.py`'s `ArticleRecord` columns): `id, slug, canonicalUrl, sourceUrl, sourceName, title, publishedAt, fetchedAt, category, summary, whyItMatters, importance, sourcesCount, essential`.

`db.ts` creates one `postgres` client instance (module-level, created once — mirroring the lesson learned in the pipeline's own engine-memoization fix) using `DATABASE_URL` from the environment.

`articles.ts` functions, each returning `Promise<Article[]>` (or `Article | null` for the single-post lookup):
- `getEssentialArticles(limit = 20)` → `WHERE essential = true ORDER BY published_at DESC LIMIT $1`
- `getLatestArticles(limit = 50)` → `ORDER BY published_at DESC LIMIT $1`
- `getArticlesByCategory(category, limit = 50)` → `WHERE category = $1 ORDER BY published_at DESC LIMIT $2`
- `getArticleBySlug(slug)` → `WHERE slug = $1 LIMIT 1`

Six category values are the same enum already defined on the Python side (`video-gen | image-gen | coding | research | tools | industry`) — the TS `Category` type is a literal union of these six strings, not re-derived from anything dynamic.

## Pages

- `app/page.tsx` (Essential): calls `getEssentialArticles()`, renders a grid/list of `ArticleCard`s. `export const revalidate = 900`.
- `app/latest/page.tsx`: calls `getLatestArticles()`, same card rendering, chronological.
- `app/category/[category]/page.tsx`: validates `category` against the 6 known values (404 via `notFound()` if not one of them), calls `getArticlesByCategory()`.
- `app/post/[slug]/page.tsx`: calls `getArticleBySlug()` (404 via `notFound()` if missing), renders the full summary, why-it-matters, and a prominent link to `source_url` (the "never rewrite, always link out" principle from the README's core design).
- `app/layout.tsx`: shared header with nav links to `/`, `/latest`, and the 6 category pages; Tailwind globals.

All four page components are Server Components (default in the App Router) — no client-side data fetching, no loading spinners needed since data is fetched at render/revalidation time.

## Testing

Consistent with this project's established pattern (pure logic gets unit tests; I/O-heavy code is verified by running it for real, not mocked): no unit tests planned for the DB query functions in `lib/articles.ts` themselves (thin, declarative SQL wrappers) — verified by actually running `npm run dev` and browsing all four page types against the real 147-row dataset. If any page contains non-trivial pure logic (e.g., category validation), that's a reasonable candidate for a small unit test, decided at implementation time rather than mandated here.

## Verification

1. `npm install`, add `DATABASE_URL` to `site/.env.local`, `npm run dev`.
2. Visit `/` — confirm Essential shows articles, all with `essential = true` in the DB (spot-check against a direct query).
3. Visit `/latest` — confirm chronological ordering, more articles than Essential.
4. Visit each of the 6 `/category/*` pages — confirm filtering is correct.
5. Visit a `/post/[slug]` for a real article — confirm summary, why-it-matters, category, and a working link to `source_url` all render correctly.
6. Visit a nonexistent slug/category — confirm a 404, not a crash.
7. Confirm the pipeline-side `essential` computation: re-run `python -m pipeline.main` once, confirm any newly-published article with `sources_count >= 3` shows up on the Essential page after the next revalidation.

## Out of scope

- Deployment to Vercel (user's own next step, not covered here).
- Phase 3's real importance-based ranking (the `essential` formula's `OR importance >= 7` half) — the column and query are structured so that addition won't require touching the site again.
- Distribution (Phase 4), SEO/sitemap polish, newsletter (Phase 5).
