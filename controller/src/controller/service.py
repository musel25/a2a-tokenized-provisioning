"""ControllerService — the production stub_controller: orchestration over the ports.

Everything here works on INJECTED dependencies (the two Protocols, the AuthStore, the
resource map) and touches no I/O of its own — which is why M4.4's httpx tests run it
against cardboard and M4.5's wiring runs it against Anvil + srl1 without changing a
line. The API layer above parses and maps; the domain below judges; this class walks
the session through its state machine.
"""

from __future__ import annotations

from dataclasses import dataclass

from a2a_interfaces import (
    EntitlementReader,
    ErrorCode,
    NetworkProvisioner,
    ResolvedNode,
    ResolvedPath,
    SessionInfo,
    SessionState,
)

from .auth import AuthStore, Challenge
from .domain import predicate, transition
from .translators import UnmappedResource, translate

_ACTION_KINDS = {"bandwidth": 0, "telemetry": 1}


class Denied(Exception):
    """Activation/lookup refused; carries the ErrorCode the API maps to a status."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass
class _Session:
    session_id: str
    entitlement_id: int
    state: SessionState
    since: int
    expires_at: int


class ControllerService:
    def __init__(
        self,
        reader: EntitlementReader,
        provisioner: NetworkProvisioner,
        auth: AuthStore,
        resource_map: dict[bytes, ResolvedPath | ResolvedNode],
    ) -> None:
        self._reader = reader
        self._net = provisioner
        self._auth = auth
        self._resource_map = resource_map
        self._sessions: dict[str, _Session] = {}
        self._seq = 0

    # --- the three endpoints' logic (docs/03 §3.1) ---------------------------

    def challenge(self, entitlement_id: int) -> Challenge:
        self._view(entitlement_id)  # unknown tickets don't get challenges
        return self._auth.issue(entitlement_id, now=self._reader.chain_time())

    def activate(
        self, entitlement_id: int, action_kind: str, nonce: str, signature: str
    ) -> SessionInfo:
        view = self._view(entitlement_id)
        owner = self._reader.owner_of(entitlement_id)
        now = self._reader.chain_time()

        denial = self._auth.verify(entitlement_id, nonce, signature, owner, now)
        if denial is not None:
            raise Denied(denial)
        # The proof bound the requester to the owner's key, so requester == owner from
        # here on; the predicate's E_NOT_OWNER path belongs to callers without proofs.
        active_ids = {
            s.entitlement_id for s in self._sessions.values() if s.state == SessionState.ACTIVE
        }
        denial = predicate(view, owner, owner, now, active_ids)
        if denial is not None:
            raise Denied(denial)
        if _ACTION_KINDS.get(action_kind) != view.service_type:
            raise Denied(ErrorCode.E_SCOPE)  # a telemetry action on a bandwidth ticket

        session_id = f"ent{entitlement_id}-a{self._seq}"
        self._seq += 1
        state = transition(SessionState.REQUESTED, "authorize")
        try:
            calls = translate(session_id, view, self._resource_map)
        except UnmappedResource as err:
            raise Denied(ErrorCode.E_SCOPE) from err

        for call in calls:
            result = getattr(self._net, call.method)(**call.kwargs)
            if not result.ok:
                # partial application must not linger: idempotent teardown, then deny
                self._net.teardown(session_id)
                self._sessions[session_id] = _Session(
                    session_id,
                    entitlement_id,
                    transition(state, "provision_failed"),
                    since=now,
                    expires_at=view.end_time,
                )
                raise Denied(ErrorCode.E_NETWORK)
        session = _Session(
            session_id,
            entitlement_id,
            transition(state, "provision_ok"),
            since=now,
            expires_at=view.end_time,
        )
        self._sessions[session_id] = session
        return self._info(session)

    def teardown(self, session_id: str) -> SessionInfo:
        """Idempotent (rule 8): unknown or already-down sessions answer torn_down."""
        session = self._sessions.get(session_id)
        if session is None:
            self._net.teardown(session_id)  # belt: clear any stray config by name
            return SessionInfo(
                session_id=session_id,
                entitlement_id=0,
                state=SessionState.TORN_DOWN,
                since=0,
                expires_at=0,
            )
        self._net.teardown(session_id)
        session.state = transition(session.state, "teardown")
        return self._info(session)

    def session(self, session_id: str) -> SessionInfo:
        session = self._sessions.get(session_id)
        if session is None:
            raise Denied(ErrorCode.E_UNKNOWN_ENTITLEMENT)
        return self._info(session)

    # --- the two autonomous teardown paths (docs/03 §3.3) ---------------------

    def tick(self) -> list[str]:
        """Time-driven: re-read chain time (ADR-004) and end sessions past t1."""
        now = self._reader.chain_time()
        ended = []
        for session in list(self._sessions.values()):
            if session.state == SessionState.ACTIVE and now >= session.expires_at:
                self.teardown(session.session_id)
                ended.append(session.session_id)
        return ended

    def handle_revoked(self, entitlement_id: int) -> None:
        """Event-driven: the chain says #id was revoked — re-check, then end it.
        (Don't trust the event blindly; the chain is the source of truth.)"""
        if not self._reader.get(entitlement_id).revoked:
            return
        for session in list(self._sessions.values()):
            if session.entitlement_id == entitlement_id and session.state == SessionState.ACTIVE:
                self.teardown(session.session_id)

    # --- plumbing --------------------------------------------------------------

    def _view(self, entitlement_id: int):
        try:
            return self._reader.get(entitlement_id)
        except KeyError:
            raise Denied(ErrorCode.E_UNKNOWN_ENTITLEMENT) from None

    def _info(self, session: _Session) -> SessionInfo:
        return SessionInfo(
            session_id=session.session_id,
            entitlement_id=session.entitlement_id,
            state=session.state,
            since=session.since,
            expires_at=session.expires_at,
        )
