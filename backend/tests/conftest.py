"""Pytest configuration for the backend test suite."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "beancount_parity: Sheets ↔ Beancount parity suite (Story 9.2 AC9) — "
        "run/skip independently in CI.",
    )
