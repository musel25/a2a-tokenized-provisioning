"""M4.1 — the domain, hardened: every deny path named, the order pinned, the machine
exhaustive, and the purity rule executable."""

from __future__ import annotations

import ast
import inspect

import pytest

from a2a_interfaces import ErrorCode, SessionState
from a2a_interfaces.fixtures import ADA, BELL, CANONICAL_ENTITLEMENT_VIEW, WINDOW

from controller import domain
from controller.domain import IllegalTransition, predicate, transition

VIEW = CANONICAL_ENTITLEMENT_VIEW  # ticket #7: Ada's 50 Mbps, 14:00–16:00
IN_WINDOW = WINDOW.start + 120  # 14:02, the canonical activation moment


def test_happy_path_allows():
    assert predicate(VIEW, owner=ADA, requester=ADA, now=IN_WINDOW, active_ids=set()) is None


# --- every deny path, by name (docs/05 §2) ------------------------------------


def test_denies_non_owner():
    code = predicate(VIEW, owner=ADA, requester=BELL, now=IN_WINDOW, active_ids=set())
    assert code == ErrorCode.E_NOT_OWNER


def test_denies_before_window():
    code = predicate(VIEW, ADA, ADA, now=WINDOW.start - 1, active_ids=set())
    assert code == ErrorCode.E_NOT_STARTED


def test_allows_at_exact_start():
    assert predicate(VIEW, ADA, ADA, now=WINDOW.start, active_ids=set()) is None


def test_denies_at_exact_end():
    # The window is [start, end): at 16:00:00 sharp the ticket is already dead —
    # pinned so nobody "fixes" the >= into > and grants a free second.
    code = predicate(VIEW, ADA, ADA, now=WINDOW.end, active_ids=set())
    assert code == ErrorCode.E_EXPIRED


def test_denies_revoked():
    revoked = VIEW.model_copy(update={"revoked": True})
    code = predicate(revoked, ADA, ADA, now=IN_WINDOW, active_ids=set())
    assert code == ErrorCode.E_REVOKED


def test_denies_unknown_service_type():
    alien = VIEW.model_copy(update={"service_type": 7})
    code = predicate(alien, ADA, ADA, now=IN_WINDOW, active_ids=set())
    assert code == ErrorCode.E_SCOPE


def test_scope_is_caller_dependent():
    # The M0.3 stub translates bandwidth only; a telemetry ticket that the REAL
    # controller admits must be E_SCOPE for the stub (docs/05 §2).
    telemetry = VIEW.model_copy(update={"service_type": 1})
    assert predicate(telemetry, ADA, ADA, IN_WINDOW, set()) is None
    assert (
        predicate(telemetry, ADA, ADA, IN_WINDOW, set(), known_service_types=(0,))
        == ErrorCode.E_SCOPE
    )


def test_denies_double_booking():
    code = predicate(VIEW, ADA, ADA, now=IN_WINDOW, active_ids={VIEW.id})
    assert code == ErrorCode.E_CONFLICT


def test_order_first_failure_wins():
    # A request failing EVERY check must report E_NOT_OWNER — the deny order is
    # contract, not accident (the e2e deny tests rely on stable codes).
    wreck = VIEW.model_copy(update={"revoked": True, "service_type": 9})
    code = predicate(wreck, owner=ADA, requester=BELL, now=WINDOW.end + 999, active_ids={VIEW.id})
    assert code == ErrorCode.E_NOT_OWNER


# --- the state machine (docs/05 §3) --------------------------------------------


@pytest.mark.parametrize(
    ("state", "event", "expected"),
    [
        (SessionState.REQUESTED, "authorize", SessionState.AUTHORIZED),
        (SessionState.REQUESTED, "deny", SessionState.FAILED),
        (SessionState.AUTHORIZED, "provision_ok", SessionState.ACTIVE),
        (SessionState.AUTHORIZED, "provision_failed", SessionState.FAILED),
        (SessionState.ACTIVE, "teardown", SessionState.TORN_DOWN),
    ],
)
def test_legal_transitions(state, event, expected):
    assert transition(state, event) == expected


@pytest.mark.parametrize("terminal", [SessionState.TORN_DOWN, SessionState.FAILED])
def test_teardown_of_terminal_states_is_absorbed(terminal):
    # Rule 8 in the machine itself: re-teardown stays put, never raises.
    assert transition(terminal, "teardown") == terminal


def test_illegal_transition_raises():
    with pytest.raises(IllegalTransition):
        transition(SessionState.REQUESTED, "provision_ok")  # skipped authorization!


def test_active_cannot_be_reauthorized():
    with pytest.raises(IllegalTransition):
        transition(SessionState.ACTIVE, "authorize")


# --- rule 4, executable ---------------------------------------------------------


def test_domain_purity_no_io_imports():
    """The explain-back made mechanical: list domain.py's imports, prove none is I/O.

    (`a2a_interfaces` is shapes+ports only — pydantic models, Protocols — so it is
    the one allowed dependency besides the stdlib's pure corners.)"""
    tree = ast.parse(inspect.getsource(domain))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "a2a_interfaces"}, imported
