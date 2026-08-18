"""Serialize/deserialize a MoveEvent to cross the subprocess boundary as
a single JSON string CLI argument (orchestrator/main.py's
trigger_pipeline spawns orchestrator/pipeline.py with this string)."""

from __future__ import annotations

import json
from datetime import datetime

from polymarket_monitor.models import MoveEvent


def move_event_to_json(event: MoveEvent) -> str:
    return json.dumps(
        {
            "market_id": event.market_id,
            "question": event.question,
            "tracked_outcome": event.tracked_outcome,
            "old_price": event.old_price,
            "new_price": event.new_price,
            "relative_move": event.relative_move,
            "old_at": event.old_at.isoformat(),
            "new_at": event.new_at.isoformat(),
            "game_start_time": event.game_start_time,
        }
    )


def move_event_from_json(text: str) -> MoveEvent:
    data = json.loads(text)
    return MoveEvent(
        market_id=data["market_id"],
        question=data["question"],
        tracked_outcome=data["tracked_outcome"],
        old_price=data["old_price"],
        new_price=data["new_price"],
        relative_move=data["relative_move"],
        old_at=datetime.fromisoformat(data["old_at"]),
        new_at=datetime.fromisoformat(data["new_at"]),
        game_start_time=data.get("game_start_time"),
    )
