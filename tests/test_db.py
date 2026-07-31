from pipeline.db import _normalize_database_url, get_engine


def test_normalize_database_url_upgrades_plain_postgres_scheme():
    assert (
        _normalize_database_url("postgres://user:pass@localhost/dbname")
        == "postgresql+psycopg://user:pass@localhost/dbname"
    )


def test_normalize_database_url_upgrades_plain_postgresql_scheme():
    assert (
        _normalize_database_url("postgresql://user:pass@localhost/dbname")
        == "postgresql+psycopg://user:pass@localhost/dbname"
    )


def test_normalize_database_url_preserves_explicit_psycopg_scheme():
    url = "postgresql+psycopg://user:pass@localhost/dbname"
    assert _normalize_database_url(url) == url


def test_get_engine_raises_when_database_url_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import pipeline.db as db

    db._engine = None
    try:
        try:
            get_engine()
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass
    finally:
        db._engine = None
