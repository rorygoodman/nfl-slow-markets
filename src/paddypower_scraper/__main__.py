from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .browser import BrowserSession
from .scraper import scrape_nfl_moneylines

OUTPUT_PATH = Path("paddypower_nfl.json")


def main() -> int:
    with BrowserSession() as session:
        games = scrape_nfl_moneylines(session)
    output = {
        "game_count": len(games),
        "games": [_game_to_dict(g) for g in games],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"Wrote {OUTPUT_PATH} ({len(games)} games)")
    return 0


def _game_to_dict(game) -> dict:
    d = dataclasses.asdict(game)
    d["teams"] = list(d["teams"])
    return d


if __name__ == "__main__":
    raise SystemExit(main())
