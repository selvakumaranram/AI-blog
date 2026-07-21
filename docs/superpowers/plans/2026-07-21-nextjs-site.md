# Phase 2 Next.js Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run locally the Next.js site that reads the pipeline's Postgres `articles` table and renders Essential / Latest / category / individual-post pages, per the README's Phase 2 scope.

**Architecture:** A small pipeline-side addition populates the existing `essential` boolean column (`sources_count >= 3`, the interim ranking signal) so the site's Essential query stays stable once Phase 3 adds real importance scoring. The Next.js app (`site/`, App Router, TypeScript, Tailwind) queries Postgres directly via `lib/db.ts` (the `postgres` package), through typed query functions in `lib/articles.ts`, rendered by Server Components with ISR (15-minute revalidation) — no separate API layer, no webhook.

**Tech Stack:** Next.js (App Router) + TypeScript + Tailwind CSS + npm, `postgres` (porsager) as the Postgres client, Python/SQLAlchemy for the small pipeline-side addition.

## Global Constraints

- Deployment to Vercel is OUT OF SCOPE for this plan — user connects their existing Vercel project themselves afterward. Every task in this plan verifies against `npm run dev` (local), not a deployed URL.
- Site queries Postgres directly (no Drizzle/Prisma/Supabase-JS-client, no separate API route layer) — per the spec's locked-in decision.
- Essential page must query `WHERE essential = true`, never `sources_count` directly — the site's query must not need to change when Phase 3 adds real importance-based ranking.
- All list/detail pages use `export const revalidate = 900` (15-minute ISR) — no webhook-based revalidation.
- The 6 category values are exactly: `video-gen, image-gen, coding, research, tools, industry` — must match `pipeline/models.py`'s `Category` enum exactly, both in the TypeScript type and in any validation logic.
- `site/.env.local` holds `DATABASE_URL` for Next.js — separate file from the pipeline's `.env`. Same connection string works, but do not assume the `+psycopg` scheme suffix is needed (that's SQLAlchemy-specific; the `postgres` npm package expects a plain `postgres://` or `postgresql://` URL).
- This repo is a git repo (initialized during the Postgres migration work) — real commits per task, as established in that prior work.
- Next.js's exact current API surface (e.g., whether dynamic route `params` is a `Promise` requiring `await`, exact `create-next-app` CLI flags) should be verified empirically against whatever `create-next-app@latest` actually scaffolds in Task 2, not assumed from potentially-stale knowledge — flagged explicitly in the tasks below where this applies.

---

### Task 1: Pipeline — compute the `essential` flag and backfill existing rows

**Files:**
- Modify: `pipeline/publish.py`
- Create: `scripts/backfill_essential_flag.py`

**Interfaces:**
- Consumes: `ArticleRecord`, `get_session_factory` from `pipeline.db` (existing)
- Produces: every newly-published `ArticleRecord` has `essential` set correctly at insert time; the 147 pre-existing rows get the same value applied via a one-time backfill

- [ ] **Step 1: Read the current `_record_from_article` function**

Read `pipeline/publish.py` to find `_record_from_article`. It currently has a line `essential=article.essential,` where `article.essential` (from `pipeline/models.py`'s `Article` dataclass) is always `False` — this was deliberate in Phase 1 (no ranking signal existed yet), but now `sources_count` is a real signal.

- [ ] **Step 2: Change the `essential` computation**

In `_record_from_article`, change:
```python
essential=article.essential,
```
to:
```python
essential=article.sources_count >= 3,
```
Leave every other field in that function unchanged. Do not modify `pipeline/models.py`'s `Article` dataclass — its `essential` field stays as-is (unused by this new logic, but not worth removing since it's part of the documented schema).

- [ ] **Step 3: Verify with a live check against Supabase**

Run:
```
python -c "
from datetime import datetime, timezone
from pipeline.models import Article, Category
from pipeline.publish import publish_article

article = Article(
    title='Test Article For Essential Flag Verification',
    source_url='https://example.com/test-essential-flag',
    source_name='Test Source',
    published_at=datetime.now(timezone.utc),
    fetched_at=datetime.now(timezone.utc),
    category=Category.TOOLS,
    summary='One. Two. Three.',
    why_it_matters='One. Two.',
    sources_count=3,
)
slug = publish_article(article)
print('published slug:', slug)

from pipeline.db import get_session_factory, ArticleRecord
sf = get_session_factory()
with sf() as s:
    row = s.query(ArticleRecord).filter(ArticleRecord.slug == slug).one()
    print('essential:', row.essential)
    s.delete(row)
    s.commit()
print('cleaned up')
"
```
Expected: `published slug: test-article-for-essential-flag-verification`, `essential: True` (since `sources_count=3 >= 3`), `cleaned up`.

- [ ] **Step 4: Write and run the one-time backfill script**

Create `scripts/backfill_essential_flag.py`:
```python
"""One-time script: backfill the essential flag on already-published articles.

Run from the repo root: python -m scripts.backfill_essential_flag
Safe to re-run: it's an idempotent UPDATE, not an insert.
"""
from pipeline.db import ArticleRecord, get_session_factory


def backfill() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.query(ArticleRecord).all()
        changed = 0
        for row in rows:
            correct = row.sources_count >= 3
            if row.essential != correct:
                row.essential = correct
                changed += 1
        session.commit()
        print(f"Checked {len(rows)} rows, updated {changed}")


if __name__ == "__main__":
    backfill()
```

Run: `python -m scripts.backfill_essential_flag`
Expected: `Checked 147 rows, updated <N>` where N is however many rows actually have `sources_count >= 3` today (could be 0 if none qualify — that's a valid outcome, not a failure).

- [ ] **Step 5: Confirm the result**

Run: `python -c "from pipeline.db import get_session_factory, ArticleRecord; sf = get_session_factory(); s = sf(); print('essential=True count:', s.query(ArticleRecord).filter(ArticleRecord.essential == True).count()); print('total:', s.query(ArticleRecord).count()); s.close()"`
Expected: prints both counts; the essential count should be small relative to the total (only stories covered by 3+ sources qualify) — sanity-check this looks like a real subset, not 0 and not all 147 (unless the real data genuinely produces one of those extremes, in which case note it, don't treat it as a bug).

- [ ] **Step 6: Run the full pytest suite and commit**

Run: `python -m pytest -q` (from D:\AI-Blog) — confirm all 16 existing tests still pass (this task doesn't touch anything they test).

Commit:
```
git add pipeline/publish.py scripts/backfill_essential_flag.py
git commit -m "Compute essential flag from sources_count and backfill existing rows"
```

---

### Task 2: Scaffold the Next.js app

**Files:**
- Create: `site/` (entire directory tree via `create-next-app`)

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: a working `site/` Next.js app skeleton that `npm run dev` can serve, with TypeScript, Tailwind, and the App Router configured, ready for Tasks 3-7 to add code into

- [ ] **Step 1: Scaffold via create-next-app**

From the repo root (`D:\AI-Blog`), run:
```
npx create-next-app@latest site --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```
If this prompts interactively despite the flags (CLI flags can change between `create-next-app` versions), run `npx create-next-app@latest --help` first to see the current flag names for TypeScript/Tailwind/App-Router/src-dir/import-alias/npm, and use whatever the current equivalents are — the goal is a non-interactive scaffold with TypeScript, Tailwind, App Router, a `src/` directory, the `@/*` import alias, and npm as the package manager. Report in your self-review which exact command ended up working, since later tasks assume this file layout.

- [ ] **Step 2: Verify it boots**

Run (from `D:\AI-Blog\site`): `npm run dev &` (background it), wait a few seconds, then `curl -s http://localhost:3000 | head -20`, then stop the dev server (`kill %1` or find/kill the node process).
Expected: curl returns HTML containing the default Next.js starter page content (something like "Get started by editing" or the Next.js logo alt text) — confirms the scaffold actually runs.

- [ ] **Step 3: Install the Postgres client**

Run (from `D:\AI-Blog\site`): `npm install postgres`
Expected: adds `postgres` to `site/package.json` dependencies, installs with no errors.

- [ ] **Step 4: Commit**

```
cd D:\AI-Blog
git add site/
git commit -m "Scaffold Next.js site (TypeScript, Tailwind, App Router)"
```
Note: `create-next-app` generates its own `site/.gitignore` (covering `site/node_modules/`, `site/.next/`, etc.) — confirm `git status` doesn't show `node_modules` or `.next` as untracked before committing; if it does, something about the scaffold's `.gitignore` didn't apply correctly and needs investigating before committing (don't manually exclude with `git add` flags — fix the root cause).

---

### Task 3: Data layer — `lib/db.ts`, `lib/types.ts`, `lib/articles.ts`

**Files:**
- Create: `site/src/lib/db.ts`
- Create: `site/src/lib/types.ts`
- Create: `site/src/lib/articles.ts`
- Create: `site/.env.local` (gitignored by the Task 2 scaffold's `.gitignore` — verify this, don't commit it)

**Interfaces:**
- Consumes: the `postgres` package (Task 2); the real Supabase `DATABASE_URL` (same DB the pipeline uses)
- Produces:
  - `Category` type (union of the 6 literal strings) and `CATEGORIES: Category[]` array, from `lib/types.ts`
  - `Article` interface, from `lib/types.ts`
  - `getEssentialArticles(limit?: number): Promise<Article[]>`
  - `getLatestArticles(limit?: number): Promise<Article[]>`
  - `getArticlesByCategory(category: Category, limit?: number): Promise<Article[]>`
  - `getArticleBySlug(slug: string): Promise<Article | null>`
  all from `lib/articles.ts`, all consumed by Tasks 5-7's pages.

- [ ] **Step 1: Add `DATABASE_URL` to `site/.env.local`**

Copy the same connection string already working in the repo root's `.env` (used by the Python pipeline), but strip the `+psycopg` driver suffix if present — the `postgres` npm package wants a plain `postgres://` or `postgresql://` URL, not a SQLAlchemy dialect URL. Write it to `D:\AI-Blog\site\.env.local` as:
```
DATABASE_URL=postgresql://<same-connection-details-without-+psycopg>
```
Confirm `site/.gitignore` (from the Task 2 scaffold) already lists `.env*.local` or similar — Next.js's default scaffold `.gitignore` does this automatically; verify rather than assume, and do not commit this file.

- [ ] **Step 2: Write `site/src/lib/types.ts`**

```typescript
export type Category =
  | "video-gen"
  | "image-gen"
  | "coding"
  | "research"
  | "tools"
  | "industry";

export const CATEGORIES: Category[] = [
  "video-gen",
  "image-gen",
  "coding",
  "research",
  "tools",
  "industry",
];

export interface Article {
  id: number;
  slug: string;
  canonicalUrl: string;
  sourceUrl: string;
  sourceName: string;
  title: string;
  publishedAt: Date;
  fetchedAt: Date;
  category: Category;
  summary: string;
  whyItMatters: string;
  importance: number | null;
  sourcesCount: number;
  essential: boolean;
}
```

- [ ] **Step 3: Write `site/src/lib/db.ts`**

```typescript
import postgres from "postgres";

const sql = postgres(process.env.DATABASE_URL!, {
  ssl: "require",
});

export default sql;
```
If connecting fails with an SSL-related error when you verify in Step 5, try `ssl: "prefer"` instead, or check Supabase's dashboard for the exact recommended connection mode (direct vs. session pooler) — same class of issue the Python pipeline's `DATABASE_URL` setup already worked through, document what worked.

- [ ] **Step 4: Write `site/src/lib/articles.ts`**

```typescript
import sql from "./db";
import type { Article, Category } from "./types";

function mapRow(row: Record<string, unknown>): Article {
  return {
    id: row.id as number,
    slug: row.slug as string,
    canonicalUrl: row.canonical_url as string,
    sourceUrl: row.source_url as string,
    sourceName: row.source_name as string,
    title: row.title as string,
    publishedAt: row.published_at as Date,
    fetchedAt: row.fetched_at as Date,
    category: row.category as Category,
    summary: row.summary as string,
    whyItMatters: row.why_it_matters as string,
    importance: row.importance as number | null,
    sourcesCount: row.sources_count as number,
    essential: row.essential as boolean,
  };
}

export async function getEssentialArticles(limit = 20): Promise<Article[]> {
  const rows = await sql`
    SELECT * FROM articles
    WHERE essential = true
    ORDER BY published_at DESC
    LIMIT ${limit}
  `;
  return rows.map(mapRow);
}

export async function getLatestArticles(limit = 50): Promise<Article[]> {
  const rows = await sql`
    SELECT * FROM articles
    ORDER BY published_at DESC
    LIMIT ${limit}
  `;
  return rows.map(mapRow);
}

export async function getArticlesByCategory(
  category: Category,
  limit = 50,
): Promise<Article[]> {
  const rows = await sql`
    SELECT * FROM articles
    WHERE category = ${category}
    ORDER BY published_at DESC
    LIMIT ${limit}
  `;
  return rows.map(mapRow);
}

export async function getArticleBySlug(slug: string): Promise<Article | null> {
  const rows = await sql`
    SELECT * FROM articles
    WHERE slug = ${slug}
    LIMIT 1
  `;
  return rows.length > 0 ? mapRow(rows[0]) : null;
}
```

- [ ] **Step 5: Verify against the real database**

From `D:\AI-Blog\site`, create a throwaway verification script `/tmp/verify-articles.mts` (or run inline via `npx tsx`) that imports and calls all four functions and prints result counts/shapes. If `tsx` isn't available, add it as a dev dependency first: `npm install -D tsx`. Then run something equivalent to:
```
npx tsx -e "
import('./src/lib/articles.ts').then(async (m) => {
  const essential = await m.getEssentialArticles();
  const latest = await m.getLatestArticles();
  const coding = await m.getArticlesByCategory('coding');
  console.log('essential:', essential.length, essential[0]?.title);
  console.log('latest:', latest.length, latest[0]?.title);
  console.log('coding:', coding.length);
  const bySlug = await m.getArticleBySlug(latest[0]?.slug ?? 'nope');
  console.log('bySlug found:', bySlug !== null, bySlug?.title);
  process.exit(0);
});
"
```
(Adjust the exact invocation if `npx tsx -e` with a dynamic import doesn't work cleanly in this environment — a small temporary `.mts` script file run via `npx tsx path/to/script.mts` is an equally valid way to verify; delete the scratch file afterward either way.) Expected: `essential` count is a small subset (matches Task 1's backfill result), `latest` returns up to 50 real articles with a real title, `coding` returns some count ≥ 0, `bySlug found: true` with a matching title.

- [ ] **Step 6: Commit**

```
git add site/src/lib/ site/package.json site/package-lock.json
git commit -m "Add Postgres data layer (db.ts, types.ts, articles.ts)"
```
(Do not `git add site/.env.local` — confirm it's excluded via `git status` before committing.)

---

### Task 4: Shared UI — layout, ArticleCard, CategoryNav

**Files:**
- Modify: `site/src/app/layout.tsx` (replace the create-next-app default)
- Modify: `site/src/app/globals.css` (only if the default needs adjusting — likely no change needed beyond what create-next-app already generated for Tailwind)
- Create: `site/src/components/ArticleCard.tsx`
- Create: `site/src/components/CategoryNav.tsx`

**Interfaces:**
- Consumes: `Article`, `Category`, `CATEGORIES` from `@/lib/types` (Task 3)
- Produces: `<ArticleCard article={article} />` and `<CategoryNav />` components, consumed by Tasks 5-6's pages; the root layout wrapping every page

- [ ] **Step 1: Write `site/src/components/ArticleCard.tsx`**

```tsx
import Link from "next/link";
import type { Article } from "@/lib/types";

export default function ArticleCard({ article }: { article: Article }) {
  return (
    <article className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
        <span className="uppercase font-semibold">{article.category}</span>
        <span>&middot;</span>
        <span>{article.sourceName}</span>
      </div>
      <h2 className="text-lg font-semibold mb-2">
        <Link href={`/post/${article.slug}`} className="hover:underline">
          {article.title}
        </Link>
      </h2>
      <p className="text-sm text-gray-700">{article.summary}</p>
    </article>
  );
}
```

- [ ] **Step 2: Write `site/src/components/CategoryNav.tsx`**

```tsx
import Link from "next/link";
import { CATEGORIES } from "@/lib/types";

export default function CategoryNav() {
  return (
    <nav className="flex flex-wrap gap-3 text-sm">
      {CATEGORIES.map((category) => (
        <Link
          key={category}
          href={`/category/${category}`}
          className="px-3 py-1 rounded-full border border-gray-300 hover:bg-gray-100"
        >
          {category}
        </Link>
      ))}
    </nav>
  );
}
```

- [ ] **Step 3: Replace `site/src/app/layout.tsx`**

Read the existing create-next-app-generated `layout.tsx` first to see what metadata/font setup it already has (it likely imports a Google font and sets up `<html>`/`<body>` with font variables) — preserve that font/metadata scaffolding, and add a header with navigation on top of it. A reasonable version, adjust to match whatever the scaffold already generated rather than deleting its font setup:

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Pulse",
  description: "Automated AI news, aggregated and summarized.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-gray-200 p-4 flex gap-4 items-center">
          <Link href="/" className="font-bold text-lg">
            AI Pulse
          </Link>
          <Link href="/" className="text-sm">
            Essential
          </Link>
          <Link href="/latest" className="text-sm">
            Latest
          </Link>
        </header>
        <main className="max-w-3xl mx-auto p-4">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Verify it builds without type errors**

Run (from `D:\AI-Blog\site`): `npx tsc --noEmit`
Expected: no output (no type errors). If the scaffold's existing font-related code from Step 3 causes a type error because you didn't preserve it correctly, fix by re-reading the original generated file and merging your header addition into it rather than replacing it wholesale.

- [ ] **Step 5: Commit**

```
git add site/src/app/layout.tsx site/src/components/
git commit -m "Add shared layout, ArticleCard, and CategoryNav components"
```

---

### Task 5: Essential page and Latest page

**Files:**
- Modify: `site/src/app/page.tsx` (replace the create-next-app default — this becomes the Essential page)
- Create: `site/src/app/latest/page.tsx`

**Interfaces:**
- Consumes: `getEssentialArticles`, `getLatestArticles` from `@/lib/articles` (Task 3); `ArticleCard`, `CategoryNav` from `@/components/*` (Task 4)
- Produces: working `/` and `/latest` routes

- [ ] **Step 1: Replace `site/src/app/page.tsx`**

```tsx
import ArticleCard from "@/components/ArticleCard";
import CategoryNav from "@/components/CategoryNav";
import { getEssentialArticles } from "@/lib/articles";

export const revalidate = 900;

export default async function EssentialPage() {
  const articles = await getEssentialArticles();
  return (
    <div className="space-y-6">
      <CategoryNav />
      <h1 className="text-2xl font-bold">Essential</h1>
      <div className="space-y-4">
        {articles.map((article) => (
          <ArticleCard key={article.slug} article={article} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `site/src/app/latest/page.tsx`**

```tsx
import ArticleCard from "@/components/ArticleCard";
import CategoryNav from "@/components/CategoryNav";
import { getLatestArticles } from "@/lib/articles";

export const revalidate = 900;

export default async function LatestPage() {
  const articles = await getLatestArticles();
  return (
    <div className="space-y-6">
      <CategoryNav />
      <h1 className="text-2xl font-bold">Latest</h1>
      <div className="space-y-4">
        {articles.map((article) => (
          <ArticleCard key={article.slug} article={article} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify against the real running dev server**

From `D:\AI-Blog\site`: start `npm run dev &`, wait for it to be ready (curl `http://localhost:3000` in a retry loop until it responds, up to ~15s), then:
```
curl -s http://localhost:3000 | grep -o '<h1[^>]*>Essential</h1>'
curl -s http://localhost:3000/latest | grep -o '<h1[^>]*>Latest</h1>'
```
Expected: both greps find a match. Also spot-check that real article titles appear: `curl -s http://localhost:3000/latest | grep -c "border-gray-200"` should print a number > 0 (roughly the count of `ArticleCard`s rendered — an `article` tag with that class per card). Stop the dev server afterward (find and kill the `next dev` process — `pkill -f "next dev"` or kill the specific PID you started).

- [ ] **Step 4: Commit**

```
git add site/src/app/page.tsx site/src/app/latest/
git commit -m "Add Essential and Latest pages"
```

---

### Task 6: Category page

**Files:**
- Create: `site/src/app/category/[category]/page.tsx`

**Interfaces:**
- Consumes: `getArticlesByCategory` from `@/lib/articles`; `CATEGORIES`, `Category` from `@/lib/types`; `ArticleCard`, `CategoryNav` from `@/components/*`
- Produces: working `/category/[category]` route for all 6 real categories, 404 for anything else

- [ ] **Step 1: Write `site/src/app/category/[category]/page.tsx`**

Next.js's dynamic route `params` API has changed across versions (in some versions it's a plain object, in newer versions it's a `Promise` that must be `await`ed). Check which convention the Task 2 scaffold actually uses by looking at whatever Next.js version landed in `site/package.json`, or by checking Next.js's own docs/changelog for that installed version, before writing this file — don't guess. The code below assumes the `Promise`-based convention (current as of recent Next.js major versions); adjust to a plain synchronous `params` object if the installed version uses that instead, and note in your report which convention was actually needed.

```tsx
import { notFound } from "next/navigation";
import ArticleCard from "@/components/ArticleCard";
import CategoryNav from "@/components/CategoryNav";
import { getArticlesByCategory } from "@/lib/articles";
import { CATEGORIES, type Category } from "@/lib/types";

export const revalidate = 900;

function isCategory(value: string): value is Category {
  return (CATEGORIES as string[]).includes(value);
}

export default async function CategoryPage({
  params,
}: {
  params: Promise<{ category: string }>;
}) {
  const { category } = await params;
  if (!isCategory(category)) {
    notFound();
  }
  const articles = await getArticlesByCategory(category);
  return (
    <div className="space-y-6">
      <CategoryNav />
      <h1 className="text-2xl font-bold">{category}</h1>
      <div className="space-y-4">
        {articles.map((article) => (
          <ArticleCard key={article.slug} article={article} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify against the real running dev server**

Start `npm run dev &` (from `D:\AI-Blog\site`), wait until ready, then:
```
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/category/coding
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/category/not-a-real-category
```
Expected: first command prints `200`, second prints `404`. Also confirm real content: `curl -s http://localhost:3000/category/coding | grep -o '<h1[^>]*>coding</h1>'` finds a match. Stop the dev server afterward.

- [ ] **Step 3: Commit**

```
git add site/src/app/category/
git commit -m "Add category filter page with 404 for unknown categories"
```

---

### Task 7: Individual post page

**Files:**
- Create: `site/src/app/post/[slug]/page.tsx`

**Interfaces:**
- Consumes: `getArticleBySlug` from `@/lib/articles`
- Produces: working `/post/[slug]` route, 404 for unknown slugs

- [ ] **Step 1: Write `site/src/app/post/[slug]/page.tsx`**

Same `params`-convention caveat as Task 6 applies here — verify against the actual installed Next.js version rather than assuming.

```tsx
import { notFound } from "next/navigation";
import { getArticleBySlug } from "@/lib/articles";

export const revalidate = 900;

export default async function PostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) {
    notFound();
  }
  return (
    <article className="space-y-4">
      <div className="text-xs text-gray-500 uppercase font-semibold">
        {article.category}
      </div>
      <h1 className="text-2xl font-bold">{article.title}</h1>
      <p className="text-gray-700">{article.summary}</p>
      <p className="text-gray-700">
        <strong>Why it matters:</strong> {article.whyItMatters}
      </p>
      <a
        href={article.sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block text-blue-600 hover:underline"
      >
        Read more at {article.sourceName} →
      </a>
    </article>
  );
}
```

- [ ] **Step 2: Verify against the real running dev server**

Start `npm run dev &` (from `D:\AI-Blog\site`), wait until ready. First get a real slug to test against:
```
npx tsx -e "
import('./src/lib/articles.ts').then(async (m) => {
  const latest = await m.getLatestArticles(1);
  console.log(latest[0]?.slug);
  process.exit(0);
});
"
```
Then, using that real slug (call it `REAL_SLUG`):
```
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/post/REAL_SLUG
curl -s http://localhost:3000/post/REAL_SLUG | grep -o 'Read more at'
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/post/definitely-not-a-real-slug-xyz
```
Expected: first command `200`, grep finds `Read more at`, third command `404`. Stop the dev server afterward.

- [ ] **Step 3: Commit**

```
git add site/src/app/post/
git commit -m "Add individual post page with 404 for unknown slugs"
```

---

### Task 8: End-to-end verification

**Files:**
- None created/modified — this task only runs and verifies existing code.

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces: confirmation that the whole site works together against real data, and that it reflects new pipeline data after a fresh run

- [ ] **Step 1: Full local run-through**

From `D:\AI-Blog\site`: `npm install` (confirm no errors on a clean install), then start `npm run dev &`, wait until ready.

- [ ] **Step 2: Exercise every route type**

```
curl -s -o /dev/null -w "Essential: %{http_code}\n" http://localhost:3000/
curl -s -o /dev/null -w "Latest: %{http_code}\n" http://localhost:3000/latest
for cat in video-gen image-gen coding research tools industry; do
  curl -s -o /dev/null -w "Category $cat: %{http_code}\n" "http://localhost:3000/category/$cat"
done
curl -s -o /dev/null -w "Unknown category: %{http_code}\n" http://localhost:3000/category/nonsense
curl -s -o /dev/null -w "Unknown post: %{http_code}\n" http://localhost:3000/post/nonsense-slug-xyz
```
Expected: `200` for Essential, Latest, and all 6 real categories; `404` for the unknown category and unknown post.

- [ ] **Step 3: Confirm Essential page content matches the DB's essential flag**

```
python -c "from pipeline.db import get_session_factory, ArticleRecord; sf = get_session_factory(); s = sf(); rows = s.query(ArticleRecord).filter(ArticleRecord.essential == True).order_by(ArticleRecord.published_at.desc()).limit(3).all(); [print(r.title) for r in rows]; s.close()"
```
Then: `curl -s http://localhost:3000/ | grep -c "border-gray-200"` — confirm the count is consistent with the number of `essential=True` rows (up to the page's limit of 20), and that at least one of the titles printed by the Python query above also appears in `curl -s http://localhost:3000/`.

- [ ] **Step 4: Confirm freshness after a new pipeline run**

Run `python -m pipeline.main` once (from `D:\AI-Blog`, real network + Gemini calls, same as every previous verification in this project). Note the printed summary's `published` count. If it's 0 (idempotent — nothing new right now), that's an acceptable outcome for this check; if it's > 0, wait for the dev server's next request (ISR will pick up fresh data on the next request after the 15-minute window, OR — since this is `npm run dev`, not a production build — Next.js dev mode typically doesn't apply the same ISR caching as a production build, so a simple page refresh should already show new data; note in your report which behavior you actually observed).

- [ ] **Step 5: Stop the dev server, run the full test suites**

Kill the `next dev` process. Run `python -m pytest -q` (from `D:\AI-Blog`) — confirm 16/16 still pass. Run `npx tsc --noEmit` (from `D:\AI-Blog\site`) — confirm no type errors across the whole site.

- [ ] **Step 6: Report final state**

No commit needed for this task (nothing changed) — just a final report confirming: all 8 routes tested return the right status code, Essential content matches the DB, freshness behavior was observed and documented, and both test suites (pytest + tsc) pass clean.
