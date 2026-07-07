"""The pure domain: the predicate and the session state machine (docs/05 §2–§3).

This module is the controller's whole judgment, and it imports NO I/O — no web3, no
pygnmi, no HTTP, no filesystem (rule 4; `test_domain_purity` inspects the imports).
It decides over facts someone else already fetched; adapters live at the edges. The
predicate was born in the M0.3 skeleton (stub_controller), matured here; the stub now
imports THIS one, so there is exactly one bouncer in the codebase.
"""

from __future__ import annotations

from a2a_interfaces import EntitlementView, ErrorCode, SessionState

# serviceTypes the controller can translate into provisioner calls (docs/05 §5).
# Admitting a type with no translator would pass the predicate and then crash
# mid-provision — E_SCOPE is the honest early answer.
KNOWN_SERVICE_TYPES = (0, 1)  # 0 = bandwidth, 1 = telemetry (both real since M3.3)


def predicate(
    view: EntitlementView,
    owner: str,
    requester: str,
    now: int,
    active_ids: set[int],
    known_service_types: tuple[int, ...] = KNOWN_SERVICE_TYPES,
) -> ErrorCode | None:
    """Return None if activation is allowed, else the FIRST failing ErrorCode.

    Order is contract (docs/05 §2): who → not-yet → expired → revoked → scope →
    conflict. `now` is chain time (ADR-004); `owner` is `ownerOf(id)`; `active_ids`
    are entitlements with a currently-active session (the no-double-booking guard).
    `known_service_types` is caller-dependent by definition — "has a translator" means
    *this* controller's translators (the M0.3 stub only wires bandwidth, for example).
    """
    if requester != owner:
        return ErrorCode.E_NOT_OWNER
    if now < view.start_time:
        return ErrorCode.E_NOT_STARTED
    if now >= view.end_time:
        return ErrorCode.E_EXPIRED
    if view.revoked:
        return ErrorCode.E_REVOKED
    if view.service_type not in known_service_types:
        return ErrorCode.E_SCOPE
    if view.id in active_ids:
        return ErrorCode.E_CONFLICT
    return None


# --- the session state machine, as data (docs/05 §3) --------------------------

# (state, event) → next state. Anything absent is an IllegalTransition — except the
# absorbing rule below, which encodes rule 8 (teardown is idempotent, never an error).
TRANSITIONS: dict[tuple[SessionState, str], SessionState] = {
    (SessionState.REQUESTED, "authorize"): SessionState.AUTHORIZED,
    (SessionState.REQUESTED, "deny"): SessionState.FAILED,
    (SessionState.AUTHORIZED, "provision_ok"): SessionState.ACTIVE,
    (SessionState.AUTHORIZED, "provision_failed"): SessionState.FAILED,
    (SessionState.ACTIVE, "teardown"): SessionState.TORN_DOWN,
}

# Terminal states absorb further teardowns silently (rule 8): tearing down what is
# already down is a success, not a protocol violation.
_ABSORBED = {
    (SessionState.TORN_DOWN, "teardown"),
    (SessionState.FAILED, "teardown"),
}


class IllegalTransition(Exception):
    """The state machine was asked something its diagram doesn't draw — a programming
    error in the caller, never a user-facing denial."""

    def __init__(self, state: SessionState, event: str) -> None:
        super().__init__(f"no transition for event {event!r} in state {state.value!r}")
        self.state = state
        self.event = event


def transition(state: SessionState, event: str) -> SessionState:
    """The one legal way to move a session; illegal moves raise, absorbed moves stay."""
    if (state, event) in _ABSORBED:
        return state
    try:
        return TRANSITIONS[(state, event)]
    except KeyError:
        raise IllegalTransition(state, event) from None
