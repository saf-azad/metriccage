"""GMM-based fighter archetype clustering + weight-class priors.

Soft clustering — each fighter gets membership probabilities across K
components, not a hard label. Most fighters are blends; "70% wrestler / 30%
striker" is a real phenotype.

PIPELINE
    1. Standardise fighter features (PER WEIGHT CLASS to avoid heavy/light bias)
    2. PCA to 10 components for noise reduction + GMM stability
    3. GMM with K in GMM_N_COMPONENTS_RANGE → pick K by minimising BIC
    4. Sanity-check with silhouette score
    5. Pickle (scaler, pca, gmm, k_chosen) → data/processed/cluster_model.pkl

WEIGHT-CLASS PRIORS (Bayesian shrinkage)
    Fighters with <3 UFC fights have noisy career stats. Pull them toward the
    division median weighted by their fight count:
        shrunk = (n / (n + n0)) * raw + (n0 / (n + n0)) * division_median
    where n0 = 3 (the prior strength). This addresses the W-BW / W-FLY blind
    spots called out in the Phase 1 error analysis.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from src.config import GMM_N_COMPONENTS_RANGE, PROCESSED, RANDOM_SEED

# Default fighter-feature columns used to derive archetype embeddings. Anything
# missing in the input frame is silently dropped — keeps the model usable while
# Track 2B columns are still rolling out.
DEFAULT_FEATURE_COLS = [
    "slpm",
    "sapm",
    "strike_net",
    "td_per15",
    "td_def_per15",
    "sub_att_per15",
    "kd_per15",
    "kd_absorbed_per15",
    "win_pct",
    "finish_rate",
    "rounds_exp",
    "reach_in",
]


@dataclass
class ClusterBundle:
    scaler: StandardScaler
    pca: PCA
    gmm: GaussianMixture
    k_chosen: int
    feature_cols: list[str]
    fighter_membership: dict[str, np.ndarray]  # fighter_id → (K,) array
    bic: float = 0.0
    silhouette: float = 0.0
    division_priors: dict[str, dict[str, float]] | None = None  # weight_class → {feature: median}

    def predict_membership(self, X: np.ndarray) -> np.ndarray:
        Xs = self.scaler.transform(X)
        Xp = self.pca.transform(Xs)
        return self.gmm.predict_proba(Xp)

    def assign_pair(self, a_id: str, b_id: str) -> tuple[np.ndarray, np.ndarray]:
        """Membership vectors for two fighters; zero-vector fallback if missing."""
        zero = np.zeros(self.k_chosen)
        return (
            self.fighter_membership.get(a_id, zero),
            self.fighter_membership.get(b_id, zero),
        )


def _select_features(fighter_features: pd.DataFrame, cols: list[str] | None) -> tuple[pd.DataFrame, list[str]]:
    cols = cols or DEFAULT_FEATURE_COLS
    available = [c for c in cols if c in fighter_features.columns]
    return fighter_features[available].fillna(0.0), available


def fit_archetype_model(
    fighter_features: pd.DataFrame,
    *,
    feature_cols: list[str] | None = None,
    pca_components: int = 10,
    save: bool = False,
) -> ClusterBundle:
    """Fit (scaler → PCA → GMM) on per-fighter features.

    `fighter_features` must include a `fighter_id` column (used to build the
    membership lookup). Optionally include `weight_class` to populate division
    priors.
    """
    fighter_features = fighter_features.copy()
    Xdf, cols = _select_features(fighter_features, feature_cols)
    if Xdf.empty:
        raise ValueError(
            f"No usable feature columns found; expected any of {DEFAULT_FEATURE_COLS}"
        )

    scaler = StandardScaler()
    Xs = scaler.fit_transform(Xdf.to_numpy(dtype=float))

    n_components = min(pca_components, Xs.shape[1])
    pca = PCA(n_components=n_components, random_state=RANDOM_SEED)
    Xp = pca.fit_transform(Xs)

    k_lo, k_hi = GMM_N_COMPONENTS_RANGE
    best_bic = float("inf")
    best_gmm = None
    best_k = k_lo
    for k in range(k_lo, k_hi + 1):
        gmm = GaussianMixture(
            n_components=k, covariance_type="full", random_state=RANDOM_SEED, n_init=2
        )
        gmm.fit(Xp)
        bic = float(gmm.bic(Xp))
        if bic < best_bic:
            best_bic = bic
            best_gmm = gmm
            best_k = k

    sil = 0.0
    if best_k >= 2 and best_gmm is not None:
        try:
            labels = best_gmm.predict(Xp)
            if len(np.unique(labels)) >= 2:
                sil = float(silhouette_score(Xp, labels))
        except Exception:
            sil = 0.0

    membership = best_gmm.predict_proba(Xp) if best_gmm is not None else np.zeros((len(Xdf), best_k))
    fighter_ids = fighter_features.get("fighter_id", pd.Series(range(len(Xdf)))).astype(str).to_numpy()
    fighter_membership = {fid: membership[i] for i, fid in enumerate(fighter_ids)}

    division_priors: dict[str, dict[str, float]] = {}
    if "weight_class" in fighter_features.columns:
        grouped = fighter_features.groupby("weight_class")
        for wc, sub in grouped:
            division_priors[str(wc)] = {c: float(sub[c].median()) for c in cols if c in sub}

    bundle = ClusterBundle(
        scaler=scaler,
        pca=pca,
        gmm=best_gmm,
        k_chosen=best_k,
        feature_cols=cols,
        fighter_membership=fighter_membership,
        bic=best_bic,
        silhouette=sil,
        division_priors=division_priors,
    )

    if save:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        with open(PROCESSED / "cluster_model.pkl", "wb") as f:
            pickle.dump(bundle, f)

    return bundle


def assign_membership(fighter_features: pd.DataFrame, bundle: ClusterBundle) -> np.ndarray:
    """Returns array shape (n_fighters, K) of membership probabilities."""
    Xdf, _ = _select_features(fighter_features, bundle.feature_cols)
    return bundle.predict_membership(Xdf.to_numpy(dtype=float))


# --- Bayesian shrinkage toward division priors -------------------------------


def shrink_toward_division(
    fighter_row: pd.Series,
    n_fights: int,
    weight_class: str,
    bundle: ClusterBundle | None,
    *,
    prior_strength: float = 3.0,
) -> pd.Series:
    """Pull a sparse fighter's stats toward their weight-class median.

    `prior_strength` = effective number of "ghost" fights at the division
    median. With n0 = 3, a fighter with 1 UFC fight → 75% prior weight, 25%
    self; a fighter with 10 UFC fights → 23% prior, 77% self. Effectively
    disappears for veteran fighters.
    """
    if bundle is None or bundle.division_priors is None:
        return fighter_row
    priors = bundle.division_priors.get(weight_class)
    if priors is None:
        return fighter_row
    n = max(0, int(n_fights))
    w_self = n / (n + prior_strength) if (n + prior_strength) > 0 else 0.0
    w_prior = 1.0 - w_self
    out = fighter_row.copy()
    for col, prior_val in priors.items():
        if col in out and pd.notna(out[col]):
            out[col] = w_self * float(out[col]) + w_prior * float(prior_val)
    return out


def aggregate_career_features(
    history: pd.DataFrame,
    fighter_id: str,
    bio: dict | None = None,
    *,
    reference_date=None,
) -> pd.Series:
    """Roll a fighter's per-fight history into a single fixed-length career vector
    suitable for GMM clustering. Imports core_features lazily to avoid a circular
    import path through src.features.
    """
    from datetime import date as _date

    from src.features import core_features as cf

    ref = reference_date or _date.today()
    out: dict[str, Any] = {
        "fighter_id": fighter_id,
        "slpm": cf.slpm(history, ref) if len(history) else 0.0,
        "sapm": cf.sapm(history, ref) if len(history) else 0.0,
        "td_per15": cf.td_accuracy(history, ref) if len(history) else 0.0,
        "td_def_per15": cf.td_defence(history, ref) if len(history) else 0.0,
        "sub_att_per15": cf.sub_avg(history, ref) if len(history) else 0.0,
        "kd_per15": cf.kd_per15(history, ref) if len(history) else 0.0,
        "kd_absorbed_per15": cf.kd_absorbed_per15(history, ref) if len(history) else 0.0,
        "win_pct": cf.win_pct(history, ref) if len(history) else 0.5,
        "finish_rate": cf.finish_rate(history) if len(history) else 0.0,
        "rounds_exp": cf.rounds_experience(history) if len(history) else 0.0,
    }
    out["strike_net"] = out["slpm"] - out["sapm"]
    if bio:
        out["reach_in"] = float(bio.get("reach_in", np.nan) or np.nan)
    return pd.Series(out)
