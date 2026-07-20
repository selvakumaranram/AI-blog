from datetime import datetime, timedelta, timezone

from pipeline.dedupe import canonicalize_url, cosine_similarity, deduplicate, titles_similar
from pipeline.models import Article

NOW = datetime.now(timezone.utc)


def make_article(title, source_url, source_name, published_offset_minutes=0):
    return Article(
        title=title,
        source_url=source_url,
        source_name=source_name,
        published_at=NOW + timedelta(minutes=published_offset_minutes),
        fetched_at=NOW,
    )


def test_canonicalize_url_strips_tracking_params():
    url = "https://Example.com/post?utm_source=x&gclid=y&id=1"
    assert canonicalize_url(url) == "https://example.com/post?id=1"


def test_canonicalize_url_normalizes_www_scheme_and_trailing_slash():
    assert canonicalize_url("http://www.Example.com/post/") == canonicalize_url("https://example.com/post")


def test_canonicalize_url_sorts_remaining_query_params():
    a = canonicalize_url("https://example.com/post?b=2&a=1")
    b = canonicalize_url("https://example.com/post?a=1&b=2")
    assert a == b


def test_titles_similar_true_positive_on_reworded_headline():
    a = "OpenAI launches GPT-5 for developers"
    b = "GPT-5 launches for developers, OpenAI announces"
    assert titles_similar(a, b)


def test_titles_similar_true_negative_on_unrelated_headlines():
    a = "OpenAI launches GPT-5 for developers"
    b = "Google releases a new image generation model"
    assert not titles_similar(a, b)


def test_cosine_similarity_identical_direction_is_one():
    assert cosine_similarity([1.0, 0.0], [2.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_deduplicate_merges_same_canonical_url():
    # Deliberately dissimilar embeddings — canonical URL match must win regardless.
    def fake_embed(texts):
        return [[1.0, 0.0], [0.0, 1.0]]

    articles = [
        make_article("OpenAI ships GPT-5", "https://openai.com/blog/gpt-5?utm_source=hn", "OpenAI Blog"),
        make_article("A completely different headline", "https://openai.com/blog/gpt-5", "Hacker News"),
    ]
    result = deduplicate(articles, embed_fn=fake_embed)
    assert len(result) == 1
    assert result[0].sources_count == 2


def test_deduplicate_merges_when_embeddings_are_semantically_similar():
    # Different URLs, differently-worded titles (as real cross-outlet headlines are) —
    # merge should be driven by embedding similarity, not by the title text itself.
    def fake_embed(texts):
        return [[1.0, 0.0], [0.95, 0.312]]  # cosine ~0.95, above the 0.90 threshold

    articles = [
        make_article(
            "Apple sues OpenAI, accuses ex-employees of stealing trade secrets",
            "https://news.ycombinator.com/item?id=1",
            "Hacker News",
        ),
        make_article(
            "Apple's lawsuit couldn't come at a worse time for OpenAI",
            "https://techcrunch.com/apple-lawsuit",
            "TechCrunch AI",
        ),
    ]
    result = deduplicate(articles, embed_fn=fake_embed)
    assert len(result) == 1
    assert result[0].sources_count == 2


def test_deduplicate_keeps_distinct_articles_separate():
    def fake_embed(texts):
        return [[1.0, 0.0], [0.0, 1.0]]  # cosine 0.0, well below threshold

    articles = [
        make_article("OpenAI ships GPT-5", "https://openai.com/blog/gpt-5", "OpenAI Blog"),
        make_article("Google releases Gemini 4", "https://blog.google/gemini-4", "Google AI Blog"),
    ]
    result = deduplicate(articles, embed_fn=fake_embed)
    assert len(result) == 2
    assert all(a.sources_count == 1 for a in result)


def test_deduplicate_falls_back_to_title_similarity_when_embeddings_fail():
    def failing_embed(texts):
        raise RuntimeError("embedding API unavailable")

    articles = [
        make_article(
            "OpenAI launches GPT-5 for developers", "https://openai.com/blog/gpt-5", "OpenAI Blog"
        ),
        make_article(
            "GPT-5 launches for developers, OpenAI announces",
            "https://news.ycombinator.com/item?id=1",
            "Hacker News",
        ),
    ]
    result = deduplicate(articles, embed_fn=failing_embed)
    assert len(result) == 1
    assert result[0].sources_count == 2
