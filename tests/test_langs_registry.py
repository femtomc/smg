"""Tests for extractor registration warnings in smg.langs."""

from __future__ import annotations

import builtins

import pytest

from smg.langs import REGISTRY, load_extractors


@pytest.fixture(autouse=True)
def _preserve_registry():
    """Snapshot and restore the global extractor REGISTRY."""
    snapshot = dict(REGISTRY)
    yield
    REGISTRY.clear()
    REGISTRY.update(snapshot)


def test_warns_on_single_extractor_failure(monkeypatch, capsys):
    """A failing extractor import emits a per-module warning to stderr."""
    REGISTRY.clear()

    _real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "smg.langs.python":
            raise ImportError("No module named 'tree_sitter_python'")
        return _real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    load_extractors()

    err = capsys.readouterr().err
    assert "failed to load extractor 'python'" in err
    assert "tree_sitter_python" in err


def test_empty_registry_hint(monkeypatch, capsys):
    """When all extractors fail, an actionable install hint is emitted."""
    REGISTRY.clear()

    _real_import = builtins.__import__

    def _always_fail(name, *args, **kwargs):
        if name.startswith("smg.langs.") and name != "smg.langs":
            raise ImportError(f"missing {name}")
        return _real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _always_fail)

    load_extractors()

    err = capsys.readouterr().err
    assert "no extractors loaded" in err
    assert "smg[scan]" in err
