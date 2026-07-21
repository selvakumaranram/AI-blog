# Running AI Pulse locally

Both halves of the project — the Python pipeline and the Next.js site — read/write the same Supabase Postgres `articles` table. Verified working end-to-end on 2026-07-21 (167 real rows in the DB, all 9 site routes returning correct status codes, both test suites passing).

## Prerequisites

- Python 3.11+ (tested on 3.14)
- Node.js 18+ (tested on v24.18.0) and npm
- A Supabase project with a Postgres database already created (the `articles` table is created automatically by the pipeline the first time it runs — no manual schema setup needed)
- A free Gemini API key from https://aistudio.google.com/apikey
- Optionally, a GitHub personal access token (raises the GitHub Search API rate limit from 10 req/min to 30 req/min; the pipeline works without one)

## 1. Backend (pipeline)

```bash
# from the repo root
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in:
- `GEMINI_API_KEY` — from the link above
- `GEMINI_MODEL` — already defaults to a working model (`gemini-3.1-flash-lite`); Gemini periodically retires model names for new API keys, so if you get a `404 ... no longer available to new users` error, list your key's actually-available models and pick a current one:
  ```bash
  python -c "
  import pipeline.config, os
  from google import genai
  client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
  for m in client.models.list():
      if 'generateContent' in (m.supported_actions or []):
          print(m.name)
  "
  ```
- `DATABASE_URL` — your Supabase connection string. **Must use the `postgresql+psycopg://` scheme** (not `postgresql://`) so SQLAlchemy picks the psycopg 3 driver. Get the base string from Supabase's dashboard → Project Settings → Database → Connection string → URI, then add `+psycopg` after `postgresql`.
- `GITHUB_TOKEN` — optional, leave blank to skip.

Run it:

```bash
python -m pipeline.main
```

Expected output: a line like `Fetched 145 -> deduped 143 -> 1 new -> 1 published, 0 failed`. Re-running immediately should show `0 new -> 0 published` (idempotency — it won't re-publish articles already in the DB).

Run the tests:

```bash
python -m pytest -q
```

Expected: `16 passed`.

**Known noisy-but-harmless things:**
- A `DeprecationWarning` from inside the `google-genai` library itself on every pytest run — pre-existing, unrelated to this project's code, safe to ignore.
- Gemini's embedding API (used for cross-outlet duplicate detection) has a fairly tight free-tier quota — both a per-minute limit and a per-day limit (1000 embedding calls/day at the time of writing). If you hit either, you'll see a `429 RESOURCE_EXHAUSTED` warning in the log; the pipeline automatically retries once after 60s for a per-minute limit, and falls back to a weaker (but still functional) title-similarity check if embeddings are unavailable at all. This is expected resilience behavior, not a bug — the pipeline still completes and publishes correctly either way.

## 2. Frontend (Next.js site)

```bash
cd site
npm install
cp .env.example .env.local
```

Edit `site/.env.local` and add:
```
DATABASE_URL=postgresql://<same connection details as the backend's .env, but WITHOUT the +psycopg suffix>
```
(The `postgres` npm package wants a plain `postgresql://` URL — the `+psycopg` driver suffix is SQLAlchemy-specific and will break the Node client if left in.)

Run it:

```bash
npm run dev
```

Then visit:
- http://localhost:3000/ — Essential (top stories from 3+ sources; may show "No essential stories yet" if nothing currently qualifies — that's real data, not a bug)
- http://localhost:3000/latest — chronological feed of everything
- http://localhost:3000/category/coding (or `video-gen`, `image-gen`, `research`, `tools`, `industry`)
- http://localhost:3000/post/<any-slug-from-the-latest-page> — individual article

Type-check the whole site:

```bash
npx tsc --noEmit
```

Expected: no output (no errors).

**Stopping the dev server on Windows:** `pkill -f "next dev"` from Git Bash often doesn't actually kill it — Git Bash's PID and the real Windows PID holding the port can differ. If `curl http://localhost:3000` still responds after `pkill`, find the real PID and force-kill it directly:
```bash
netstat -ano | grep ":3000" | grep LISTENING   # note the PID in the last column
taskkill //F //PID <that-pid>
```

## 3. Verifying both sides agree

Since they share one database, you can sanity-check the site is showing real pipeline output:

```bash
# from the repo root, after running the pipeline
python -c "
from pipeline.db import get_session_factory, ArticleRecord
sf = get_session_factory()
s = sf()
print('total articles:', s.query(ArticleRecord).count())
print('essential:', s.query(ArticleRecord).filter(ArticleRecord.essential == True).count())
s.close()
"
```
Compare the `total articles` count against what `/latest` shows (capped at 50 per page by design), and the `essential` count against what's on `/`.

## Project layout recap

- `pipeline/` — the Python fetch → dedupe → summarize → publish pipeline (run manually or on a schedule; see `Readme.md` for the full architecture)
- `site/` — the Next.js app (this is what you deploy to Vercel separately; deployment isn't covered here, see `Readme.md`'s tech stack section)
- Both read/write the same Postgres `articles` table — there's no API layer between them, and no shared code (by design, so they can eventually live in separate repos).
