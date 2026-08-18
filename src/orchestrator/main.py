"""Continuous Polymarket poll loop. On each detected move, spawns the
scrape -> match -> arb -> notify pipeline (orchestrator/pipeline.py) as
an isolated subprocess and returns immediately — never blocks waiting
for a trigger to finish. Structurally the same loop as
polymarket_monitor/poller.py, except a detected move spawns a pipeline
run instead of only logging."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from datetime import datetime, timezone

import httpx

from polymarket_monitor.client import fetch_nfl_moneyline_markets
from polymarket_monitor.detector import MoveDetector
from polymarket_monitor.models import MoveEvent

from .serialization import move_event_to_json

POLL_INTERVAL_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 480.0  # 8 minutes

logger = logging.getLogger("orchestrator")


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
    """Fetch current NFL moneyline prices, feed them to the detector, and
    spawn the pipeline for each detected move. Returns True on a
    successful fetch, False if the fetch failed (the caller backs off
    before retrying)."""
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
            game_start_time=snapshot.game_start_time,
        )
        if event is not None:
            logger.info(
                "MOVE DETECTED: %s (%s) %.3f -> %.3f (%.1f%% relative move) over %s",
                event.question,
                event.tracked_outcome,
                event.old_price,
                event.new_price,
                event.relative_move * 100,
                event.new_at - event.old_at,
            )
            trigger_pipeline(event)
    return True


def trigger_pipeline(event: MoveEvent) -> subprocess.Popen | None:
    """Fire-and-forget: spawn `python -m orchestrator.pipeline
    <move-event-json>` as a subprocess and return immediately. Inherits
    the parent's stdout/stderr (no redirection), so pipeline output
    interleaves with poll-loop logging in the same terminal. Never
    raises — a failure to even spawn the subprocess is logged and
    swallowed, matching this module's "a pipeline problem can never
    take down polling" contract."""
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "orchestrator.pipeline", move_event_to_json(event)]
        )
    except OSError as exc:
        logger.warning("Failed to spawn orchestrator pipeline: %s", exc)
        return None
