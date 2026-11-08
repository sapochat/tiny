"""Local diagnostics through a real gateway: `hermes gadget debug` reaches the live adapter.

A real ``hermes gadget debug`` CLI process talks to a real ``hermes gateway run`` (the
plugin installed from this repository, a temporary HERMES_HOME, loopback only) over the
adapter's private Unix socket, while a simulated device is paired and connected.

Opt-in like the other gateway test (spawns processes, about a minute):
    HERMES_GADGET_E2E=1 HERMES_AGENT_DIR=~/.hermes/hermes-agent pytest tests/test_debug_bridge_e2e.py
"""

from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from conftest import requires_sim
from test_gateway_e2e import VENV_PY, _hermes, gateway  # noqa: F401  (the fixture)

pytestmark = [
    requires_sim,
    pytest.mark.skipif(sys.platform != "linux", reason="the diagnostics socket is Linux same-user IPC"),
    pytest.mark.skipif(os.environ.get("HERMES_GADGET_E2E") != "1", reason="set HERMES_GADGET_E2E=1 to run"),
    pytest.mark.skipif(not VENV_PY.exists(), reason=f"no Hermes virtualenv at {VENV_PY}"),
]


def _json(done) -> dict:
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    assert lines, f"no JSON from the CLI (exit {done.returncode}):\n{done.stdout}\n{done.stderr}"
    return json.loads(lines[-1])


def test_debug_status_reads_the_live_gateway_and_writes_need_confirm(gateway, make_sim):
    home = gateway["home"]
    sim = make_sim(gateway["url"], name="Debug Gadget")
    assert sim.wait_for(lambda: sim.status().get("pairing_code"), timeout=60)
    approved = _hermes(home, "pairing", "approve", "gadget", sim.status()["pairing_code"])
    assert approved.returncode == 0, approved.stdout + approved.stderr
    assert sim.wait_screen("ready", timeout=30)

    # Status: the live connection as the gateway holds it, read from a separate process.
    status = _hermes(home, "gadget", "debug", "status")
    assert status.returncode == 0, status.stdout + status.stderr
    data = _json(status)
    assert data["success"] is True
    assert data["operations"] == ["status", "display", "tone"]
    mine = [c for c in data["connected"] if c["name"] == "Debug Gadget"]
    assert len(mine) == 1, data
    device = mine[0]
    assert device["paired"] is True
    assert device["device_id"].startswith("hg-")
    assert "talk" in device["inputs"]
    assert isinstance(device["last_rx_age_s"], float)

    # A write without --confirm is refused and nothing reaches the device.
    sim.received.clear()
    refused = _hermes(home, "gadget", "debug", "display", device["device_id"], "hello from debug")
    assert refused.returncode == 1
    assert "--confirm" in _json(refused)["error"]
    sim.run_for(1.0)
    assert sim.last_received("display") is None

    # Confirmed: the card arrives, and the result says only that the transport sent it.
    shown = _hermes(home, "gadget", "debug", "display", device["device_id"], "hello from debug", "--confirm")
    assert shown.returncode == 0, shown.stdout + shown.stderr
    result = _json(shown)
    assert result["delivery"] == "transport_sent" and result["device_acknowledged"] is False
    assert sim.wait_for(lambda: (sim.last_received("display") or {}).get("body") == "hello from debug",
                        timeout=10), sim.received
    assert sim.last_received("display")["title"] == "Hermes debug"

    # An unknown device is an error, not a broadcast.
    unknown = _hermes(home, "gadget", "debug", "display", "hg-0000000000000000", "x", "--confirm")
    assert unknown.returncode == 1 and "not connected" in _json(unknown)["error"]

    # The socket and its directory are private to this user.
    sock = home / "plugin-data" / "gadget" / "debug" / "control.sock"
    assert stat.S_ISSOCK(sock.lstat().st_mode)
    assert stat.S_IMODE(sock.lstat().st_mode) == 0o600
    assert stat.S_IMODE(sock.parent.lstat().st_mode) == 0o700
