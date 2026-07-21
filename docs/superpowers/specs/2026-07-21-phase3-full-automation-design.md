# Phase 3 — Full Automation: Design

## Context

The README's roadmap marks Phase 3 as next: GitHub Actions cron every 6 hours, a ranker agent for importance scoring feeding the Essential page, and (per the original roadmap wording) "auto-commit content → Vercel auto-rebuild." That last bullet is stale — it described the retired markdown-file architecture. The site now reads Postgres directly with 15-minute ISR (`revalidate = 900` in `site/src/app/*/page.tsx`), so no commit-triggered rebuild is needed once the site is deployed to Vercel (deployment itself remains a separate, already-tracked Phase 2 item the user is doing themselves).

This plan covers the two real pieces of remaining Phase 3 scope: importance scoring and unattended scheduled runs.

## Decisions (confirmed with user)

- **Scoring method:** extend the existing `summarize.py` Gemini structured-output call to also return `importance`, rather than a second dedicated LLM call or a rule-based heuristic. Zero additional API calls per article — important given the free-tier's tight per-day quota already observed (embedding calls hit a 1000/day ceiling during earlier testing).
- **Repo secrets:** the assistant writes the GitHub Actions workflow file; the user adds the actual secret values (`GEMINI_API_KEY`, `DATABASE_URL`, optionally `GITHUB_TOKEN`) via GitHub repo Settings themselves. The assistant does not have and will not request the user's live key values for this purpose.
- **Backfill:** skip. The 167 articles already in the DB keep `importance = NULL` and whatever `essential` value they already have (`sources_count >= 3` only). Only articles processed from this point forward get real importance scores. Saves ~167 Gemini calls against the free-tier quota; can be revisited later as a separate one-time script if wanted.

## Architecture

Three independent, additive changes. No new pipeline modules — this extends `summarize.py` and `publish.py` in place, plus adds one new CI workflow file.

### 1. Importance scoring — `pipeline/summarize.py`

The current `RESPONSE_SCHEMA` requires `summary`, `why_it_matters`, `category`. Add a fourth required field:

```python
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "category": {"type": "string", "enum": [c.value for c in Category]},
        "importance": {"type": "integer"},
    },
    "required": ["summary", "why_it_matters", "category", "importance"],
}
```

`PROMPT_TEMPLATE` gains scoring guidance so the model has a consistent rubric across calls (a bare "rate 1-10" invites drift):

```
- "importance": an integer 1-10 rating how significant this news is to an AI-interested \
reader, using this rubric: 1-3 = niche or minor (small tool update, incremental release), \
4-6 = notable (meaningful feature, funding round, solid research result), 7-8 = significant \
(major product launch, notable model release, widely-relevant industry shift), 9-10 = major \
or breaking (industry-defining announcement, landmark research, major acquisition).
```

`_validate()` gains a range/type check, following the same pattern as the existing sentence-count checks (raise `ValueError` on violation, caught by the existing retry-once loop in `summarize_article`):

```python
def _validate(data: dict) -> None:
    for field in ("summary", "why_it_matters", "category"):
        if not data.get(field, "").strip():
            raise ValueError(f"empty field: {field}")
    if len(SENTENCE_BOUNDARY.findall(data["summary"])) > 3:
        raise ValueError("summary exceeds 3 sentences")
    if len(SENTENCE_BOUNDARY.findall(data["why_it_matters"])) > 2:
        raise ValueError("why_it_matters exceeds 2 sentences")
    importance = data.get("importance")
    if not isinstance(importance, int) or isinstance(importance, bool) or not (1 <= importance <= 10):
        raise ValueError(f"importance out of range: {importance!r}")
```

(`isinstance(importance, bool)` guard: in Python, `bool` is a subclass of `int`, and Gemini's JSON `true`/`false` could in principle decode to a Python `bool` if the model ever emits a boolean by mistake — this rejects that case explicitly rather than silently treating `True` as `1`.)

`summarize_article` sets `article.importance = data["importance"]` alongside the existing three field assignments, inside the same `try` block, before `return article`.

### 2. Essential formula — `pipeline/publish.py`

`_record_from_article` currently hardcodes:

```python
essential=article.sources_count >= 3,
```

Change to match the README's already-documented target formula:

```python
essential=(article.importance is not None and article.importance >= 7) or article.sources_count >= 3,
```

No other changes to `publish.py` — `article.importance` already flows through from `models.py`'s `Article` dataclass and is already read into `ArticleRecord(importance=article.importance, ...)` on the line above (unchanged).

### 3. GitHub Actions cron — `.github/workflows/pipeline.yml` (new file)

```yaml
name: Pipeline

on:
  schedule:
    - cron: "0 */6 * * *"
  workflow_dispatch:

concurrency:
  group: pipeline-cron
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m pipeline.main
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GEMINI_MODEL: ${{ secrets.GEMINI_MODEL }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          GITHUB_TOKEN: ${{ secrets.GH_TRENDING_TOKEN }}
```

Notes:
- `concurrency` with `cancel-in-progress: false` means if a run is still going (e.g. sleeping through an embedding-quota 429 retry) when the next 6-hour trigger fires, the new run queues instead of overlapping or being killed mid-write.
- `permissions: contents: read` — the pipeline only writes to Postgres, never to git, so no write scope is needed (this is a deliberate tightening vs. GitHub Actions' default `read/write` token).
- `GEMINI_MODEL` secret is optional — `config.py`'s `GEMINI_MODEL_DEFAULT` already covers it if the secret is unset (empty string), matching local-dev behavior in `.env`.
- The trending fetcher's env var is named `GITHUB_TOKEN` in `pipeline/fetchers/github_trending.py` and `.env`, but **`GITHUB_TOKEN` is a reserved name automatically populated by GitHub Actions itself** (a repo-scoped token, different purpose/permissions than a personal token used for Search API rate limits). To avoid colliding with that reserved name, the workflow sources the value from a differently-named repo secret (`GH_TRENDING_TOKEN`) and maps it to the `GITHUB_TOKEN` env var the pipeline code expects at runtime. This is a repo secret the user creates, not the automatic Actions token.
- `timeout-minutes: 20` is a safety net — the pipeline currently runs in well under a minute per the local runs observed, but a stuck retry-sleep loop or hung network call shouldn't be able to run indefinitely on a schedule.

### 4. Docs — `Readme.md`

- Tick the "GitHub Actions cron every 6 hours" and "Ranker agent: importance scoring → Essential page selection" checkboxes under Phase 3.
- Reword the "Auto-commit content → Vercel auto-rebuild" bullet to reflect current architecture — replace with a note that ISR (15-min revalidation) already handles freshness once deployed, so no commit-triggered rebuild step exists or is needed; leave it unchecked since Vercel deployment itself is still pending (tracked under Phase 2).
- Update the `essential` field schema comment (`pipeline/models.py`'s docstring-equivalent note in the README, currently `importance >= 7 OR sources_count >= 3 (interim: sources_count only, until Phase 3 adds importance)`) to drop the "(interim...)" parenthetical, since real `importance` now exists.

## Testing

Pure-function unit tests only, matching this project's existing testing philosophy (Phase 1's plan explicitly scoped tests to pure, I/O-free functions — no Gemini/DB mocking, since faithful mocks would be speculative robustness ahead of need):

- **New `tests/test_summarize.py`:** unit tests for `_validate()`'s new importance checks — accepts `importance` in range 1-10, rejects missing, rejects out-of-range (0, 11), rejects non-int (string, float), rejects `bool`. No network/client involved — `_validate()` is a pure function over a dict.
- **Extend `tests/test_publish.py`:** unit tests for `_record_from_article`'s new essential formula — `importance=8, sources_count=1` → `essential=True`; `importance=None, sources_count=3` → `essential=True`; `importance=5, sources_count=1` → `essential=False`; `importance=None, sources_count=1` → `essential=False`. `_record_from_article` is a pure function (builds an `ArticleRecord` from an `Article`, no I/O), so this is testable directly without a real DB session.

## Out of scope (explicitly not building now)

- Backfilling `importance` for the 167 existing articles (user's choice — separate future script if wanted).
- Deploying the site to Vercel (already tracked separately; user is doing this themselves).
- Any change to the ranker's inputs beyond title/source/excerpt already available to `summarize_article` — no cross-article comparison, no trending-signal weighting.
- Adding the actual GitHub repo secrets — the user does this manually after the workflow file is merged.
