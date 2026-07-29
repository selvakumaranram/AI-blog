from pipeline.db import _normalize_database_url


def test_normalize_database_url_upgrades_postgresql_scheme():
    url = "postgresql://localhost:5432/dbname"
    assert _normalize_database_url(url) == "postgresql+psycopg://localhost:5432/dbname"


def test_normalize_database_url_upgrades_postgres_alias():
    url = "postgres://localhost:5432/dbname"
    assert _normalize_database_url(url) == "postgresql+psycopg://localhost:5432/dbname"


def test_normalize_database_url_leaves_driver_specific_url_unchanged():
    url = "postgresql+psycopg://localhost:5432/dbname"
    assert _normalize_database_url(url) == url


def test_normalize_database_url_leaves_non_postgres_urls_unchanged():
    url = "sqlite:///test.db"
    assert _normalize_database_url(url) == url
