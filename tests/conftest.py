"""Shared pytest configuration.

Provides the ``requires_data`` marker (registered in pyproject.toml, which runs
with ``--strict-markers``): tests carrying it are auto-skipped when the local
data/model artifacts they depend on are absent — e.g. in CI, where parquet and
pickle files are gitignored and never checked out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_BUNDLE = ROOT / "data" / "processed" / "final_model_bundle.pkl"
_FIGHTS = ROOT / "data" / "interim" / "fights.parquet"
_FIGHTS_ENRICHED = ROOT / "data" / "interim" / "fights_enriched.parquet"


def _data_available() -> bool:
    """True when the model bundle and a fights parquet both exist locally."""
    return _BUNDLE.exists() and (_FIGHTS.exists() or _FIGHTS_ENRICHED.exists())


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if _data_available():
        return
    skip_missing_data = pytest.mark.skip(
        reason=(
            "local data artifacts missing: needs data/processed/final_model_bundle.pkl "
            "and data/interim/fights.parquet (or fights_enriched.parquet)"
        )
    )
    for item in items:
        if "requires_data" in item.keywords:
            item.add_marker(skip_missing_data)
