"""Model C — PyTorch career sequence model.

The piece the JSX blueprint didn't have. For each fighter, build a sequence of
their past-fight feature vectors (sorted by date). A small bidirectional LSTM
encodes the sequence into a fixed-size embedding. Both fighters' embeddings
are concatenated with the fight-day differential features and pushed through
an MLP head producing P(A wins).

WHY THIS HELPS
    Trees see "current Elo, current SLpM" — a snapshot. The LSTM sees the
    trajectory: was this fighter improving or declining over the last 5
    fights? That signal is invisible to point-in-time features but real for
    prediction.

CONTRACT
    Per-fight feature vector dim ~16 (decayed stats + outcomes per past fight).
    Sequences are padded to max length per batch and masked.
    Output: scalar in [0, 1].

DEFAULTS
    See LSTM_DEFAULTS in src.config. Mixed precision on CUDA when available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from src.config import LSTM_DEFAULTS, RANDOM_SEED

# --- Architecture (already designed in v1) ----------------------------------


class CareerEncoder(nn.Module):
    """Bidirectional LSTM that pools a variable-length career into a vector."""

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = int(LSTM_DEFAULTS["hidden_dim"]),
        num_layers: int = int(LSTM_DEFAULTS["num_layers"]),
        dropout: float = float(LSTM_DEFAULTS["dropout"]),
        bidirectional: bool = bool(LSTM_DEFAULTS["bidirectional"]),
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=bidirectional,
            batch_first=True,
        )
        out_dim = hidden_dim * (2 if bidirectional else 1)
        self.out_dim = out_dim

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        # Clamp to ≥1 so a fighter with no prior fights still produces a vector
        # (we feed a zero-padded "ghost" entry; the masked LSTM treats it as no signal).
        lengths_safe = torch.clamp(lengths, min=1)
        packed = nn.utils.rnn.pack_padded_sequence(
            x, lengths_safe.cpu(), batch_first=True, enforce_sorted=False
        )
        _, (h_n, _) = self.lstm(packed)
        if self.lstm.bidirectional:
            forward = h_n[-2]
            backward = h_n[-1]
            return torch.cat([forward, backward], dim=-1)
        return h_n[-1]


class FightPredictor(nn.Module):
    """Concatenate two career embeddings + differential features → P(A wins)."""

    def __init__(self, sequence_input_dim: int, diff_feature_dim: int) -> None:
        super().__init__()
        self.encoder = CareerEncoder(sequence_input_dim)
        head_in = self.encoder.out_dim * 2 + diff_feature_dim
        self.head = nn.Sequential(
            nn.Linear(head_in, 64),
            nn.ReLU(),
            nn.Dropout(LSTM_DEFAULTS["dropout"]),
            nn.Linear(64, 1),
        )

    def forward(
        self,
        a_seq: torch.Tensor,
        a_lengths: torch.Tensor,
        b_seq: torch.Tensor,
        b_lengths: torch.Tensor,
        diff_features: torch.Tensor,
    ) -> torch.Tensor:
        a_emb = self.encoder(a_seq, a_lengths)
        b_emb = self.encoder(b_seq, b_lengths)
        x = torch.cat([a_emb, b_emb, diff_features], dim=-1)
        return self.head(x).squeeze(-1)  # logits (BCEWithLogitsLoss handles sigmoid)


# --- Sequence dataset -------------------------------------------------------


# Per-past-fight feature columns (inputs to the LSTM encoder). Compact enough
# to pad to N=20 without exploding memory. The last four columns are filled
# only when the bilateral fights frame includes the Track 2B detail-page
# enrichment (ss_attempted, td_attempted, control_time); otherwise zero.
_PAST_FIGHT_COLS = [
    "winner",
    "ss_landed_self",
    "ss_landed_opp",
    "td_landed_self",
    "td_landed_opp",
    "sub_attempts_self",
    "kd_self",
    "kd_opp",
    "fight_minutes",
    "method_ko",
    "method_sub",
    "method_dec",
    "days_since",
    # Track 2B
    "ss_acc_self",        # landed/attempted (fighter)
    "ss_acc_opp",         # landed/attempted (opponent)
    "td_acc_self",        # landed/attempted (fighter)
    "control_pct_self",   # control / fight_minutes
]
PAST_FIGHT_DIM = len(_PAST_FIGHT_COLS)


def _safe_div(num: float, den: float) -> float:
    """NaN-safe division: returns 0.0 when either operand is NaN/0/None."""
    if num is None or den is None:
        return 0.0
    if pd.isna(num) or pd.isna(den):
        return 0.0
    if den <= 0:
        return 0.0
    return float(num) / float(den)


def _per_fight_vector(fight: pd.Series, ref_event_date: pd.Timestamp, role: str) -> np.ndarray:
    """Encode one past fight as a fixed-length numeric vector from the fighter's POV."""
    is_a = role == "a"
    landed_self = fight["ss_landed_a" if is_a else "ss_landed_b"]
    landed_opp = fight["ss_landed_b" if is_a else "ss_landed_a"]
    td_self = fight["td_landed_a" if is_a else "td_landed_b"]
    td_opp = fight["td_landed_b" if is_a else "td_landed_a"]
    sub_self = fight["sub_att_a" if is_a else "sub_att_b"]
    kd_self = fight["kd_a" if is_a else "kd_b"]
    kd_opp = fight["kd_b" if is_a else "kd_a"]
    minutes = float(fight.get("fight_duration_min", 0.0))
    method = str(fight.get("method_canon", fight.get("method", "")))
    method_ko = 1.0 if "KO" in method else 0.0
    method_sub = 1.0 if "Sub" in method else 0.0
    method_dec = 1.0 if "Dec" in method else 0.0
    winner_id = fight.get("winner_id")
    self_id = fight["fighter_a_id"] if is_a else fight["fighter_b_id"]
    won = 1.0 if winner_id == self_id else 0.0
    days_since = max(0, (ref_event_date - pd.to_datetime(fight["event_date"])).days)

    # Track 2B — defensible 0 fallback when the detail-page columns are absent
    ss_att_self = fight.get("ss_attempted_a" if is_a else "ss_attempted_b")
    ss_att_opp = fight.get("ss_attempted_b" if is_a else "ss_attempted_a")
    td_att_self = fight.get("td_attempted_a" if is_a else "td_attempted_b")
    ctrl_self = fight.get("control_time_a" if is_a else "control_time_b")
    ss_acc_self = _safe_div(landed_self, ss_att_self if ss_att_self is not None else 0.0)
    ss_acc_opp = _safe_div(landed_opp, ss_att_opp if ss_att_opp is not None else 0.0)
    td_acc_self = _safe_div(td_self, td_att_self if td_att_self is not None else 0.0)
    ctrl_pct_self = _safe_div(
        ctrl_self if ctrl_self is not None else 0.0, minutes * 60.0
    )

    return np.array(
        [
            won,
            float(landed_self),
            float(landed_opp),
            float(td_self),
            float(td_opp),
            float(sub_self),
            float(kd_self),
            float(kd_opp),
            minutes,
            method_ko,
            method_sub,
            method_dec,
            float(days_since) / 365.0,  # in years
            ss_acc_self,
            ss_acc_opp,
            td_acc_self,
            ctrl_pct_self,
        ],
        dtype=np.float32,
    )


class CareerSequenceDataset(Dataset):
    """For each fight, yield (a_seq, b_seq, diff_features, label).

    `fights` must be sorted by event_date ascending. `feature_matrix` is the
    diff-feature matrix produced by build_matrix.build_full_matrix().

    `past_fight_dim` slices the per-fight vector — pass 13 to match the
    legacy v1 LSTM (no Track 2B columns), 17 (default) for the v2 vector.
    """

    def __init__(
        self,
        fights: pd.DataFrame,
        feature_matrix: pd.DataFrame,
        diff_feature_cols: list[str],
        *,
        max_seq_len: int = 20,
        past_fight_dim: int = PAST_FIGHT_DIM,
    ) -> None:
        self.max_seq_len = max_seq_len
        self.past_fight_dim = past_fight_dim
        self.diff_feature_cols = diff_feature_cols
        self.diff_features = feature_matrix[diff_feature_cols].fillna(0.0).to_numpy(dtype=np.float32)
        self.labels = feature_matrix["fighter_a_won"].to_numpy(dtype=np.float32)
        self.fight_ids = feature_matrix["fight_id"].to_numpy()

        # Build per-fighter history index: fighter_id → list of (event_date, fight_row, role)
        fights = fights.sort_values("event_date").reset_index(drop=True)
        fights["event_date"] = pd.to_datetime(fights["event_date"])
        history: dict[str, list[tuple[pd.Timestamp, dict, str]]] = {}
        for f in fights.itertuples(index=False):
            d = f._asdict()
            ev = pd.to_datetime(d["event_date"])
            history.setdefault(d["fighter_a_id"], []).append((ev, d, "a"))
            history.setdefault(d["fighter_b_id"], []).append((ev, d, "b"))
        self._history = history

        # Index feature_matrix rows by (fighter_a_id, fighter_b_id, event_date) for fast lookup
        feature_matrix = feature_matrix.copy()
        feature_matrix["event_date"] = pd.to_datetime(feature_matrix["event_date"])
        self._matrix_keys: list[tuple[str, str, pd.Timestamp]] = list(
            zip(
                feature_matrix["fighter_a_id"].astype(str),
                feature_matrix["fighter_b_id"].astype(str),
                feature_matrix["event_date"],
                strict=False,
            )
        )

    def __len__(self) -> int:
        return len(self._matrix_keys)

    def _seq_for(self, fighter_id: str, role: str, ref_date: pd.Timestamp) -> np.ndarray:
        """Last `max_seq_len` past fights for fighter, oldest-first."""
        prior = [
            (ev, fight, r)
            for ev, fight, r in self._history.get(fighter_id, [])
            if ev < ref_date
        ]
        if not prior:
            return np.zeros((0, self.past_fight_dim), dtype=np.float32)
        prior = prior[-self.max_seq_len :]
        rows = [
            _per_fight_vector(pd.Series(fight), ref_date, role)[: self.past_fight_dim]
            for ev, fight, role in prior
        ]
        return np.stack(rows, axis=0)

    def __getitem__(self, idx: int) -> dict:
        a_id, b_id, ev = self._matrix_keys[idx]
        a_seq = self._seq_for(a_id, "a", ev)
        b_seq = self._seq_for(b_id, "b", ev)
        return {
            "a_seq": a_seq,
            "b_seq": b_seq,
            "diff": self.diff_features[idx],
            "label": float(self.labels[idx]),
            "fight_id": self.fight_ids[idx],
        }


def _collate(batch: list[dict]) -> dict[str, torch.Tensor]:
    # Infer the per-fight feature dim from the first non-empty sequence so the
    # collate works for both v1 (13-dim) and v2 (17-dim) datasets.
    feat_dim = PAST_FIGHT_DIM
    for b in batch:
        for key in ("a_seq", "b_seq"):
            arr = b[key]
            if arr.shape[0] > 0:
                feat_dim = arr.shape[1]
                break
        else:
            continue
        break

    def pad_seqs(seqs: list[np.ndarray]) -> tuple[torch.Tensor, torch.Tensor]:
        lengths = torch.tensor([max(1, s.shape[0]) for s in seqs], dtype=torch.long)
        max_len = max(int(lengths.max().item()), 1)
        out = torch.zeros((len(seqs), max_len, feat_dim), dtype=torch.float32)
        for i, s in enumerate(seqs):
            if s.shape[0] > 0:
                out[i, : s.shape[0]] = torch.from_numpy(s)
        return out, lengths

    a_seq, a_len = pad_seqs([b["a_seq"] for b in batch])
    b_seq, b_len = pad_seqs([b["b_seq"] for b in batch])
    diff = torch.tensor(np.stack([b["diff"] for b in batch], axis=0), dtype=torch.float32)
    label = torch.tensor([b["label"] for b in batch], dtype=torch.float32)
    return {
        "a_seq": a_seq,
        "a_lengths": a_len,
        "b_seq": b_seq,
        "b_lengths": b_len,
        "diff": diff,
        "label": label,
    }


# --- Training loop ----------------------------------------------------------


@dataclass
class LSTMTrainResult:
    model: FightPredictor
    diff_feature_cols: list[str]
    metrics: dict[str, float] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    device: str = "cpu"

    def predict_proba(self, df: pd.DataFrame, feat_cols: list[str]) -> np.ndarray:  # pragma: no cover
        """Intentional usage guard — NOT an unimplemented feature.

        The LSTM cannot score a flat feature frame: inference needs each
        fighter's padded career-sequence tensors, which live in the sequence
        dataset, not in the diff-feature matrix. This method exists only so
        train_all-style wiring that duck-types ``predict_proba`` fails loudly
        with directions instead of producing garbage. Use
        :func:`predict_model_c`, which builds the dataset and scores correctly.
        """
        raise NotImplementedError("Use predict_model_c with the dataset to score new fights.")


def _label_smoothed_bce(
    logits: torch.Tensor, target: torch.Tensor, smoothing: float
) -> torch.Tensor:
    target = target * (1 - smoothing) + 0.5 * smoothing
    return nn.functional.binary_cross_entropy_with_logits(logits, target)


def train_model_c(
    train_fights: pd.DataFrame,
    val_fights: pd.DataFrame,
    feat_cols: list[str],
    *,
    full_fights: pd.DataFrame | None = None,
    feature_matrix_full: pd.DataFrame | None = None,
    epochs: int | None = None,
    batch_size: int | None = None,
    seq_len: int = 20,
) -> LSTMTrainResult:
    """Training loop with AdamW + cosine LR + linear warmup + label smoothing.

    Inputs:
        train_fights / val_fights — slices of the diff-feature matrix
                                    (must include fight_id, event_date, fighter_*_id)
        feat_cols                 — the diff feature columns to feed the head
        full_fights               — bilateral fights parquet (needed for sequences);
                                    falls back to data/interim/fights.parquet
        feature_matrix_full       — full diff matrix (for joining sequence index);
                                    defaults to concat of train+val
    """
    torch.manual_seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    if full_fights is None:
        from src.config import ROOT

        enriched = ROOT / "data" / "interim" / "fights_enriched.parquet"
        path = enriched if enriched.exists() else ROOT / "data" / "interim" / "fights.parquet"
        full_fights = pd.read_parquet(path)

    if feature_matrix_full is None:
        feature_matrix_full = pd.concat([train_fights, val_fights], ignore_index=True)

    # Detect whether the input fights frame carries Track 2B columns. If yes
    # we feed the full 17-dim per-fight vector; otherwise the 13-dim legacy.
    pfd = PAST_FIGHT_DIM if "ss_attempted_a" in full_fights.columns else 13
    train_ds = CareerSequenceDataset(
        full_fights, train_fights.reset_index(drop=True), feat_cols,
        max_seq_len=seq_len, past_fight_dim=pfd,
    )
    val_ds = CareerSequenceDataset(
        full_fights, val_fights.reset_index(drop=True), feat_cols,
        max_seq_len=seq_len, past_fight_dim=pfd,
    )

    bs = int(batch_size or LSTM_DEFAULTS["batch_size"])
    n_epochs = int(epochs or LSTM_DEFAULTS["epochs"])
    train_loader = DataLoader(train_ds, batch_size=bs, shuffle=True, collate_fn=_collate)
    val_loader = DataLoader(val_ds, batch_size=bs, shuffle=False, collate_fn=_collate)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = FightPredictor(pfd, len(feat_cols)).to(device)

    optim = torch.optim.AdamW(
        model.parameters(),
        lr=LSTM_DEFAULTS["lr"],
        weight_decay=LSTM_DEFAULTS["weight_decay"],
    )
    total_steps = max(1, len(train_loader) * n_epochs)
    warmup_steps = max(1, int(total_steps * LSTM_DEFAULTS["warmup_pct"]))

    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return step / warmup_steps
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return 0.5 * (1 + np.cos(np.pi * progress))

    sched = torch.optim.lr_scheduler.LambdaLR(optim, lr_lambda)

    history: list[dict] = []
    best_val = float("inf")
    best_state: dict[str, Any] | None = None

    for epoch in range(n_epochs):
        model.train()
        train_loss_sum = 0.0
        n = 0
        for batch in train_loader:
            optim.zero_grad()
            logits = model(
                batch["a_seq"].to(device),
                batch["a_lengths"].to(device),
                batch["b_seq"].to(device),
                batch["b_lengths"].to(device),
                batch["diff"].to(device),
            )
            loss = _label_smoothed_bce(
                logits, batch["label"].to(device), LSTM_DEFAULTS["label_smoothing"]
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optim.step()
            sched.step()
            train_loss_sum += float(loss.item()) * batch["label"].size(0)
            n += batch["label"].size(0)

        train_loss = train_loss_sum / max(1, n)

        # ---- validation ----
        model.eval()
        val_loss_sum, vn = 0.0, 0
        all_p, all_y = [], []
        with torch.no_grad():
            for batch in val_loader:
                logits = model(
                    batch["a_seq"].to(device),
                    batch["a_lengths"].to(device),
                    batch["b_seq"].to(device),
                    batch["b_lengths"].to(device),
                    batch["diff"].to(device),
                )
                loss = _label_smoothed_bce(
                    logits, batch["label"].to(device), LSTM_DEFAULTS["label_smoothing"]
                )
                val_loss_sum += float(loss.item()) * batch["label"].size(0)
                vn += batch["label"].size(0)
                all_p.append(torch.sigmoid(logits).cpu().numpy())
                all_y.append(batch["label"].numpy())
        val_loss = val_loss_sum / max(1, vn)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    # Final val metrics
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    p = np.concatenate(all_p) if all_p else np.zeros(0)
    y = np.concatenate(all_y) if all_y else np.zeros(0)
    metrics: dict[str, float] = {"val_loss": float(best_val)}
    if len(y) > 0:
        metrics.update(
            {
                "val_logloss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))),
                "val_brier": float(brier_score_loss(y, p)),
                "val_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else 0.5,
            }
        )

    return LSTMTrainResult(
        model=model.cpu(), diff_feature_cols=feat_cols, metrics=metrics, history=history, device=device
    )


def predict_model_c(
    result: LSTMTrainResult,
    fights_full: pd.DataFrame,
    feature_matrix: pd.DataFrame,
    *,
    seq_len: int = 20,
    batch_size: int = 256,
) -> np.ndarray:
    """Score every row of `feature_matrix` and return P(A wins) as a numpy array."""
    # Probe the LSTM to see what input dim it was trained with so we can
    # match it (v1 used 13-dim per-fight vectors, v2 uses 17).
    try:
        pfd = result.model.encoder.lstm.input_size
    except Exception:
        pfd = PAST_FIGHT_DIM if "ss_attempted_a" in fights_full.columns else 13
    ds = CareerSequenceDataset(
        fights_full, feature_matrix.reset_index(drop=True), result.diff_feature_cols,
        max_seq_len=seq_len, past_fight_dim=pfd,
    )
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, collate_fn=_collate)
    model = result.model.eval()
    out: list[np.ndarray] = []
    with torch.no_grad():
        for batch in loader:
            logits = model(
                batch["a_seq"], batch["a_lengths"], batch["b_seq"], batch["b_lengths"], batch["diff"]
            )
            out.append(torch.sigmoid(logits).numpy())
    return np.concatenate(out) if out else np.zeros(0)
