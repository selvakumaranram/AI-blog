import json
import logging
import os
import re

from google import genai
from google.genai import types

from pipeline import config
from pipeline.models import Article, Category

logger = logging.getLogger(__name__)

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

SENTENCE_BOUNDARY = re.compile(r"[.!?](?:\s|$)")


class SummarizeError(Exception):
    pass


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SummarizeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def build_prompt(article: Article) -> str:
    return PROMPT_TEMPLATE.format(
        title=article.title,
        source_name=article.source_name,
        excerpt=article.source_excerpt or "(none available)",
        categories=", ".join(c.value for c in Category),
    )


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


def summarize_article(article: Article, client: genai.Client | None = None) -> Article:
    client = client or _get_client()
    model = os.environ.get("GEMINI_MODEL", config.GEMINI_MODEL_DEFAULT)
    prompt = build_prompt(article)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    temperature=0.4,
                ),
            )
            data = json.loads(resp.text)
            _validate(data)
            article.summary = data["summary"].strip()
            article.why_it_matters = data["why_it_matters"].strip()
            article.category = Category(data["category"])
            article.importance = data["importance"]
            return article
        except Exception as e:
            last_error = e
            logger.warning("summarize_attempt_failed attempt=%s title=%s error=%s", attempt, article.title, e)
    raise SummarizeError(f"failed to summarize '{article.title}': {last_error}")


if __name__ == "__main__":
    from datetime import datetime, timezone

    logging.basicConfig(level=logging.INFO)
    sample = Article(
        title="OpenAI releases a new coding-focused model",
        source_url="https://example.com/sample",
        source_name="OpenAI Blog",
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        source_excerpt="OpenAI announced a model tuned for software engineering tasks.",
    )
    result = summarize_article(sample)
    print(f"category={result.category}")
    print(f"summary={result.summary}")
    print(f"why_it_matters={result.why_it_matters}")
    print(f"importance={result.importance}")
