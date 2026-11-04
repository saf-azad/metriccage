"""End-to-end smoke test for `scripts/train_all.py --smoke`.

Runs the real training wiring (load → split → tiny Model A + Model B → ensemble
→ isotonic → method head → blind backtest → bundle + metrics) on a hard
subsample, and asserts it (1) exits 0, (2) prints the `SMOKE OK` summary, and
(3) leaves the PRODUCTION `final_model_bundle.pkl` byte-identical. Outputs are
redirected to a temp dir so nothing in data/processed is touched.

Marked ``requires_data`` (auto-skipped by conftest when the model bundle + a
fights parquet are absent, e.g. in CI). Kept well under a minute.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROD_BUNDLE = ROOT / "data" / "processed" / "final_model_bundle.pkl"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.requires_data
def test_smoke_runs_and_leaves_production_bundle_untouched(tmp_path: Path) -> None:
    before = _sha256(PROD_BUNDLE)

    proc = subprocess.run(
        [sys.executable, "scripts/train_all.py", "--smoke", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Merge streams: the summary is on stdout, logging on stderr.
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"smoke exited {proc.returncode}\n{output}"
    assert "SMOKE OK" in output, f"missing SMOKE OK line\n{output}"

    # Smoke wrote its artifacts to the scratch dir, not production.
    assert (tmp_path / "final_model_bundle.pkl").exists()
    assert (tmp_path / "final_model_metrics.json").exists()

    # Production bundle must be byte-identical after the smoke run.
    assert _sha256(PROD_BUNDLE) == before, "smoke run mutated the production bundle!"
