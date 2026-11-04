"""Monte Carlo fight simulator (deferred to v1.5).

For each matchup, sample 10k synthetic fights from per-round output
distributions estimated from each fighter's history. Apply fatigue
multipliers and momentum adjustments. Aggregate to produce:

    - Distribution over winners (mean ≈ ensemble probability, but with std)
    - Distribution over methods
    - Distribution over finish round

Useful for predictive intervals and downstream uncertainty quantification.

DELIBERATELY UNIMPLEMENTED — deferred to v1.5 per docs/PLAN.md §6.7: ship the
calibrated point-estimate ensemble first, then layer the simulator. This stub
is kept so imports don't break; it is not a forgotten TODO.
"""

from __future__ import annotations


def simulate_fight(*args, **kwargs):
    """Intentionally deferred (docs/PLAN.md §6.7, v1.5). Always raises."""
    raise NotImplementedError(
        "monte_carlo.simulate_fight is intentionally deferred to v1.5 — see docs/PLAN.md §6.7"
    )
