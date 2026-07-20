from pipeline.publish import generate_slug


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
