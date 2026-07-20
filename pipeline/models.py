from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Category(str, Enum):
    VIDEO_GEN = "video-gen"
    IMAGE_GEN = "image-gen"
    CODING = "coding"
    RESEARCH = "research"
    TOOLS = "tools"
    INDUSTRY = "industry"


@dataclass
class Article:
    title: str
    source_url: str
    source_name: str
    published_at: datetime
    fetched_at: datetime
    source_excerpt: str = ""
    slug: str = ""
    category: Category | None = None
    summary: str = ""
    why_it_matters: str = ""
    importance: int | None = None
    sources_count: int = 1
    essential: bool = False
