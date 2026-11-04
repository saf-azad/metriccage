"""Model-bundle / data loading and fighter-name resolution for the prediction API.

Owns the module-level `_State` cache: the first `_load_state()` call loads the
trained bundle, the fights/fighters parquets, replays the Elo store, and builds
per-fighter history caches. Re-loading is automatic if the bundle file mtime
changes (handy when train_all.py rewrites it while a notebook is open).
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROCESSED, ROOT
from src.features.build_matrix import _build_bio_lookup, _fight_to_perfighter_rows
from src.features.elo import MMAElo

try:  # Optional — only required if the bundle ships an LSTM stream
    import torch  # noqa: F401  (presence gates the LSTM stream)

    from src.models.career_lstm import PAST_FIGHT_DIM, FightPredictor

    _HAS_TORCH = True
except Exception:  # pragma: no cover — torch missing → ensemble silently drops LSTM
    _HAS_TORCH = False


# --- Module-level cache -----------------------------------------------------


class _State:
    """Lazy loader for the bundle, fights, fighters, Elo replay, history cache."""

    def __init__(self) -> None:
        self.bundle: dict[str, Any] | None = None
        self.bundle_mtime: float | None = None
        self.fights: pd.DataFrame | None = None
        self.fighters: pd.DataFrame | None = None
        self.bio_lookup: dict[str, Any] | None = None
        self.elo: MMAElo | None = None
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.name_index: dict[str, str] = {}  # lowercased fighter name → id
        self.method_freq: dict[str, float] = {
            "Decision": 0.50,
            "KO/TKO": 0.30,
            "Submission": 0.20,
        }
        self.cluster_model: Any = None  # populated once Track 2C lands
        self.lstm_model: Any = None  # FightPredictor (CPU) when bundle has LSTM
        self.lstm_seq_len: int = 20

    @property
    def loaded(self) -> bool:
        return self.bundle is not None and self.fights is not None


_state = _State()
_BUNDLE_PATH = PROCESSED / "final_model_bundle.pkl"
_CLUSTER_PATH = PROCESSED / "cluster_model.pkl"
_FIGHTS_PATH_V1 = ROOT / "data" / "interim" / "fights.parquet"
_FIGHTS_PATH_ENRICHED = ROOT / "data" / "interim" / "fights_enriched.parquet"
_FIGHTERS_PATH = ROOT / "data" / "interim" / "fighters.parquet"
_FEATURE_MATRIX_PATH = PROCESSED / "feature_matrix.parquet"


def _fights_path() -> Path:
    """Prefer the Track 2B enriched parquet when present (carries
    ss_attempted/td_attempted/control_time). Falls back to v1 transparently."""
    return _FIGHTS_PATH_ENRICHED if _FIGHTS_PATH_ENRICHED.exists() else _FIGHTS_PATH_V1


def _load_state(force: bool = False) -> _State:
    if not _BUNDLE_PATH.exists():
        raise FileNotFoundError(f"No model bundle at {_BUNDLE_PATH}; run scripts/train_all.py first")

    bundle_mtime = _BUNDLE_PATH.stat().st_mtime
    if (
        not force
        and _state.loaded
        and _state.bundle_mtime is not None
        and _state.bundle_mtime == bundle_mtime
    ):
        return _state

    with open(_BUNDLE_PATH, "rb") as f:
        _state.bundle = pickle.load(f)
    _state.bundle_mtime = bundle_mtime

    # Load the archetype cluster model when available — used by build_feature_row
    # to compute as-of-date cluster_a_*/cluster_b_* membership features.
    _state.cluster_model = None
    if _CLUSTER_PATH.exists():
        try:
            with open(_CLUSTER_PATH, "rb") as f:
                _state.cluster_model = pickle.load(f)
        except Exception:
            _state.cluster_model = None

    # Reconstruct the LSTM (Model C) if the bundle ships one.
    _state.lstm_model = None
    if _HAS_TORCH and _state.bundle.get("lstm_state_dict") is not None:
        cfg = _state.bundle.get("lstm_config") or {}
        seq_in = int(cfg.get("sequence_input_dim", PAST_FIGHT_DIM))
        diff_in = int(cfg.get("diff_feature_dim", len(_state.bundle["feats"])))
        m = FightPredictor(seq_in, diff_in)
        m.load_state_dict(_state.bundle["lstm_state_dict"])
        m.eval()
        _state.lstm_model = m
        _state.lstm_seq_len = int(_state.bundle.get("lstm_seq_len", 20))

    fights_path = _fights_path()
    if fights_path.exists():
        _state.fights = pd.read_parquet(fights_path).sort_values("event_date").reset_index(drop=True)
    if _FIGHTERS_PATH.exists():
        _state.fighters = pd.read_parquet(_FIGHTERS_PATH)
        _state.bio_lookup = _build_bio_lookup(_state.fighters)
        _state.name_index = {
            str(r["name"]).strip().lower(): str(r["fighter_id"])
            for _, r in _state.fighters.iterrows()
            if pd.notna(r.get("name"))
        }

    # Replay Elo + per-fighter history caches
    elo = MMAElo()
    history: dict[str, list[dict[str, Any]]] = {}
    if _state.fights is not None:
        method_counts: dict[str, int] = {}
        for fight in _state.fights.itertuples(index=False):
            fd = fight._asdict()
            ev = pd.to_datetime(fd["event_date"]).date()
            a_pf, b_pf = _fight_to_perfighter_rows(pd.Series(fd))
            history.setdefault(fd["fighter_a_id"], []).append(a_pf)
            history.setdefault(fd["fighter_b_id"], []).append(b_pf)
            winner = fd.get("winner_id")
            if winner and winner in {fd["fighter_a_id"], fd["fighter_b_id"]}:
                loser = (
                    fd["fighter_b_id"] if winner == fd["fighter_a_id"] else fd["fighter_a_id"]
                )
                method = fd.get("method_canon") or fd.get("method") or "Decision"
                elo.update(winner, loser, method, ev)
            method_counts[fd.get("method_canon", "Decision")] = (
                method_counts.get(fd.get("method_canon", "Decision"), 0) + 1
            )
        total = sum(method_counts.values()) or 1
        _state.method_freq = {
            "Decision": method_counts.get("Decision", 0) / total,
            "KO/TKO": method_counts.get("KO/TKO", 0) / total,
            "Submission": method_counts.get("Submission", 0) / total,
        }

    _state.elo = elo
    _state.history = history
    return _state


def _resolve_fighter_id(name_or_id: str, state: _State) -> str:
    if not name_or_id:
        raise ValueError("fighter name/id is required")
    nm = name_or_id.strip().lower()
    if nm in state.name_index:
        return state.name_index[nm]
    # Allow callers to pass an id directly
    if state.fighters is not None and name_or_id in set(state.fighters["fighter_id"].astype(str)):
        return name_or_id
    # Fuzzy: substring match
    matches = [
        (real_name, fid)
        for real_name, fid in state.name_index.items()
        if nm in real_name
    ]
    if len(matches) == 1:
        return matches[0][1]
    if len(matches) > 1:
        candidates = ", ".join(m[0] for m in matches[:5])
        raise LookupError(f"Ambiguous fighter '{name_or_id}': {candidates}…")
    raise LookupError(f"Fighter '{name_or_id}' not found")
