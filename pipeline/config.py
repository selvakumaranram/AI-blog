from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # every module that needs an env var imports pipeline.config first;
# real env vars (e.g. future GH Actions secrets) win over .env since override=False.

CONTENT_DIR = Path("content")

RSS_FEEDS: list[dict[str, str]] = [
    {"name": "OpenAI Blog", "url": "https://openai.com/news/rss.xml"},
    {
        "name": "Anthropic News",
        # No official Anthropic RSS feed exists; this is a best-effort third-party
        # mirror. If it goes stale/disappears, the per-feed try/except in rss.py
        # means the rest of the pipeline is unaffected.
        "url": "https://raw.githubusercontent.com/taobojlen/anthropic-rss-feed/main/anthropic_news_rss.xml",
    },
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/"},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
]

RSS_LOOKBACK_DAYS = 3  # some feeds (e.g. OpenAI's) return their entire historical
# archive rather than just recent posts — bound volume the same way HN/GitHub are bounded.

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_KEYWORDS = ["AI", "GPT", "LLM", "OpenAI", "Anthropic", "Gemini", "machine learning"]
HN_MIN_POINTS = 50
HN_LOOKBACK_DAYS = 3

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_SEARCH_QUERY = "topic:artificial-intelligence topic:machine-learning topic:llm"
GITHUB_MIN_STARS = 50
GITHUB_LOOKBACK_DAYS = 7
GITHUB_RESULT_LIMIT = 10

TITLE_SIMILARITY_THRESHOLD = 0.85  # fallback signal, used only if embeddings are unavailable
SEMANTIC_SIMILARITY_THRESHOLD = 0.90  # primary dedupe signal (embedding cosine similarity).
# Real-data finding: true-positive scores (same story, different outlets, e.g. 0.762-0.945)
# and false-positive scores (same topic/product, different stories, e.g. 0.701-0.833) overlap
# substantially on title-only embeddings -- no threshold separates them cleanly. Set high
# (above the observed false-positive ceiling) to trade recall for precision: fewer merges,
# but avoids silently collapsing distinct stories into one. Revisit if title+excerpt embeddings
# are tried later for better separation.
SOURCE_PRIORITY = [
    "OpenAI Blog",
    "Anthropic News",
    "Google AI Blog",
    "TechCrunch AI",
    "VentureBeat AI",
    "Hacker News",
    "GitHub Trending",
]

GEMINI_MODEL_DEFAULT = "gemini-3.1-flash-lite"
GEMINI_CALL_DELAY_SECONDS = 4.0
