"""One-time script: backfill the essential flag on already-published articles.

Run from the repo root: python -m scripts.backfill_essential_flag
Safe to re-run: it's an idempotent UPDATE, not an insert.
"""
from pipeline.db import ArticleRecord, get_session_factory


def backfill() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.query(ArticleRecord).all()
        changed = 0
        for row in rows:
            correct = row.sources_count >= 3
            if row.essential != correct:
                row.essential = correct
                changed += 1
        session.commit()
        print(f"Checked {len(rows)} rows, updated {changed}")


if __name__ == "__main__":
    backfill()
