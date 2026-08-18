"""Load and validate ~/.nfl-slow-markets/credentials.json."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ntfy's documented topic charset: letters, numbers, underscores, dashes;
# 1-64 characters. https://docs.ntfy.sh/publish/#topics
_NTFY_TOPIC_RE = re.compile(r"^[-_A-Za-z0-9]{1,64}$")


@dataclass(frozen=True)
class Credentials:
    ntfy_topic: str


def parse_credentials(text: str) -> Credentials:
    """JSON object with a string field ntfy_topic. Extra fields ignored.
    Missing/non-string/invalid-topic field -> ValueError."""
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise ValueError(f"credentials JSON is not a valid object: {e}")
    ntfy_topic = root.get("ntfy_topic")
    if not isinstance(ntfy_topic, str):
        raise ValueError("credentials JSON missing or non-string field: ntfy_topic")
    if not _NTFY_TOPIC_RE.fullmatch(ntfy_topic):
        raise ValueError(
            "ntfy_topic is not a valid ntfy topic (must match ^[-_A-Za-z0-9]{1,64}$)"
        )
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
