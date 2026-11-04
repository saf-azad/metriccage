"""Path helpers — keep filesystem assumptions in one place."""

from __future__ import annotations

from pathlib import Path

from src.config import INTERIM, PROCESSED, RAW


def raw_event_html(event_id: str) -> Path:
    return RAW / "events" / f"{event_id}.html"


def fights_parquet() -> Path:
    return INTERIM / "fights.parquet"


def fighters_parquet() -> Path:
    return INTERIM / "fighters.parquet"


def feature_matrix_parquet() -> Path:
    return PROCESSED / "feature_matrix.parquet"


def ensure_dirs() -> None:
    """Make sure every data subdirectory exists. Idempotent."""
    for p in [RAW, INTERIM, PROCESSED, RAW / "events", RAW / "fighters"]:
        p.mkdir(parents=True, exist_ok=True)
