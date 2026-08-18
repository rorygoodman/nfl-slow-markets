"""One trigger's worth of work: scrape both bookmakers, match against a
detected Polymarket move, compute edges, and send notifications for
anything not already in cooldown.

Runs as its own OS process per invocation (see orchestrator/main.py's
trigger_pipeline, which spawns `python -m orchestrator.pipeline
<move-event-json>` via subprocess.Popen) so a Playwright hang or crash
here can never take down the continuously-running Polymarket poll loop.

Scrapes Paddy Power and Novibet sequentially, not concurrently. Each
BrowserSession's Cloudflare warmup + fetch takes on the order of
10-30s, so a trigger-to-alert round trip is roughly 20-60s. Running the
two scrapers concurrently would roughly halve that — each BrowserSession
already creates its own independent sync_playwright() instance with no
shared state, so it's plausible — but Playwright's sync API under
threading isn't exercised anywhere else in this codebase, and this is
the last module of the project. Deferred as a follow-up rather than
risked here; sequential is simple and definitely correct."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from arb_finder.finder import find_value_bets
from common.credentials import default_credentials_path, load_credentials
from matching.adapters import from_novibet, from_paddypower
from matching.models import BookmakerGame
from notifier.formatting import format_alert
from notifier.ntfy import send_notification
from novibet_scraper.browser import BrowserSession as NovibetBrowserSession
from novibet_scraper.scraper import AllMarketViewGroupsFailedError
from novibet_scraper.scraper import scrape_nfl_moneylines as scrape_novibet
from paddypower_scraper.browser import BrowserSession as PaddyPowerBrowserSession
from paddypower_scraper.scraper import AllCompetitionsFailedError
from paddypower_scraper.scraper import scrape_nfl_moneylines as scrape_paddypower

from .cooldown import (
    default_cooldown_path,
    is_in_cooldown,
    load_cooldowns,
    record_alert,
    save_cooldowns,
)
from .serialization import move_event_from_json


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m orchestrator.pipeline <move-event-json>", file=sys.stderr)
        return 1
    move = move_event_from_json(argv[0])

    try:
        creds = load_credentials(default_credentials_path())
    except ValueError as exc:
        print(f"orchestrator: {exc}", file=sys.stderr)
        return 1

    paddypower_games = _scrape_paddypower()
    novibet_games = _scrape_novibet()
    alerts = find_value_bets(move, paddypower_games, novibet_games)

    if not alerts:
        print(f"orchestrator: no value bets found for {move.question}")
        return 0

    cooldown_path = default_cooldown_path()
    cooldowns = load_cooldowns(cooldown_path)
    now = datetime.now(timezone.utc)
    sent = 0
    for alert in alerts:
        if is_in_cooldown(cooldowns, move.market_id, alert.bookmaker, now):
            print(f"orchestrator: {move.market_id}/{alert.bookmaker} in cooldown, skipping")
            continue
        message = format_alert(alert)
        if send_notification(message, creds.ntfy_topic):
            record_alert(cooldowns, move.market_id, alert.bookmaker, now)
            sent += 1
        else:
            print(f"orchestrator: failed to send notification for {alert.bookmaker}", file=sys.stderr)

    save_cooldowns(cooldown_path, cooldowns)
    print(f"orchestrator: sent {sent}/{len(alerts)} alert(s) for {move.question}")
    return 0


def _scrape_paddypower() -> list[BookmakerGame]:
    try:
        with PaddyPowerBrowserSession() as session:
            games = scrape_paddypower(session)
    except Exception as exc:
        # Broad by design: BrowserSession.__enter__ drives Playwright's
        # own startup/navigation (sync_playwright().start(), launch(),
        # goto(), wait_for_load_state()), any of which can raise
        # Playwright's own exception types, not just this scraper's
        # AllCompetitionsFailedError. Each bookmaker must fail
        # independently and non-fatally, so catch everything here.
        print(f"orchestrator: paddypower scrape failed: {exc}", file=sys.stderr)
        return []
    return [from_paddypower(g) for g in games]


def _scrape_novibet() -> list[BookmakerGame]:
    try:
        with NovibetBrowserSession() as session:
            games = scrape_novibet(session)
    except Exception as exc:
        # Broad by design: see _scrape_paddypower's comment above — this
        # also has to catch Playwright's own exception types raised
        # during BrowserSession's startup/navigation, not just
        # AllMarketViewGroupsFailedError.
        print(f"orchestrator: novibet scrape failed: {exc}", file=sys.stderr)
        return []
    return [from_novibet(g) for g in games]


if __name__ == "__main__":
    raise SystemExit(main())
