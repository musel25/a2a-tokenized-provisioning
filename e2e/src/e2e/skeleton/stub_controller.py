"""The stub controller: the naive predicate plus a minimal session machine.

This is where the authorization predicate first appears — two phases before the real
controller (M4.1) — so the concept is in hand early. The predicate is pure (rule 4):
it decides over data the controller already fetched, importing no chain, network, or
clock. M4.1 lifts it verbatim into controller/domain.py and hardens it.
"""

from __future__ import annotations

from dataclasses import dataclass

from a2a_interfaces import (
    EntitlementReader,
    EntitlementView,
    ErrorCode,
    NetworkProvisioner,
    ResolvedPath,
    SessionState,
)
from a2a_interfaces.fixtures import RESOURCE_ID, RESOLVED_PATH

# serviceType values this controller knows how to honor. Telemetry (1) is a real
# serviceType (docs/03 §4.2) but activate() only knows apply_bandwidth, so admitting
# it here would pass the predicate and then crash mid-provision; it joins the tuple
# when the telemetry translator exists (M3.3/M4.3).
_KNOWN_SERVICE_TYPES = (0,)  # 0 = bandwidth

# Stand-in for controller/resource_map.yaml (rule 6 / ADR-005): the real
# resourceId -> topology map arrives at M4.3. In v0 we know one path; an unmapped
# resource_id is a raw KeyError — no ErrorCode names "unresolvable resource" yet,
# and M4.3 decides whether that becomes E_SCOPE or a new code (v bump).
_RESOURCE_MAP: dict[bytes, ResolvedPath] = {bytes.fromhex(RESOURCE_ID[2:]): RESOLVED_PATH}


def _resolve(resource_id: bytes) -> ResolvedPath:
    return _RESOURCE_MAP[resource_id]


class Denied(Exception):
    """Activation refused by the predicate (or proof check). Carries the ErrorCode."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass
class Session:
    session_id: str
    entitlement_id: int
    state: SessionState


def predicate(
    view: EntitlementView,
    owner: str,
    requester: str,
    now: int,
    active_ids: set[int],
) -> ErrorCode | None:
    """Return None if activation is allowed, else the first failing ErrorCode.

    Five boring checks, in order: who, when (start, end), revoked, scope, conflict.
    `now` is chain time (ADR-004); `owner` is owner_of(id); `active_ids` is the set of
    entitlements with a currently-active session (the no-double-booking guard).
    """
    if requester != owner:
        return ErrorCode.E_NOT_OWNER
    if now < view.start_time:
        return ErrorCode.E_NOT_STARTED
    if now >= view.end_time:
        return ErrorCode.E_EXPIRED
    if view.revoked:
        return ErrorCode.E_REVOKED
    if view.service_type not in _KNOWN_SERVICE_TYPES:
        return ErrorCode.E_SCOPE
    if view.id in active_ids:
        return ErrorCode.E_CONFLICT
    return None


class StubController:
    """Nonce issue/check, the predicate, and a minimal session state machine.

    Depends only on the two ports (rule 4), so the real ChainClient/GnmiProvisioner
    drop in unchanged later. Activation is synchronous; teardown has two paths that
    foreshadow the real controller (M4.5): time-driven via tick() and event-driven
    via the chain's watch_revoked.
    """

    def __init__(self, chain: EntitlementReader, net: NetworkProvisioner) -> None:
        self._chain = chain
        self._net = net
        self._sessions: dict[str, Session] = {}
        self._open_nonces: set[str] = set()
        self._nonce_seq = 0
        self._session_seq = 0
        self._chain.watch_revoked(self._on_revoked)

    def challenge(self, entitlement_id: int) -> str:
        """Issue a fresh single-use nonce (the activation proof will bind to it)."""
        nonce = f"nonce-{self._nonce_seq}"
        self._nonce_seq += 1
        self._open_nonces.add(nonce)
        return nonce

    def activate(self, entitlement_id: int, requester: str, nonce: str) -> str:
        """Honor an entitlement: check proof, run the predicate, provision. -> session_id.

        Raises Denied(ErrorCode) on any rejection. `requester` stands in for the
        address recovered from a signed proof; real recovery is M4.2.
        """
        # A set can't tell "reused" from "never issued", so both surface as
        # E_NONCE_REUSED here; M4.2's real nonce store separates them.
        if nonce not in self._open_nonces:
            raise Denied(ErrorCode.E_NONCE_REUSED)
        self._open_nonces.discard(nonce)  # burn it after one use

        view = self._chain.get(entitlement_id)
        owner = self._chain.owner_of(entitlement_id)
        now = self._chain.chain_time()
        active_ids = {
            s.entitlement_id for s in self._sessions.values() if s.state == SessionState.ACTIVE
        }
        error = predicate(view, owner, requester, now, active_ids)
        if error is not None:
            raise Denied(error)

        session_id = f"sess-{self._session_seq}"
        self._session_seq += 1
        path = _resolve(view.resource_id)
        result = self._net.apply_bandwidth(
            session_id, path, view.params.capacity_bps, view.params.qos_class
        )
        if not result.ok:
            raise Denied(ErrorCode.E_NETWORK)  # AUTHORIZED never reaches ACTIVE
        self._sessions[session_id] = Session(session_id, entitlement_id, SessionState.ACTIVE)
        return session_id

    def tick(self) -> None:
        """Time-driven teardown: re-read chain time (ADR-004) and end expired sessions."""
        now = self._chain.chain_time()
        for session in list(self._sessions.values()):
            if session.state != SessionState.ACTIVE:
                continue
            if now >= self._chain.get(session.entitlement_id).end_time:
                self.teardown(session.session_id)

    def _on_revoked(self, entitlement_id: int) -> None:
        """Event-driven teardown: the chain says #id was revoked — re-check, then end it.

        Re-reads the entitlement before acting (don't trust the event blindly; the
        chain is the source of truth, ADR-004) and tears down any active session.
        """
        if not self._chain.get(entitlement_id).revoked:
            return
        for session in list(self._sessions.values()):
            if session.entitlement_id == entitlement_id and session.state == SessionState.ACTIVE:
                self.teardown(session.session_id)

    def teardown(self, session_id: str) -> None:
        """Idempotent (rule 8): tear down the network, mark the session torn_down."""
        self._net.teardown(session_id)
        session = self._sessions.get(session_id)
        if session is not None and session.state != SessionState.TORN_DOWN:
            session.state = SessionState.TORN_DOWN

    def state(self, session_id: str) -> SessionState:
        return self._sessions[session_id].state
