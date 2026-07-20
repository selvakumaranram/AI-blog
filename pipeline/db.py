import os

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from pipeline import config  # noqa: F401 -- import triggers config's load_dotenv()

Base = declarative_base()


class ArticleRecord(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    canonical_url = Column(String, unique=True, nullable=False)
    source_url = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    category = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    why_it_matters = Column(Text, nullable=False)
    importance = Column(Integer, nullable=True)
    sources_count = Column(Integer, nullable=False, default=1)
    essential = Column(Boolean, nullable=False, default=False)


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL not set")
        _engine = create_engine(database_url)
    return _engine


def get_session_factory(engine=None):
    engine = engine or get_engine()
    return sessionmaker(bind=engine)


def init_db(engine=None):
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
