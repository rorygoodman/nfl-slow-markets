from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from .client import fetch_nfl_moneyline_markets
from .detector import MoveDetector

POLL_INTERVAL_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 480.0  # 8 minutes

logger = logging.getLogger("polymarket_monitor")


def run(poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    detector = MoveDetector()
    with httpx.Client(timeout=10.0) as client:
        backoff = poll_interval
        while True:
            ok = poll_once(client, detector)
            if ok:
                backoff = poll_interval
                time.sleep(poll_interval)
            else:
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


def poll_once(client: httpx.Client, detector: MoveDetector) -> bool:
    """Fetch current NFL moneyline prices and feed them to the detector.
    Returns True on a successful fetch, False if the fetch failed (the
    caller backs off before retrying)."""
    now = datetime.now(timezone.utc)
    try:
        snapshots = fetch_nfl_moneyline_markets(client)
    except httpx.HTTPError as exc:
        logger.warning("Polymarket fetch failed: %s", exc)
        return False

    logger.info("Polled %d NFL moneyline markets", len(snapshots))
    for snapshot in snapshots:
        event = detector.observe(
            market_id=snapshot.market_id,
            question=snapshot.question,
            tracked_outcome=snapshot.tracked_outcome,
            price=snapshot.best_ask,
            now=now,
        )
        if event is not None:
            logger.info(
                "MOVE DETECTED: %s (%s) %.3f -> %.3f (%.1f%% relative move) over %s",
                event.question, event.tracked_outcome, event.old_price, event.new_price,
                event.relative_move * 100, event.new_at - event.old_at,
            )
    return True
