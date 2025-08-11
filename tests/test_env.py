import os
import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from simple_round_ws import get_env


def test_get_env_returns_value(monkeypatch):
    monkeypatch.setenv('FOO', 'bar')
    assert get_env('FOO') == 'bar'


def test_get_env_missing(monkeypatch):
    monkeypatch.delenv('MISSING', raising=False)
    with pytest.raises(RuntimeError):
        get_env('MISSING')
