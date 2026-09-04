"""Packaging-metal metadata tests.

These catch upload-time failures that ``twine check`` misses. In particular,
PyPI rejects a wheel whose ``classifiers`` contain a Trove classifer that is
not in PyPI's authoritative list (HTTP 400 "is not a valid classifier") — see
commit 37b6105. ``twine check`` does NOT validate classifiers against that
list; only this test does, via the ``trove-classifiers`` package (the same
source-trove list PyPI accepts uploads against).
"""

import tomllib

import pytest
import trove_classifiers

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _classifiers() -> list[str]:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["classifiers"]


def test_every_classifier_is_a_valid_trove_classifier():
    known = trove_classifiers.classifiers
    invalid = [c for c in _classifiers() if c not in known]
    assert not invalid, f"classifiers not in PyPI's Trove list: {invalid}"


def test_at_least_one_classifier():
    assert len(_classifiers()) > 0
