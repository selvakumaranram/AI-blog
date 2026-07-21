from datetime import datetime, timezone

from pipeline.models import Article, Category
from pipeline.publish import _record_from_article, generate_slug


def test_generate_slug_lowercases_and_hyphenates():
    assert generate_slug("OpenAI Ships GPT-5") == "openai-ships-gpt-5"


def test_generate_slug_collapses_punctuation_to_single_hyphens():
    assert generate_slug("Wow!! A big / weird -- title??") == "wow-a-big-weird-title"


def test_generate_slug_strips_leading_and_trailing_hyphens():
    assert generate_slug("---Leading and trailing---") == "leading-and-trailing"


def test_generate_slug_caps_length_at_80_chars():
    long_title = "word " * 40
    slug = generate_slug(long_title)
    assert len(slug) <= 80
    assert not slug.endswith("-")


def test_generate_slug_handles_empty_result():
    assert generate_slug("!!!???") == "untitled"


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
