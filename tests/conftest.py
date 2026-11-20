"""Configuration commune des tests."""

from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "navigateur: lance Chrome via Playwright (ignoré si Playwright ou Chrome est absent)")
