from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketSnapshot:
    """One poll's reading of a single NFL moneyline market."""
    market_id: str
    question: str
    tracked_outcome: str
    best_ask: float
    game_start_time: str | None


@dataclass(frozen=True)
class PriceSample:
    timestamp: datetime
    price: float


@dataclass(frozen=True)
class MoveEvent:
    """A detected >=5% relative move in a market's tracked outcome price,
    measured against the oldest sample still inside the trailing window."""
    market_id: str
    question: str
    tracked_outcome: str
    old_price: float
    new_price: float
    relative_move: float
    old_at: datetime
    new_at: datetime
