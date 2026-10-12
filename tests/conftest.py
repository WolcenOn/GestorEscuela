from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def enable_legacy_bootstrap_only_for_legacy_regressions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep pre-Bearer regression tests explicit about their compatibility dependency.

    Production code defaults the legacy role bootstrap to disabled. The historical API tests still
    exercise the old bootstrap flow, so the test environment opts in deliberately. Security tests
    that verify the production default remove this variable inside the individual test.
    """

    monkeypatch.setenv("ALLOW_LEGACY_ROLE_BOOTSTRAP", "true")
