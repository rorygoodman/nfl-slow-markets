"""Pure value-bet edge math. See the design spec for the formula's
derivation — this is the whole reason the tool exists."""

from __future__ import annotations


def value_bet_edge(decimal_odds: float, true_prob: float) -> float:
    """Expected value per £1 staked, backing this bookmaker price against
    `true_prob` (the reference "fair" probability — this project always
    uses Polymarket's post-move sell-side price for this). Positive means
    a value bet; negative means the bookmaker price is worse than fair."""
    return decimal_odds * true_prob - 1
