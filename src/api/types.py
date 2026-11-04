"""Public prediction types and their rendering helpers.

`FightPrediction` is the frozen public contract returned by
`src.api.predict_fight.predict_fight` (field names may not change — see
the project's frozen API contract). The markdown/dict renderers live on the
dataclass so consumers only ever need the one object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

Confidence = Literal["high", "medium", "low"]


# --- Plain-English translations ---------------------------------------------


_FEATURE_LABELS: dict[str, str] = {
    "elo_diff": "Elo rating",
    "elo_prob_a": "Elo win probability",
    "slpm_diff": "Striking output (sig. strikes / min)",
    "sapm_diff": "Striking absorbed",
    "strike_net_diff": "Net striking (output minus absorbed)",
    "td_per15_diff": "Takedown rate",
    "td_def_per15_diff": "Takedown defence",
    "sub_att_per15_diff": "Submission threat",
    "kd_per15_diff": "Knockdown rate",
    "kd_absorbed_per15_diff": "Chin (knockdowns absorbed)",
    "win_pct_diff": "Recent win percentage",
    "finish_rate_diff": "Career finish rate",
    "rounds_exp_diff": "Championship-round experience",
    "streak_diff": "Current win streak",
    "days_inactive_diff": "Layoff (days since last fight)",
    "layoff_signed": "Layoff (days since last fight)",
    "n_fights_a": "UFC fights (A)",
    "n_fights_b": "UFC fights (B)",
    "reach_diff": "Reach",
    "age_diff": "Age",
    "stance_mismatch": "Stance matchup (orthodox vs southpaw)",
    "elo_x_streak": "Elo × streak interaction",
    "slpm_x_sapm": "Striking exchange ratio",
    "year_idx": "Era index",
    "slpm_adj_diff": "Era-adjusted striking output",
    "absorption_ratio_diff": "Strikes absorbed ratio",
    "reach_x_slpm": "Reach × striking output",
    "grappler_index_diff": "Grappling index",
    "grappling_mismatch": "Grappling vs striking matchup",
    "sub_threat_diff": "Submission threat index",
    "recent3_wr_diff": "Recent 3-fight win rate",
    "ko_loss_recency_diff": "Recent KO losses",
    "is_rematch": "Rematch indicator",
    "long_streak_flag_diff": "Long-streak flag",
    "champ_round_exp_diff": "Championship-round experience",
}


def _humanise(feature: str, value: float) -> str:
    """Plain-English driver line for the markdown card."""
    label = _FEATURE_LABELS.get(feature, feature.replace("_", " ").title())
    if abs(value) < 1e-9:
        magnitude = "neutral"
    elif feature == "elo_diff":
        magnitude = f"{int(round(value))} Elo points"
    elif "diff" in feature:
        magnitude = f"diff {value:+.2f}"
    else:
        magnitude = f"{value:+.2f}"
    return f"{label} ({magnitude})"


# --- FightPrediction --------------------------------------------------------


@dataclass
class FightPrediction:
    """Output of `predict_fight`. The two-name interface is the public contract."""

    fighter_a: str
    fighter_b: str
    event_date: date
    winner_prob: dict[str, float]
    method_prob: dict[str, float]
    round_estimate: tuple[int, int] | None
    confidence: Confidence
    top_drivers: list[str] = field(default_factory=list)
    cluster_matchup: str = ""
    warnings: list[str] = field(default_factory=list)

    # Optional deeper details
    fighter_a_id: str = ""
    fighter_b_id: str = ""
    weight_class: str = ""
    event_name: str = ""
    confidence_spread: float = 0.0
    ensemble_streams: dict[str, float] = field(default_factory=dict)
    key_advantages_a: list[str] = field(default_factory=list)
    key_advantages_b: list[str] = field(default_factory=list)
    finish_round_dist: dict[str, float] = field(default_factory=dict)
    n_similar_fights: int = 0
    cluster_a: str = ""
    cluster_b: str = ""

    # ----- Card rendering helpers (per skills/fight_card_markdown.md) ------

    @staticmethod
    def _render_probability_bar(probability: float, width: int = 24) -> str:
        probability = max(0.0, min(1.0, float(probability)))
        filled = int(round(probability * width))
        empty = width - filled
        return "█" * filled + "░" * empty

    @staticmethod
    def _classify_confidence(spread: float) -> Confidence:
        if spread <= 0.04:
            return "high"
        elif spread <= 0.10:
            return "medium"
        return "low"

    @staticmethod
    def _render_method_breakdown(method_probs: dict[str, float], width: int = 24) -> str:
        """Legacy compact 3-way method bar — kept for backwards compatibility."""
        d = method_probs.get("Decision", method_probs.get("decision", 0.0))
        k = method_probs.get("KO/TKO", method_probs.get("ko", 0.0))
        s = method_probs.get("Submission", method_probs.get("submission", 0.0))
        chars_d = int(round(d * width))
        chars_k = int(round(k * width))
        chars_s = int(round(s * width))
        total = chars_d + chars_k + chars_s
        chars_s += width - total
        chars_s = max(chars_s, 0)
        bar = "D" * chars_d + "K" * chars_k + "S" * chars_s
        return f"[{bar.ljust(width, '·')}]"

    @staticmethod
    def _compute_top_outcomes(
        prob_a: float,
        method_probs: dict[str, float],
        fighter_a: str,
        fighter_b: str,
        top_n: int = 4,
    ) -> list[dict[str, Any]]:
        """Decompose (P(winner) × P(method)) into 6 fighter×method outcomes; return top N.

        Independence assumption: P(A by M) ≈ P(A wins) × P(M). This is the standard
        approximation when method-conditional-on-winner isn't separately modeled.
        Returns a list of dicts: {label, fighter, method, prob}, sorted descending.
        """
        prob_b = 1.0 - prob_a
        d = float(method_probs.get("Decision", method_probs.get("decision", 0.0)))
        k = float(method_probs.get("KO/TKO", method_probs.get("ko", 0.0)))
        s = float(method_probs.get("Submission", method_probs.get("submission", 0.0)))

        outcomes: list[dict[str, Any]] = [
            {"fighter": fighter_a, "method": "Decision",   "prob": prob_a * d},
            {"fighter": fighter_a, "method": "KO/TKO",     "prob": prob_a * k},
            {"fighter": fighter_a, "method": "Submission", "prob": prob_a * s},
            {"fighter": fighter_b, "method": "Decision",   "prob": prob_b * d},
            {"fighter": fighter_b, "method": "KO/TKO",     "prob": prob_b * k},
            {"fighter": fighter_b, "method": "Submission", "prob": prob_b * s},
        ]
        for o in outcomes:
            short = o["fighter"].split()[-1] if " " in o["fighter"] else o["fighter"]
            o["label"] = f"{short} by {o['method']}"
        outcomes.sort(key=lambda o: -o["prob"])
        return outcomes[:top_n]

    @staticmethod
    def _render_outcome_bar(prob: float, width: int = 20) -> str:
        """Bar scaled to absolute probability (0..1 maps to 0..width chars)."""
        p = max(0.0, min(1.0, float(prob)))
        filled = int(round(p * width))
        return "█" * filled + "░" * (width - filled)

    @staticmethod
    def _render_round_prediction(finish_round_dist: dict[str, float]) -> str:
        if not finish_round_dist:
            return "Unclear"
        decision_prob = finish_round_dist.get("decision", 0.0)
        rounds = {k: v for k, v in finish_round_dist.items() if k.startswith("round_")}
        r2_r3 = rounds.get("round_2", 0.0) + rounds.get("round_3", 0.0)
        if decision_prob >= 0.40:
            return f"Decision ({decision_prob*100:.0f}%)"
        if r2_r3 >= 0.30:
            return f"Round 2–3 ({r2_r3*100:.0f}%)"
        if rounds:
            top = max(rounds, key=lambda k: rounds[k])
            return f"{top.replace('_', ' ').title()} ({rounds[top]*100:.0f}%)"
        return "Unclear"

    def to_markdown(self) -> str:
        """Plain-text fight card per skills/fight_card_markdown.md."""
        prob_a = float(self.winner_prob.get("a", 0.5))
        prob_b = float(self.winner_prob.get("b", 1 - prob_a))
        conf = self.confidence.upper()
        spread_pp = self.confidence_spread * 100

        bar_a = self._render_probability_bar(prob_a)
        bar_b = self._render_probability_bar(prob_b)
        round_line = self._render_round_prediction(self.finish_round_dist)
        top_outcomes = self._compute_top_outcomes(
            prob_a, self.method_prob, self.fighter_a, self.fighter_b, top_n=4
        )

        title_bits = [self.event_name or "UFC", self.weight_class or "—", str(self.event_date)]
        title = " · ".join(b for b in title_bits if b)

        lines = [
            "═══════════════════════════════════════════════════════════",
            f"  {self.fighter_a} vs. {self.fighter_b}",
            f"  {title}",
            "═══════════════════════════════════════════════════════════",
            "",
            "  WHO WINS?",
            f"  {self.fighter_a:<14}  {bar_a}   {prob_a*100:.0f}%",
            f"  {self.fighter_b:<14}  {bar_b}   {prob_b*100:.0f}%",
            "",
            f"  Confidence: {conf}  (ensemble spread: ±{spread_pp:.0f} pp)",
            "",
        ]

        if self.method_prob and top_outcomes:
            top_sum = sum(o["prob"] for o in top_outcomes)
            lines += [
                "  HOW DOES IT END?  (top 4 outcomes — together " + f"{top_sum*100:.0f}% of probability)",
            ]
            for i, o in enumerate(top_outcomes, 1):
                bar = self._render_outcome_bar(o["prob"])
                lines.append(f"  {i}. {o['label']:<32} {bar}  {o['prob']*100:>4.0f}%")
            lines += [
                f"  IF FINISHED — {round_line}",
                "",
            ]

        favoured = self.fighter_a if prob_a >= prob_b else self.fighter_b
        favoured_advs = self.key_advantages_a if prob_a >= prob_b else self.key_advantages_b
        if favoured_advs:
            lines.append(f"  WHY IS {favoured.upper()} FAVOURED?")
            for adv in favoured_advs[:4]:
                lines.append(f"    • {adv}")
            lines.append("")

        if self.warnings:
            lines.append("  WARNINGS")
            for w in self.warnings[:3]:
                lines.append(f"    ⚠ {w}")
            lines.append("")

        lines += [
            f"  Model uncertainty: {conf.lower()}  |  n similar fights in training: {self.n_similar_fights}",
            "  Not betting advice. This model is wrong ~40% of the time.",
            "═══════════════════════════════════════════════════════════",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialisable view for json fixtures / dashboards."""
        prob_a = float(self.winner_prob.get("a", 0.5))
        top_outcomes = self._compute_top_outcomes(
            prob_a, self.method_prob, self.fighter_a, self.fighter_b, top_n=4
        )
        return {
            "fighter_a": self.fighter_a,
            "fighter_b": self.fighter_b,
            "fighter_a_id": self.fighter_a_id,
            "fighter_b_id": self.fighter_b_id,
            "event_date": self.event_date.isoformat(),
            "event_name": self.event_name,
            "weight_class": self.weight_class,
            "winner_prob": self.winner_prob,
            "method_prob": self.method_prob,
            "top_outcomes": top_outcomes,
            "round_estimate": list(self.round_estimate) if self.round_estimate else None,
            "confidence": self.confidence,
            "confidence_spread": self.confidence_spread,
            "ensemble_streams": self.ensemble_streams,
            "top_drivers": self.top_drivers,
            "key_advantages_a": self.key_advantages_a,
            "key_advantages_b": self.key_advantages_b,
            "warnings": self.warnings,
            "cluster_matchup": self.cluster_matchup,
            "cluster_a": self.cluster_a,
            "cluster_b": self.cluster_b,
            "finish_round_dist": self.finish_round_dist,
            "n_similar_fights": self.n_similar_fights,
        }
