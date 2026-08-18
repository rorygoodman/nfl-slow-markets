from __future__ import annotations

import json
import os

import pytest

from common.credentials import default_credentials_path, load_credentials, parse_credentials


def test_parses_valid_credentials():
    creds = parse_credentials(json.dumps({"ntfy_topic": "my-topic"}))
    assert creds.ntfy_topic == "my-topic"


def test_ignores_extra_fields():
    creds = parse_credentials(json.dumps({"ntfy_topic": "my-topic", "extra": "ignored"}))
    assert creds.ntfy_topic == "my-topic"


def test_raises_on_missing_field():
    with pytest.raises(ValueError, match="ntfy_topic"):
        parse_credentials(json.dumps({}))


def test_raises_on_non_string_field():
    with pytest.raises(ValueError, match="ntfy_topic"):
        parse_credentials(json.dumps({"ntfy_topic": 123}))


def test_raises_on_invalid_json():
    with pytest.raises(ValueError):
        parse_credentials("not json")


def test_raises_on_non_object_json():
    with pytest.raises(ValueError):
        parse_credentials(json.dumps(["a", "b"]))


def test_default_credentials_path_is_under_home():
    path = default_credentials_path()
    assert path.name == "credentials.json"
    assert path.parent.name == ".nfl-slow-markets"


def test_load_credentials_raises_when_file_missing(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_credentials(tmp_path / "missing.json")


def test_load_credentials_reads_and_parses_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"ntfy_topic": "my-topic"}))
    creds = load_credentials(path)
    assert creds.ntfy_topic == "my-topic"


def test_load_credentials_warns_when_world_readable(tmp_path, capsys):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"ntfy_topic": "my-topic"}))
    os.chmod(path, 0o644)
    load_credentials(path)
    assert "chmod 600" in capsys.readouterr().err


def test_load_credentials_no_warning_when_private(tmp_path, capsys):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"ntfy_topic": "my-topic"}))
    os.chmod(path, 0o600)
    load_credentials(path)
    assert capsys.readouterr().err == ""
