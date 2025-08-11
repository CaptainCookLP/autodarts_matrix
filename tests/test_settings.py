import json
import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import simple_round_ws


def test_get_setting_reads_file(monkeypatch, tmp_path):
    data = {"autodarts_username": "foo"}
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps(data))
    monkeypatch.delenv("AUTODARTS_USERNAME", raising=False)
    monkeypatch.setattr(simple_round_ws, "SETTINGS_FILE", str(cfg))
    assert simple_round_ws.get_setting("AUTODARTS_USERNAME") == "foo"


def test_get_setting_missing(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text("{}")
    monkeypatch.delenv("AUTODARTS_USERNAME", raising=False)
    monkeypatch.setattr(simple_round_ws, "SETTINGS_FILE", str(cfg))
    with pytest.raises(RuntimeError):
        simple_round_ws.get_setting("AUTODARTS_USERNAME")
