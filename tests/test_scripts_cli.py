"""Argparse-wiring smoke tests for the canonical script CLIs.

The ``--help`` cases need no data (argparse exits before any bundle/data load),
so they run everywhere including CI. The end-to-end ``predict.py`` case is marked
``requires_data`` and auto-skipped when the model artifacts are absent.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_ENV = {**os.environ, "PYTHONPATH": str(ROOT)}


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=_ENV,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.parametrize(
    "script",
    ["scripts/predict.py", "scripts/backtest.py", "scripts/build_features.py",
     "scripts/train_all.py"],
)
def test_cli_help_exits_zero(script: str) -> None:
    proc = _run([script, "--help"], timeout=30)
    assert proc.returncode == 0, f"{script} --help exited {proc.returncode}\n{proc.stderr}"
    assert "usage" in proc.stdout.lower()


def test_predict_requires_a_and_b() -> None:
    # Missing required args -> argparse error (exit 2), no data load needed.
    proc = _run(["scripts/predict.py"], timeout=30)
    assert proc.returncode == 2
    assert "required" in proc.stderr.lower()


def test_predict_rejects_bad_date() -> None:
    proc = _run(
        ["scripts/predict.py", "--a", "X", "--b", "Y", "--date", "not-a-date"], timeout=30
    )
    assert proc.returncode == 2
    assert "yyyy-mm-dd" in proc.stderr.lower()


@pytest.mark.requires_data
def test_predict_end_to_end_json() -> None:
    proc = _run(
        [
            "scripts/predict.py",
            "--a", "Islam Makhachev",
            "--b", "Charles Oliveira",
            "--date", "2025-04-12",
            "--weight-class", "Lightweight",
            "--json",
        ],
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["fighter_a"] == "Islam Makhachev"
    assert payload["fighter_b"] == "Charles Oliveira"
    assert "winner_prob" in payload
