"""Idle reset end to end: a real ``hermes gateway run`` with the gadget plugin, a simulated
device and the fake OpenAI-compatible model, so "fresh conversation" is judged by what the
model is actually shown, and resets are counted in the gateway's own state.db.

Failure modes this covers:
- the device keeps one conversation forever (no reset after the idle window);
- a reset fires too eagerly, between quick follow-ups;
- a long task's result is lost: the follow-up right after it finishes lands in a new
  conversation because the request that started it is old;
- a reset fires while a turn is running, cutting the work's conversation off;
- with the setting absent, behaviour changes at all.

Opt-in like the other gateway E2E (spawns processes, ~1 minute):
    HERMES_GADGET_E2E=1 pytest tests/test_idle_reset_e2e.py
The temporary HERMES_HOME must live outside ~/.hermes (use --basetemp elsewhere), or the
host gateway takes it for its own tenant and the test gateway refuses to start.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time

import pytest

from conftest import REPO
import test_gateway_e2e as gw

pytestmark = gw.pytestmark
IDLE_S = 4.0
OUT = REPO / os.environ.get("IDLE_ARTIFACTS", "artifacts/idle-reset/local")


@pytest.fixture
def gateway(tmp_path):
    with gw.running_gateway(tmp_path, f"idle_reset_minutes: {IDLE_S / 60:.6f}") as g:
        yield g


def _chat_requests(api, since):
    return [r for r in api[since:] if r["path"].endswith("/chat/completions")]


def _resets(home):
    with sqlite3.connect(home / "state.db") as db:
        return db.execute("SELECT COUNT(*) FROM sessions WHERE source = 'gadget' AND end_reason = 'session_reset'"
                          ).fetchone()[0]


def _ask(sim, api, text, timeout=90):
    mark = len(api)
    sim.received.clear()
    sim.type_text(text)
    assert sim.wait_for(lambda: sim.last_received("turn.end") is not None, timeout=timeout), sim.received
    chats = [r for r in _chat_requests(api, mark) if text in r.get("user", "")]
    assert chats, ("the model never saw", text)
    return chats[-1]["conversation"]


def test_idle_device_starts_fresh_and_quick_follow_ups_do_not(gateway, make_sim):
    api, home = gateway["api"], gateway["home"]
    evidence = {"idle_s": IDLE_S, "steps": []}
    sim = make_sim(gateway["url"], name="Idle Gadget")
    assert sim.wait_for(lambda: sim.status().get("pairing_code"), timeout=60)
    approved = gw._hermes(home, "pairing", "approve", "gadget", sim.status()["pairing_code"])
    assert approved.returncode == 0, approved.stdout + approved.stderr
    assert sim.wait_screen("ready", timeout=30)

    def step(name, conversation, **facts):
        evidence["steps"].append({"step": name, "conversation": conversation, "resets": _resets(home), **facts})

    first = _ask(sim, api, "remember pineapple")
    step("first", first)
    follow = _ask(sim, api, "quick follow up")
    step("quick follow-up", follow)
    assert "pineapple" in follow, "a quick follow-up lost the conversation"
    assert _resets(home) == 0

    time.sleep(IDLE_S + 1.5)
    fresh = _ask(sim, api, "back after a break")
    step("after idle", fresh)
    assert "pineapple" not in fresh, "an idle device kept the old conversation"
    assert _resets(home) == 1

    # A long task: the request is older than the window when its result arrives, but the
    # follow-up right after the result belongs to the same conversation.
    slow = _ask(sim, api, "run the slow job")
    step("slow job", slow, slow_s=8.0)
    after = _ask(sim, api, "and what did that find")
    step("right after the slow job", after)
    assert "slow job" in after, "the follow-up to a long task lost its context"
    assert _resets(home) == 1

    # A message that arrives while a turn is running never resets, however old the request.
    mark = len(api)
    sim.received.clear()
    sim.type_text("run the slow job again")
    assert sim.wait_for(lambda: sim.last_received("turn.start") is not None, timeout=30)
    time.sleep(IDLE_S + 1.0)
    sim.type_text("still there?")
    assert sim.wait_for(lambda: any("still there?" in r.get("user", "") for r in _chat_requests(api, mark)),
                        timeout=90), "the mid-turn message never reached the model"
    step("mid-turn message", next(r["conversation"] for r in _chat_requests(api, mark)
                                  if "still there?" in r.get("user", "")))
    assert _resets(home) == 1, "a reset fired while a turn was running"

    OUT.mkdir(parents=True, exist_ok=True)
    log = (home / "logs" / "gateway.log").read_text(errors="replace")
    evidence["gateway_reset_log"] = sorted({line for line in log.splitlines() if "idle reset" in line})
    assert len(evidence["gateway_reset_log"]) == 1, evidence["gateway_reset_log"]
    (OUT / "idle-reset.json").write_text(json.dumps(evidence, indent=2))


def test_without_the_setting_the_device_keeps_its_conversation(gw_plain, make_sim):
    api, home = gw_plain["api"], gw_plain["home"]
    sim = make_sim(gw_plain["url"], name="Plain Gadget")
    assert sim.wait_for(lambda: sim.status().get("pairing_code"), timeout=60)
    assert gw._hermes(home, "pairing", "approve", "gadget", sim.status()["pairing_code"]).returncode == 0
    assert sim.wait_screen("ready", timeout=30)
    _ask(sim, api, "remember mango")
    time.sleep(IDLE_S + 1.5)
    later = _ask(sim, api, "later on")
    assert "mango" in later, "without idle_reset_minutes the conversation must carry on"
    assert _resets(home) == 0


@pytest.fixture
def gw_plain(tmp_path):
    with gw.running_gateway(tmp_path) as g:
        yield g
