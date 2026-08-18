from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueBetAlert:
    """Everything needed to describe one value-bet opportunity to a human.
    Future modules (arb_finder, orchestrator) construct this; notifier only
    consumes it."""
    game_name: str
    team_name: str
    bookmaker: str
    decimal_odds: float
    polymarket_old_price: float
    polymarket_new_price: float
    polymarket_relative_move: float
    edge: float


@dataclass(frozen=True)
class NtfyMessage:
    title: str
    body: str
