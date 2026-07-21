# Phase 3 — Full Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-scored importance (1-10) to the summarization step, use it in the Essential-page selection formula, and run the pipeline unattended every 6 hours via GitHub Actions.

**Architecture:** Three independent, additive changes to the existing pipeline — no new pipeline modules. `summarize.py`'s existing structured-output Gemini call gains a fourth required field (`importance`). `publish.py`'s existing `essential` computation switches from `sources_count >= 3` alone to `(importance >= 7) or (sources_count >= 3)`. A new GitHub Actions workflow runs `python -m pipeline.main` on a cron schedule plus manual dispatch.

**Tech Stack:** Python 3.11+, `google-genai` SDK (already in use), `pytest`, GitHub Actions (`ubuntu-latest`, `actions/setup-python@v5`).

## Global Constraints

- No backfill of the 167 existing DB rows — they keep `importance = NULL` and their current `essential` value. Only articles processed after this change get real importance scores.
- The importance score comes from the **same** Gemini call that already produces `summary`/`why_it_matters`/`category` — do not add a second LLM call.
- `essential` formula: `(importance is not None and importance >= 7) or sources_count >= 3` — exact formula, matches `Readme.md`'s already-documented target.
- GitHub Actions workflow must not request `contents: write` — the pipeline writes to Postgres only, never to git.
- The workflow must **not** reference a secret literally named `GITHUB_TOKEN` for the GitHub Search API token — GitHub reserves the `GITHUB_` prefix for secret names and repo-secret creation with that name is rejected. Use `GH_TRENDING_TOKEN` as the repo secret name, mapped to the `GITHUB_TOKEN` env var at run time (the pipeline code reads `os.environ["GITHUB_TOKEN"]`, unchanged).
- Tests stay pure-function / I/O-free, matching the existing suite's style (no Gemini client mocking, no live DB in tests) — see `tests/test_dedupe.py` and `tests/test_publish.py` for the established pattern.

---

### Task 1: Importance scoring in the summarizer

**Files:**
- Modify: `pipeline/summarize.py`
- Create: `tests/test_summarize.py`

**Interfaces:**
- Consumes: `pipeline.models.Article` (existing, has `importance: int | None = None` field already), `pipeline.models.Category` (existing enum).
- Produces: `pipeline.summarize._validate(data: dict) -> None` now also validates an `"importance"` key (raises `ValueError` on violation) — Task 2 does not depend on this function directly, but the overall pipeline behavior downstream (real non-null `importance` values reaching `publish.py`) depends on this task's change to `summarize_article`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_summarize.py`:

```python
import pytest

from pipeline.summarize import _validate


def _base_data(**overrides):
    data = {
        "summary": "One. Two. Three.",
        "why_it_matters": "It matters.",
        "category": "coding",
        "importance": 5,
    }
    data.update(overrides)
    return data


def test_validate_accepts_importance_in_range():
    _validate(_base_data(importance=1))
    _validate(_base_data(importance=5))
    _validate(_base_data(importance=10))


def test_validate_rejects_missing_importance():
    data = _base_data()
    del data["importance"]
    with pytest.raises(ValueError):
        _validate(data)


def test_validate_rejects_importance_below_range():
    with pytest.raises(ValueError):
        _validate(_base_data(importance=0))


def test_validate_rejects_importance_above_range():
    with pytest.raises(ValueError):
        _validate(_base_data(importance=11))


def test_validate_rejects_non_int_importance():
    with pytest.raises(ValueError):
        _validate(_base_data(importance="7"))
    with pytest.raises(ValueError):
        _validate(_base_data(importance=7.5))


def test_validate_rejects_bool_importance():
    with pytest.raises(ValueError):
        _validate(_base_data(importance=True))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_summarize.py -v`

Expected: all 6 tests FAIL. The `importance`-specific tests fail because `_validate` doesn't check that key yet (no error raised where one is expected, or vice versa) — `test_validate_accepts_importance_in_range` should currently PASS (importance is simply ignored), but the four `rejects_*` tests must currently FAIL since nothing raises for those inputs today.

- [ ] **Step 3: Update `RESPONSE_SCHEMA` and `PROMPT_TEMPLATE`**

In `pipeline/summarize.py`, replace:

```python
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "category": {"type": "string", "enum": [c.value for c in Category]},
    },
    "required": ["summary", "why_it_matters", "category"],
}

PROMPT_TEMPLATE = """You write for "AI Pulse", an AI news blog that aggregates and summarizes AI news \
in fully original wording. You never copy phrases verbatim from the source.

Source title: {title}
Publisher: {source_name}
Source excerpt (may be partial or empty): {excerpt}

Return a JSON object with exactly these fields:
- "summary": exactly 3 sentences, original wording, describing what was announced/happened. Never copy \
phrases from the excerpt.
- "why_it_matters": 1-2 sentences on why an AI-interested reader should care.
- "category": exactly one of {categories}.

Do not invent facts beyond what the title/excerpt imply. Be concise and factual, not promotional."""
```

with:

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

PROMPT_TEMPLATE = """You write for "AI Pulse", an AI news blog that aggregates and summarizes AI news \
in fully original wording. You never copy phrases verbatim from the source.

Source title: {title}
Publisher: {source_name}
Source excerpt (may be partial or empty): {excerpt}

Return a JSON object with exactly these fields:
- "summary": exactly 3 sentences, original wording, describing what was announced/happened. Never copy \
phrases from the excerpt.
- "why_it_matters": 1-2 sentences on why an AI-interested reader should care.
- "category": exactly one of {categories}.
- "importance": an integer 1-10 rating how significant this news is to an AI-interested reader, using \
this rubric: 1-3 = niche or minor (small tool update, incremental release), 4-6 = notable (meaningful \
feature, funding round, solid research result), 7-8 = significant (major product launch, notable model \
release, widely-relevant industry shift), 9-10 = major or breaking (industry-defining announcement, \
landmark research, major acquisition).

Do not invent facts beyond what the title/excerpt imply. Be concise and factual, not promotional."""
```

- [ ] **Step 4: Update `_validate`**

Replace:

```python
def _validate(data: dict) -> None:
    for field in ("summary", "why_it_matters", "category"):
        if not data.get(field, "").strip():
            raise ValueError(f"empty field: {field}")
    if len(SENTENCE_BOUNDARY.findall(data["summary"])) > 3:
        raise ValueError("summary exceeds 3 sentences")
    if len(SENTENCE_BOUNDARY.findall(data["why_it_matters"])) > 2:
        raise ValueError("why_it_matters exceeds 2 sentences")
```

with:

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

(The `isinstance(importance, bool)` check exists because `bool` is a subclass of `int` in Python — this rejects a stray JSON `true`/`false` instead of silently treating `True` as `1`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_summarize.py -v`

Expected: all 6 tests PASS.

- [ ] **Step 6: Wire `importance` into `summarize_article` and the smoke-test block**

In `pipeline/summarize.py`, inside `summarize_article`, replace:

```python
            data = json.loads(resp.text)
            _validate(data)
            article.summary = data["summary"].strip()
            article.why_it_matters = data["why_it_matters"].strip()
            article.category = Category(data["category"])
            return article
```

with:

```python
            data = json.loads(resp.text)
            _validate(data)
            article.summary = data["summary"].strip()
            article.why_it_matters = data["why_it_matters"].strip()
            article.category = Category(data["category"])
            article.importance = data["importance"]
            return article
```

And in the `if __name__ == "__main__":` block at the bottom of the file, replace:

```python
    result = summarize_article(sample)
    print(f"category={result.category}")
    print(f"summary={result.summary}")
    print(f"why_it_matters={result.why_it_matters}")
```

with:

```python
    result = summarize_article(sample)
    print(f"category={result.category}")
    print(f"summary={result.summary}")
    print(f"why_it_matters={result.why_it_matters}")
    print(f"importance={result.importance}")
```

- [ ] **Step 7: Run the full test suite**

Run: `python -m pytest -q`

Expected: all tests pass (previous 16 + 6 new = 22 passed), no regressions in `test_dedupe.py` or `test_publish.py`.

- [ ] **Step 8: Commit**

```bash
git add pipeline/summarize.py tests/test_summarize.py
git commit -m "Add LLM-scored importance to the summarizer"
```

---

### Task 2: Essential-flag formula in publish.py

**Files:**
- Modify: `pipeline/publish.py`
- Modify: `tests/test_publish.py`

**Interfaces:**
- Consumes: `pipeline.models.Article` (existing, `importance: int | None` and `sources_count: int` fields), `pipeline.db.ArticleRecord` (existing, has `essential` column).
- Produces: `pipeline.publish._record_from_article(article, slug, canonical_url) -> ArticleRecord` — signature unchanged, only the `essential` value it computes changes. No other task depends on this function's internals beyond what's already used by `publish_article` (unchanged in this task).

- [ ] **Step 1: Write the failing tests**

In `tests/test_publish.py`, add these imports at the top (below the existing `from pipeline.publish import generate_slug` line, replace that single import line with the block below):

```python
from datetime import datetime, timezone

from pipeline.models import Article, Category
from pipeline.publish import _record_from_article, generate_slug
```

Then append this helper and these tests to the end of the file:

```python
def _make_article(**overrides):
    defaults = dict(
        title="Sample title",
        source_url="https://example.com/a",
        source_name="Example",
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        category=Category.CODING,
        summary="Summary.",
        why_it_matters="Matters.",
        importance=None,
        sources_count=1,
    )
    defaults.update(overrides)
    return Article(**defaults)


def test_essential_true_when_importance_at_least_seven():
    article = _make_article(importance=8, sources_count=1)
    record = _record_from_article(article, "slug", "https://example.com/a")
    assert record.essential is True


def test_essential_true_when_sources_count_at_least_three():
    article = _make_article(importance=None, sources_count=3)
    record = _record_from_article(article, "slug", "https://example.com/a")
    assert record.essential is True


def test_essential_false_when_neither_threshold_met():
    article = _make_article(importance=5, sources_count=1)
    record = _record_from_article(article, "slug", "https://example.com/a")
    assert record.essential is False


def test_essential_false_when_importance_none_and_low_sources_count():
    article = _make_article(importance=None, sources_count=1)
    record = _record_from_article(article, "slug", "https://example.com/a")
    assert record.essential is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_publish.py -v`

Expected: the 5 pre-existing `generate_slug` tests PASS; `test_essential_true_when_importance_at_least_seven` FAILS (current code only checks `sources_count >= 3`, so `essential` is `False` when `importance=8, sources_count=1`). The other 3 new tests should currently PASS (they only involve `sources_count`, unaffected by this task's change) — that's expected; Step 2 confirms only the one genuinely-changing case fails before the fix.

- [ ] **Step 3: Update the essential formula**

In `pipeline/publish.py`, inside `_record_from_article`, replace:

```python
        essential=article.sources_count >= 3,
```

with:

```python
        essential=(article.importance is not None and article.importance >= 7) or article.sources_count >= 3,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_publish.py -v`

Expected: all 9 tests (5 existing + 4 new) PASS.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -q`

Expected: all 26 tests pass (22 from Task 1 + 4 new), no regressions.

- [ ] **Step 6: Commit**

```bash
git add pipeline/publish.py tests/test_publish.py
git commit -m "Use importance>=7 OR sources_count>=3 for the essential flag"
```

---

### Task 3: GitHub Actions cron workflow and README updates

**Files:**
- Create: `.github/workflows/pipeline.yml`
- Modify: `Readme.md`

**Interfaces:**
- Consumes: `pipeline/main.py`'s `run()` entry point (invoked via `python -m pipeline.main`, unchanged), the env vars already read by `pipeline/config.py` and `pipeline/db.py` (`GEMINI_API_KEY`, `GEMINI_MODEL`, `DATABASE_URL`) and `pipeline/fetchers/github_trending.py` (`GITHUB_TOKEN`).
- Produces: nothing consumed by later tasks — this is the final task in the plan.

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/pipeline.yml`:

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

- [ ] **Step 2: Verify the workflow YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/pipeline.yml')); print('valid yaml')"`

Expected output: `valid yaml`

(`PyYAML` is already a project dependency per `requirements.txt` — no install needed.)

- [ ] **Step 3: Update `Readme.md`'s roadmap checkboxes**

In `Readme.md`, replace:

```markdown
- [ ] **Phase 3 — Full automation (Weeks 5–6).**
  - [ ] GitHub Actions cron every 6 hours
  - [ ] Ranker agent: importance scoring → Essential page selection
  - [ ] Auto-commit content → Vercel auto-rebuild
```

with:

```markdown
- [ ] **Phase 3 — Full automation (Weeks 5–6).**
  - [x] GitHub Actions cron every 6 hours
  - [x] Ranker agent: importance scoring → Essential page selection
  - [ ] ~~Auto-commit content → Vercel auto-rebuild~~ — not needed: the site reads Postgres directly with 15-minute ISR (`revalidate = 900`), so there's no commit-triggered rebuild step. Once deployed, Vercel serves fresh content automatically as ISR revalidates.
```

(Phase 3's own heading checkbox stays unchecked — Vercel deployment, tracked under Phase 2, is still pending.)

- [ ] **Step 4: Update `Readme.md`'s `essential` field schema note**

In `Readme.md`, replace:

```markdown
essential: bool          # importance >= 7 OR sources_count >= 3 (interim: sources_count only, until Phase 3 adds importance)
```

with:

```markdown
essential: bool          # importance >= 7 OR sources_count >= 3
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/pipeline.yml Readme.md
git commit -m "Add GitHub Actions cron workflow; update README for Phase 3"
```

---

## Post-plan manual step (not part of any task — for the user, not an agentic worker)

After this plan is merged, add three repo secrets under GitHub → repo Settings → Secrets and variables → Actions:
- `GEMINI_API_KEY`
- `DATABASE_URL` (same value as the pipeline's local `.env`, `postgresql+psycopg://` scheme)
- `GH_TRENDING_TOKEN` (optional — a GitHub personal access token; omitting it just means the trending fetcher runs unauthenticated at a lower rate limit, same as local dev without `GITHUB_TOKEN` set)

`GEMINI_MODEL` is optional to set as a secret — if omitted, the workflow's env var resolves to an empty string and `pipeline/config.py`'s `GEMINI_MODEL_DEFAULT` is used, same as local `.env` behavior.
