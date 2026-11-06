"""Make sure a populated database exists before the dashboard reads it."""

from __future__ import annotations

from pathlib import Path

from isn_engagement import etl, seed


def ensure_database(db_path: Path, raw_dir: Path, report_path: Path | None = None) -> bool:
    """Build ``db_path`` from ``raw_dir`` if it does not exist yet.

    Generates the synthetic seed exports first when ``raw_dir`` has none.
    Returns True if a build happened, False if the database was already there.
    """
    if db_path.exists() and db_path.stat().st_size > 0:
        return False
    if not (raw_dir / "members.csv").exists():
        seed.generate(raw_dir)
    etl.run(raw_dir, db_path, report_path)
    return True
