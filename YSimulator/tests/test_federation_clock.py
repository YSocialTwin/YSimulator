"""Federated clock hooks of the YSimulator server (F2.6): the gate is a stub, no coordinator, no network."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from YSimulator.YServer.server import OrchestratorServer

CLASS = getattr(OrchestratorServer, "__ray_actor_class__", OrchestratorServer)
SLOTS = 24


class StubGate:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def on_barrier_ready(self, local_round):
        self.calls.append(("barrier", tuple(local_round)))
        return self.allowed

    def on_round_opened(self, local_round):
        self.calls.append(("opened", tuple(local_round)))

    def on_finished(self):
        self.calls.append(("finished",))


class _Server(SimpleNamespace):
    @property
    def day(self):
        return self.round_manager.day

    @property
    def slot(self):
        return self.round_manager.slot


def make_server(gate=None, active=("a",), submitted=("a",)):
    rm = SimpleNamespace(day=1, slot=1)

    def advance(recompute_interests_callback=None):
        rm.slot += 1
        done = rm.slot > SLOTS
        if done:
            rm.slot, rm.day = 1, rm.day + 1
        return {"day_completed": done}

    rm.advance_simulation = advance
    s = _Server(
        _federation_gate=gate, _advance_pending=False, _advance_lock=threading.RLock(),
        round_manager=rm, submitted_clients=set(submitted), active=set(active),
        barrier_handler=SimpleNamespace(check_barrier_and_should_advance=lambda act, sub: set(act) <= set(sub)),
        client_manager=SimpleNamespace(clear_submitted_clients=Mock(), complete_client=Mock(return_value=True)),
        archetype_manager=SimpleNamespace(should_perform_transitions=lambda d: False),
        _recompute_all_agent_interests=Mock(), min_to_start=1, recent_posts_cache=[],
        _check_for_stale_clients=Mock(),
    )
    s._get_active_clients = lambda: s.active
    for name in ("_check_barrier_and_advance", "_check_barrier_and_advance_locked"):
        setattr(s, name, getattr(CLASS, name).__get__(s))
    return s


def local(s):
    return s.round_manager.day, s.round_manager.slot


def test_standalone_advances_without_a_gate():
    s = make_server()
    s._check_barrier_and_advance()
    assert local(s) == (1, 2) and s._advance_pending is False


def test_gate_closed_holds_the_round_and_marks_it_pending():
    gate = StubGate(allowed=False)
    s = make_server(gate)
    s._check_barrier_and_advance()
    assert local(s) == (1, 1) and s._advance_pending is True
    assert gate.calls == [("barrier", (1, 1))]
    s.client_manager.clear_submitted_clients.assert_not_called()


def test_gate_opening_releases_the_held_round_and_reports_the_new_one():
    gate = StubGate(allowed=False)
    s = make_server(gate)
    s._check_barrier_and_advance()
    gate.allowed = True
    s._check_barrier_and_advance()  # what get_instruction does while pending
    assert local(s) == (1, 2) and s._advance_pending is False
    assert gate.calls[-2:] == [("barrier", (1, 1)), ("opened", (1, 2))]
    s.client_manager.clear_submitted_clients.assert_called_once()


def test_local_barrier_not_ready_does_not_ask_the_gate():
    gate = StubGate()
    s = make_server(gate, active=("a", "b"), submitted=("a",))
    s._check_barrier_and_advance()
    assert gate.calls == [] and local(s) == (1, 1)


def test_day_rollover_is_reported_in_one_based_local_time():
    gate = StubGate()
    s = make_server(gate)
    s.round_manager.slot = SLOTS
    s._check_barrier_and_advance()
    assert local(s) == (2, 1) and gate.calls[-1] == ("opened", (2, 1))


def test_get_instruction_retries_a_pending_advance():
    gate = StubGate(allowed=False)
    s = make_server(gate)
    s._check_barrier_and_advance()
    gate.allowed = True
    # get_instruction body, reached through the undecorated function
    fn = getattr(CLASS.get_instruction, "__wrapped__", None)
    if fn is None:
        pytest.skip("get_instruction is not unwrappable")
    fn(s, "a")
    assert local(s) == (1, 2)


def test_complete_client_reports_the_end_of_the_run():
    fn = getattr(CLASS.complete_client, "__wrapped__", None)
    if fn is None:
        pytest.skip("complete_client is not unwrappable")
    gate = StubGate()
    s = make_server(gate, active=(), submitted=())
    fn(s, "a")
    assert gate.calls[-1] == ("finished",)
