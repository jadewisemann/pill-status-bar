"""Suite-wide fixtures.

The tests run offline, always. `shell/modules/weather.py` fetches from
Open-Meteo on a worker thread the moment the module starts, and the `shell`
fixture starts the real modules -- so without this, every test that builds the
app makes two real HTTP calls. Where the runner can reach the network that is
merely slow and non-deterministic; where it cannot, each call sits out its 10s
socket timeout, which is what turned a 2-second suite into a ten-minute one on
the Windows CI legs.

It also raced with interpreter shutdown: CI segfaulted on 3.13 with a worker
thread still inside an SSL handshake while the process was tearing down.
Refusing the connection outright removes the race from the suite. It does not
fix it in the shell -- a fetch in flight when the app quits is a real shutdown
race -- but a test suite is the wrong place to discover that.

Refusing also exercises the path the shell takes on a machine with no network,
which is the behaviour worth pinning down anyway.
"""

from __future__ import annotations

import urllib.request

import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches the network."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("the test suite does not reach the network")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
