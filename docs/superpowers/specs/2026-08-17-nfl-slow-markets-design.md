---
status: draft
date: 2026-08-17
topic: Polymarket-triggered NFL bookmaker value-bet alerting
---

# NFL slow markets

## Goal

During NFL preseason, Polymarket's NFL game-winner markets react within
seconds to beat-reporter news (QB benchings, injuries, availability). UK/IE
bookmakers (Paddy Power, Novibet) are slower to reprice. This tool watches
Polymarket continuously, and when a market's implied probability moves
sharply, scrapes the bookmakers to check whether their odds still imply the
old (stale) probability. If backing a bookmaker's current price is
positive-EV against Polymarket's new fair price, it sends a push
notification (via [ntfy](https://ntfy.sh)) with the details.

Read-only against Polymarket throughout — no wallet, no order placement, no
Polymarket position. Polymarket is used purely as a fast, efficient
reference price; the only stake ever considered is at the bookmaker.

## Non-goals

- No cross-platform arbitrage (no Polymarket buy/sell, no hedged position
  across both platforms). Polymarket is a price oracle only.
- No spreads, totals, or player props. Game-winner (moneyline) markets only.
- No persistence of price history or alert state across restarts. This is a
  short-lived tool for one preseason window; losing ~10 minutes of rolling
  window and any pending alert cooldowns on a crash/restart is an accepted
  simplification, not a design goal to solve.
- No public site / GitHub Pages publishing. This is a private alerting tool
  for one recipient, unlike `horsey-scraper` and `golf-odds-scraper`.
- No stake-sizing recommendation in the notification beyond the computed
  edge — a human decides bet size.
- No US sportsbooks (DraftKings/FanDuel/BetMGM) in this iteration.

## Architecture

```
Polymarket poll loop (30-60s, continuous process)
   -> rolling 10-min sell-side (best-ask) price window, per market
   -> |relative change vs. price ~10min ago| >= 5%
        -> scrape Paddy Power + Novibet NFL odds (subprocess, isolated
           from the poll loop so a scraper crash/hang can't kill polling)
        -> match Polymarket market -> bookmaker event
           (team names + kickoff time; no shared IDs across platforms)
        -> per matched bookmaker leg:
             true_prob   = Polymarket sell-side price at trigger time
             edge        = decimal_odds * true_prob - 1
        -> edge > threshold (default 2%) AND not in cooldown
             -> ntfy push notification
```

The poll loop and the scrape pipeline are process-isolated (the pipeline
runs as a subprocess invocation per trigger) so a Playwright hang or crash
in a bookmaker scraper can never take down the continuously-running
Polymarket poller.

## Why sell-side (best ask), not midpoint or last-trade

The "true probability" reference is the best-ask price of the relevant
outcome token: the price at which you could actually acquire that outcome
right now. Using the midpoint is noisier in thin preseason order books —
one side of the book disappearing (not an actual trade) can swing the
midpoint and produce a false-positive "move." Best-ask is used consistently
for both:

1. **Move detection** — the trailing 10-minute price series is the best-ask
   at each poll.
2. **The edge calculation** — `true_prob` at trigger time is the same
   best-ask price, not a separate midpoint or last-trade figure.

## Move detection formula

Relative change, not percentage points:

```
relative_move = abs(price_now - price_10min_ago) / price_10min_ago
trigger if relative_move >= 0.05
```

`price_10min_ago` is the oldest sample still inside the trailing 10-minute
window (samples are taken every poll interval, so this is the sample
closest to but not older than `now - 10min`). A market with no sample yet
at least 10 minutes old cannot trigger (not enough history).

## Modules

Python (uv), styled on `horsey-scraper`'s per-concern layout:

- **`polymarket_monitor/`**
  - `client.py` — Gamma API (market discovery: NFL game-winner markets,
    current week) + CLOB API (best-ask price per outcome token).
  - `models.py` — `Market`, `PriceSample`.
  - `detector.py` — pure function: given a market's sample deque and a new
    sample, returns whether the trailing-10-min relative-move threshold is
    crossed. Unit-testable without any network access.
- **`paddypower_scraper/`** — NFL event odds. Reuses the
  Playwright/internal-API approach from `horsey-scraper`'s
  `paddypower_scraper`, retargeted from racing to NFL event pages.
- **`novibet_scraper/`** — NFL event odds. Reuses the Cloudflare-warmup +
  gateway-header approach from `horsey-scraper`'s `novibet_scraper`
  (`x-gw-*` headers, `WARMUP_URL` + in-page `fetch()`, same shape as
  `paddypower_scraper`'s `BrowserSession`), retargeted from horse racing's
  `sport_id`/`group_id` to American football's.
- **`matching/`** — normalizes team names (e.g. "Kansas City Chiefs" /
  "Chiefs" / "KC") and matches a Polymarket market to a bookmaker's event
  listing by teams + kickoff time. Same shape as
  `horsey-scraper`'s `arb_finder/matching.py` name-based matching.
- **`arb_finder/`**
  - `calculator.py` — pure function `value_bet_edge(decimal_odds: float,
    true_prob: float) -> float`, returning `decimal_odds * true_prob - 1`.
  - orchestration: joins a detected move to matched bookmaker prices,
    computes edge per leg, filters by minimum edge threshold, ranks.
- **`notifier/`** — ntfy (https://ntfy.sh) push sender: a plain HTTP POST
  to `https://ntfy.sh/<topic>` per alert (no SMTP, no email account, no
  app password). Formats one push per alert: title = game + move %, body =
  market, Polymarket move (old price, new price, relative %), bookmaker +
  leg odds, computed edge. Chosen over email for latency — Apple Mail only
  gets true push for IMAP-push-capable accounts (iCloud/Exchange-style);
  Gmail in Apple Mail is periodic fetch, not push, which is a real problem
  for a tool whose entire value is catching a mispricing before it closes.
  ntfy's iOS app is wired into APNs directly, so delivery is near-instant,
  without standing up Apple Developer / APNs provider infrastructure for
  one recipient.
- **`common/`** — `jsonio.py`, `timeutil.py`, `credentials.py` (adapted from
  `horsey-scraper`'s `common/`).
- **`orchestrator/`** (`main.py`) — runs the poll loop; on trigger, invokes
  scrape -> match -> arb -> notify; holds the in-memory cooldown map.

## Config & credentials

`~/.nfl-slow-markets/credentials.json`:

```json
{
  "ntfy_topic": "<long, random, generated per-deployment — never committed>"
}
```

ntfy's free public server (`ntfy.sh`) has no sign-up or auth — the topic
name is the only thing standing between the alerts and anyone who knows
it, so it's generated long and random (not a guessable slug like
`rory-nfl-arbs`) and treated as a secret: same `chmod 600` +
group/other-readable warning convention as `horsey-scraper`'s Betfair
credentials file, never logged, never committed. The recipient side is a
one-time setup: install the ntfy iOS app and subscribe to this exact
topic string. No credentials needed for Polymarket (public read API) or,
expected, for Paddy Power / Novibet odds pages (public, unauthenticated,
matching how `horsey-scraper` scrapes both bookmakers' each-way prices
today).

Thresholds (move %, min edge %, poll interval, cooldown window) are
config values with defaults, not hardcoded:

| Setting | Default |
|---|---|
| Poll interval | 30s |
| Move threshold (relative) | 5% |
| Trailing window | 10 min |
| Minimum edge to alert | 2% |
| Cooldown per (market, bookmaker) | 30 min |

## Error handling

- **Polymarket poll errors** (network, rate limit): caught, logged,
  exponential backoff up to a cap, loop continues. Never crashes the
  process.
- **Bookmaker scrape errors**: each bookmaker scraped independently;
  failure in one is logged and non-fatal (mirrors `horsey-scraper`'s
  888/Novibet pattern) — a Paddy Power success still produces an alert even
  if Novibet fails entirely.
- **No match found** (Polymarket market has no corresponding event at a
  given bookmaker, or the bookmaker's market is suspended): skip that leg,
  log, continue — not an error.
- **All legs fail for a trigger**: logged, no notification sent.
- **ntfy delivery failure** (network error, non-2xx from `ntfy.sh`): caught,
  logged to stderr, non-fatal — a failed push must not crash the poll loop
  or the trigger pipeline. The alert is lost for that trigger (no retry
  queue — matches the project's short-lived, no-cross-restart-persistence
  scope).
- **Cooldown**: same (market, bookmaker) pair does not re-alert within the
  cooldown window even if the edge persists across multiple polls, to avoid
  spamming a push notification per poll cycle while a mispricing sits
  open. Cooldown resets are in-memory only (see Non-goals: no
  cross-restart persistence).

## Testing

Pytest, matching `horsey-scraper`'s convention (`pythonpath = ["src"]`,
`testpaths = ["tests"]`, `integration` marker opt-in via `RUN_INTEGRATION=1`
for live network/browser tests):

- **Unit** (no network): `detector.py`'s trailing-window relative-move logic
  (exact-5% boundary, oscillating prices, insufficient history, gaps in
  polling); `calculator.py`'s `value_bet_edge`; `matching/`'s team-name
  normalization and kickoff-time matching.
- **Integration** (opt-in): live Polymarket API call confirming the client
  can fetch current NFL game-winner markets; live scraper smoke tests for
  Paddy Power / Novibet (expected to need periodic maintenance as site
  structure changes, same as your other scrapers).
- The ntfy HTTP POST is mocked in tests; the test suite never sends a real
  push notification.

## Risks

- **bet365 dropped from scope**: originally planned as the second
  bookmaker, but has no existing scraping pattern anywhere in your repos
  and is known for aggressive anti-bot/obfuscation. Replaced with Novibet,
  which `horsey-scraper` already scrapes successfully for horse racing
  (Cloudflare-warmup + `x-gw-*` gateway headers) — same reuse story as
  Paddy Power, lower risk than attempting bet365 from scratch. bet365
  coverage could be revisited later if Paddy Power + Novibet prove
  insufficient.
- **Novibet's NFL `sport_id`/`group_id` are unverified**: `horsey-scraper`'s
  `novibet_scraper` targets horse racing's IDs; the implementation plan
  must discover the correct American-football equivalents against the
  live site (or via captured network requests, the same way
  `paddypower_scraper`'s NFL-specific endpoint and competition IDs were
  found) before building `client.py`/`api.py`.
- **Polymarket API surface**: exact Gamma/CLOB endpoint shapes may have
  shifted since this design was written; the implementation plan should
  verify current endpoints against Polymarket's live API before building
  `client.py`.
- **In-memory state loss on restart**: accepted per Non-goals; worth
  re-raising only if the tool needs to run unattended for longer than a
  preseason window.

## Deployment

Run as a single long-lived process for the duration of preseason:

```
uv run python -m orchestrator
```

Intended to run in a persistent terminal/tmux session or as a
launchd/systemd user service — no cron, no scheduled re-invocation (unlike
`horsey-scraper`/`golf-odds-scraper`'s cron-driven batch model), since the
rolling 10-minute window and cooldown state live in process memory and must
not be torn down between polls.
