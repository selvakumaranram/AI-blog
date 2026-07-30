from pipeline import db


def test_normalize_database_url_adds_psycopg_driver_for_postgresql_scheme():
    url = "postgresql://db.example.com:5432/aiblog"
    assert db._normalize_database_url(url) == "postgresql+psycopg://db.example.com:5432/aiblog"


def test_normalize_database_url_adds_psycopg_driver_for_postgres_scheme():
    url = "postgres://db.example.com:5432/aiblog"
    assert db._normalize_database_url(url) == "postgresql+psycopg://db.example.com:5432/aiblog"


def test_normalize_database_url_keeps_explicit_driver_scheme():
    url = "postgresql+psycopg://db.example.com:5432/aiblog"
    assert db._normalize_database_url(url) == url
