"""Load and validate ~/.nfl-slow-markets/credentials.json."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Credentials:
    ntfy_topic: str


def parse_credentials(text: str) -> Credentials:
    """JSON object with a string field ntfy_topic. Extra fields ignored.
    Missing/non-string field -> ValueError."""
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise ValueError(f"credentials JSON is not a valid object: {e}")
    ntfy_topic = root.get("ntfy_topic")
    if not isinstance(ntfy_topic, str):
        raise ValueError("credentials JSON missing or non-string field: ntfy_topic")
    return Credentials(ntfy_topic)


def default_credentials_path() -> Path:
    return Path.home() / ".nfl-slow-markets" / "credentials.json"


def load_credentials(path: "Path | str") -> Credentials:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"credentials file not found: {path}")
    _warn_if_world_readable(path)
    try:
        text = path.read_text()
    except OSError as e:
        raise ValueError(f"failed to read {path}: {e}")
    return parse_credentials(text)


def _warn_if_world_readable(path: Path) -> None:
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return
    if mode & 0o077:
        print(
            f"Warning: {path} is readable by group/others; recommend `chmod 600`.",
            file=sys.stderr,
        )
