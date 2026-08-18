from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import MoveEvent, PriceSample

DEFAULT_WINDOW = timedelta(minutes=10)
DEFAULT_THRESHOLD = 0.05


@dataclass
class _MarketState:
    first_seen_at: datetime
    samples: "deque[PriceSample]" = field(default_factory=deque)


class MoveDetector:
    """Tracks each market's trailing price window and flags a >=5%
    relative move (5% of the prior price), measured against the oldest
    sample still inside the trailing window. A market needs a full
    window of observation history before it can trigger."""

    def __init__(self, window: timedelta = DEFAULT_WINDOW, threshold: float = DEFAULT_THRESHOLD):
        self._window = window
        self._threshold = threshold
        self._states: dict[str, _MarketState] = {}

    def observe(
        self,
        market_id: str,
        question: str,
        tracked_outcome: str,
        price: float,
        now: datetime,
        game_start_time: "str | None" = None,
    ) -> MoveEvent | None:
        state = self._states.get(market_id)
        if state is None:
            state = _MarketState(first_seen_at=now)
            self._states[market_id] = state

        cutoff = now - self._window
        while state.samples and state.samples[0].timestamp < cutoff:
            state.samples.popleft()
        reference = state.samples[0] if state.samples else None

        state.samples.append(PriceSample(timestamp=now, price=price))

        if now - state.first_seen_at < self._window or reference is None:
            return None
        if reference.price <= 0:
            return None  # guards div-by-zero on malformed upstream data

        relative_move = abs(price - reference.price) / reference.price
        if relative_move < self._threshold:
            return None

        return MoveEvent(
            market_id=market_id,
            question=question,
            tracked_outcome=tracked_outcome,
            old_price=reference.price,
            new_price=price,
            relative_move=relative_move,
            old_at=reference.timestamp,
            new_at=now,
            game_start_time=game_start_time,
        )
