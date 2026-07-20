# AI Pulse — Automated AI News Blog

An automated blog that aggregates the latest AI news (video generation, image generation, coding tools, trending GitHub repos, research papers), summarizes each item with an LLM in an original voice, and publishes it — with downstream content repurposing for LinkedIn, Instagram, and YouTube.

**Core principle:** Aggregate → Summarize → Add value → Link out. Every post is a short original summary + why it matters + a link to the source. We never rewrite or republish someone else's article. This keeps the site legal, SEO-safe, and genuinely useful.

---

## What visitors see

Two main pages:

| Page | Purpose | Logic |
|------|---------|-------|
| **Essential** | The must-know stories | Ranked by importance score (multi-source coverage + HN points + LLM importance rating 1–10) |
| **Latest** | Everything recent | Chronological feed |

Both pages support category filters: `video-gen`, `image-gen`, `coding`, `research`, `tools`, `industry`.

---

## Architecture

```
┌─────────────────────────── PIPELINE (Python, runs on GitHub Actions cron) ───────────────────────────┐
│                                                                                                      │
│  FETCHERS ──────────► DEDUPE ──────► SUMMARIZER ──────► RANKER ──────► PUBLISHER                     │
│  - RSS feeds          (URL +         (LLM: 3-sentence   (LLM scores    (writes rows to               │
│  - Hacker News API     title          summary, "why      importance     Supabase Postgres,           │
│  - GitHub trending     similarity)    it matters",       1–10)          triggers site rebuild)       │
│  - arXiv API                          category tag)                                                  │
│  - Reddit API                                                                                        │
│  - YouTube Data API                                                                                  │
│                                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────── WEBSITE (Next.js, hosted free on Vercel) ────────────────────────────────┐
│  /            → Essential page (top-ranked stories)                                                  │
│  /latest      → Chronological feed                                                                   │
│  /category/*  → Filtered views                                                                       │
│  /post/[slug] → Individual story page (summary + source link)                                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────── DISTRIBUTION (Phase 4 — draft generation only) ──────────────────────────┐
│  - LinkedIn post drafts        (from day's top stories)                                              │
│  - Instagram carousel text                                                                           │
│  - YouTube script: "Top 5 AI updates today" (hook → segments → outro)                                │
│  Human reviews and posts manually. No auto-posting.                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Pipeline | Python 3.11+ | Scheduled script, no server needed |
| Scheduler | GitHub Actions (cron, every 6h) | Free |
| LLM | Claude API (Haiku-class) or Gemini free tier | Summaries + scoring, pennies/day |
| Storage | Supabase Postgres free tier — single `articles` table (via SQLAlchemy) | Zero cost, managed Postgres |
| Frontend | Next.js (App Router) | React + server rendering for SEO |
| Hosting | Vercel free tier | Zero cost, auto-deploy on push |
| Styling | Tailwind CSS | Fast, consistent |

**Budget: ₹0 infrastructure. Only LLM API calls (~30 articles/day = trivial cost).**

---

## Repository structure

```
.
├── README.md                  ← you are here
├── CLAUDE.md                  ← Claude Code project instructions
├── .claude/skills/            ← project skills (already built)
├── pipeline/                  ← Python aggregation pipeline
│   ├── fetchers/
│   │   ├── rss.py             # RSS feeds (OpenAI, Anthropic, Google AI, TechCrunch AI, VentureBeat AI)
│   │   ├── hackernews.py      # HN API — AI-related stories above points threshold
│   │   ├── github_trending.py # Trending AI/ML repos
│   │   ├── arxiv.py           # cs.AI / cs.CL / cs.CV recent papers
│   │   └── youtube.py         # Top AI channels via YouTube Data API
│   ├── dedupe.py              # URL canonicalization + title similarity
│   ├── summarize.py           # LLM: summary, why-it-matters, category
│   ├── rank.py                # LLM importance score + source-coverage boost
│   ├── db.py                  # SQLAlchemy engine/session + ArticleRecord model (Postgres)
│   ├── publish.py             # Persists articles to Postgres via db.py
│   ├── models.py              # Article dataclass / schema
│   ├── config.py              # Feed lists, thresholds, categories
│   └── main.py                # Orchestrates: fetch → dedupe → summarize → rank → publish
├── site/                      ← Next.js app
│   ├── app/
│   │   ├── page.tsx           # Essential page
│   │   ├── latest/page.tsx
│   │   ├── category/[cat]/page.tsx
│   │   └── post/[slug]/page.tsx
│   └── lib/content.ts         # Reads articles from Postgres
├── distribution/              ← Phase 4: repurposing agents
│   ├── linkedin.py
│   ├── instagram.py
│   └── youtube_script.py
├── .github/workflows/
│   └── pipeline.yml           # Cron: runs pipeline/main.py every 6 hours
├── requirements.txt
└── .env.example               # ANTHROPIC_API_KEY / GEMINI_API_KEY, YOUTUBE_API_KEY
```

---

## Article schema

Every article (a row in the Postgres `articles` table) has:

```yaml
title: string            # Original headline, shortened if needed
slug: string             # kebab-case, unique
source_url: string       # REQUIRED — link to original
source_name: string      # e.g. "Hacker News", "OpenAI Blog"
published_at: ISO date   # When the source published it
fetched_at: ISO date     # When our pipeline picked it up
category: enum           # video-gen | image-gen | coding | research | tools | industry
summary: string          # 3 sentences, original wording
why_it_matters: string   # 1–2 sentences
importance: int          # 1–10 (LLM-scored)
sources_count: int       # How many feeds covered this story (dedupe merge count)
essential: bool          # importance >= 7 OR sources_count >= 3
```

---

## Phased roadmap & current status

- [x] **Phase 0 — Planning.** Concept, stack, and phases decided. Claude Code skills built.
- [ ] **Phase 1 — Pipeline MVP (Weeks 1–2).** ← **WE ARE HERE — START NEXT**
  - [ ] `models.py` + `config.py` with 5–10 RSS feeds
  - [ ] Fetchers: RSS + Hacker News + GitHub trending (arXiv/Reddit/YouTube can wait)
  - [ ] Dedupe by canonical URL + fuzzy title match
  - [ ] Summarizer: one LLM call per article → summary, why-it-matters, category
  - [ ] Output markdown files to `content/`
  - [ ] Run manually; verify output quality on real data
- [ ] **Phase 2 — Website (Weeks 3–4).**
  - [ ] Next.js app: Essential, Latest, category, post pages
  - [ ] Reads markdown from `content/`
  - [ ] Deploy to Vercel
- [ ] **Phase 3 — Full automation (Weeks 5–6).**
  - [ ] GitHub Actions cron every 6 hours
  - [ ] Ranker agent: importance scoring → Essential page selection
  - [ ] Auto-commit content → Vercel auto-rebuild
- [ ] **Phase 4 — Distribution.**
  - [ ] LinkedIn draft generator, Instagram caption generator
  - [ ] YouTube script generator: daily "Top 5 AI updates" (hook, segments, outro)
  - [ ] Human review before posting — no auto-posting
- [ ] **Phase 5 — Growth.**
  - [ ] Newsletter (Buttondown/Beehiiv free tier)
  - [ ] SEO pages, sitemap, OG images
  - [ ] Monetization via sponsorships once traffic exists

---

## What Claude should do next

1. **Start Phase 1.** Build `pipeline/` in the order listed above. Small, testable modules — one fetcher at a time, each runnable standalone (`python -m pipeline.fetchers.rss`).
2. **Prove quality before quantity.** After the first end-to-end run, stop and show sample output for human review before adding more sources.
3. **Keep it free.** No paid services, no persistent servers — Supabase Postgres (free tier) is already in use for storage as of Phase 1.
4. **Never plagiarize.** Summaries must be original wording. Always store and display `source_url`. If an LLM summary looks like a close paraphrase of the source, regenerate it.
5. **Update this README.** When a phase item is completed, tick its checkbox in the roadmap so the next session knows the true state.

## Hard rules

- Every published article MUST link to its original source.
- Summaries are max 3 sentences; why-it-matters is max 2 sentences.
- No auto-posting to social platforms — drafts only, human approves.
- Secrets only via environment variables; never commit keys. `.env` is gitignored.
- Pipeline must be idempotent: re-running must not duplicate articles (dedupe on canonical URL).
- All timestamps stored in UTC (ISO 8601).

## Running locally

```bash
# Pipeline
pip install -r requirements.txt
cp .env.example .env       # set GEMINI_API_KEY and DATABASE_URL (Postgres, postgresql+psycopg:// scheme); GITHUB_TOKEN optional
python -m pipeline.main    # full run → persists new articles to Postgres

# Site
cd site
npm install
npm run dev                # http://localhost:3000
```