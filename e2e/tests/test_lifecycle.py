"""Walking skeleton v0 lifecycle (M0.3).

These tests are the whole play with cardboard props: Ada buys 50 Mbps from Bell,
the controller honors ticket #7, and the session is torn down at chain time t1.
Everything is fake (no signatures, no chain, no routers) — the point is to prove the
architecture's joints, and to run in CI forever after.

Run with `-s` to see the narration lines print as the lifecycle executes.
"""

from __future__ import annotations

import pytest

from a2a_interfaces import (
    ApplyResult,
    EntitlementReader,
    ErrorCode,
    NetworkProvisioner,
    ResolvedPath,
    SessionState,
)
from a2a_interfaces.fixtures import (
    ADA,
    BELL,
    BANDWIDTH_NEED,
    CAPACITY_50_MBPS,
    PRICE_10_TOK,
    QOS_CLASS,
    TICKET_ID,
    WINDOW,
)
from e2e.skeleton.fakes import FakeChain, FakeClock, FakeNet, OfferAlreadyUsed
from e2e.skeleton.scripted_agents import ScriptedConsumer, ScriptedProvider
from e2e.skeleton.stub_controller import Denied, StubController

SEED_TOK = int(PRICE_10_TOK) * 5  # Ada starts with plenty to spend


def narrate(line: str) -> None:
    """Print one epilogue line as the play runs (visible under `pytest -s`)."""
    print(line)


def _new_world():
    """Wire the cardboard props: clock just before the window, Ada funded, Bell empty."""
    clock = FakeClock(WINDOW.start - 1680)  # ~13:32, before the window opens
    chain = FakeChain(clock, balances={ADA: SEED_TOK, BELL: 0}, next_id=TICKET_ID)
    net = FakeNet()
    controller = StubController(chain, net)
    return clock, chain, net, controller, ScriptedProvider(), ScriptedConsumer()


def test_fakes_satisfy_ports():
    """Rule 7: a mock implements the SAME Protocol as the real adapter will."""
    chain = FakeChain(FakeClock(0), balances={})
    net = FakeNet()
    assert isinstance(chain, EntitlementReader)
    assert isinstance(net, NetworkProvisioner)


def test_happy_path_lifecycle():
    clock, chain, net, controller, provider, consumer = _new_world()
    need = BANDWIDTH_NEED

    # 1-3. Discover -> quote -> decide (all off-chain messages).
    narrate(f"13:31  Ada needs {need.capacity_bps // 1_000_000} Mbps {need.src}->{need.dst}")
    signed = provider.quote(need)
    decision = consumer.decide(need, signed)
    assert decision.accept
    narrate(f'13:32  Bell signs 50 Mbps/10 TOK; Ada: {{"accept": {decision.accept}}}')

    # 4. Redeem on-chain: the one write. Salt punched, payment moved, ticket minted.
    eid = chain.fulfill(signed, buyer=ADA)
    narrate(f"13:32  fulfill(): ticket #{eid} -> Ada, 10 TOK -> Bell")
    assert eid == TICKET_ID
    assert chain.owner_of(eid) == ADA
    assert chain.balances[BELL] == int(PRICE_10_TOK)
    assert chain.balances[ADA] == SEED_TOK - int(PRICE_10_TOK)
    assert signed.offer.salt in chain.consumed

    # 5-8. Activation: challenge -> proof -> predicate -> provision.
    clock.advance(1800)  # 14:02 — now inside the window
    nonce = controller.challenge(eid)
    sid = controller.activate(eid, requester=ADA, nonce=nonce)
    narrate("14:02  checklist passed; gNMI Set: police 50,000 kbps")
    assert controller.state(sid) == SessionState.ACTIVE
    assert net.applied[sid]["capacity_bps"] == CAPACITY_50_MBPS
    assert net.applied[sid]["qos_class"] == QOS_CLASS

    # 9. Teardown at chain time t1 (ADR-004: the controller re-checks chain_time).
    clock.advance(chain.get(eid).end_time - chain.chain_time())  # advance to endTime
    controller.tick()
    narrate("16:00  chain time >= endTime -> torn down")
    assert controller.state(sid) == SessionState.TORN_DOWN
    assert sid in net.torn_down
    assert sid not in net.applied


def test_replayed_offer_is_rejected():
    _, chain, _, _, provider, _ = _new_world()
    signed = provider.quote(BANDWIDTH_NEED)

    eid = chain.fulfill(signed, buyer=ADA)
    narrate(f"13:32  fulfill(): ticket #{eid} minted, salt punched")

    # The same signed offer cannot be spent twice — the salt ledger punches it once.
    with pytest.raises(OfferAlreadyUsed):
        chain.fulfill(signed, buyer=ADA)
    narrate("13:33  replay of the same offer -> rejected")

    # The rejected replay changed nothing: Bell was paid once, no second ticket minted.
    assert chain.balances[BELL] == int(PRICE_10_TOK)
    assert chain.balances[ADA] == SEED_TOK - int(PRICE_10_TOK)
    with pytest.raises(KeyError):
        chain.owner_of(eid + 1)


def test_revocation_tears_down_active_session():
    clock, chain, net, controller, provider, _ = _new_world()
    eid = chain.fulfill(provider.quote(BANDWIDTH_NEED), buyer=ADA)

    clock.advance(1800)  # inside the window
    sid = controller.activate(eid, requester=ADA, nonce=controller.challenge(eid))
    assert controller.state(sid) == SessionState.ACTIVE

    # Bell revokes #7 mid-window; the chain fires watch_revoked and the controller
    # tears the session down without waiting for the window to end (event-driven).
    chain.revoke(eid)
    narrate("15:10  Bell revokes #7 -> session torn down mid-window")
    assert controller.state(sid) == SessionState.TORN_DOWN
    assert sid in net.torn_down


class _FailingNet(FakeNet):
    """A provisii saw u created 3 files, but i didnt get fully what u did, no documentation, no narrative no examples, not shown how each specific piece of code serves a purpose, no visuals, go ahead and do that so i understand in detailoner whose apply_bandwidth refuses — the netctl-said-no joint."""

    def apply_bandwidth(
        self, session_id: str, path: ResolvedPath, capacity_bps: int, qos_class: int
    ) -> ApplyResult:
        return ApplyResult(ok=False, detail="lab unreachable")


def test_activation_denied_when_provisioner_fails():
    clock = FakeClock(WINDOW.start + 60)  # inside the window, so only the net can fail
    chain = FakeChain(clock, balances={ADA: SEED_TOK, BELL: 0}, next_id=TICKET_ID)
    controller = StubController(chain, _FailingNet())
    eid = chain.fulfill(ScriptedProvider().quote(BANDWIDTH_NEED), buyer=ADA)

    with pytest.raises(Denied) as exc:
        controller.activate(eid, requester=ADA, nonce=controller.challenge(eid))
    assert exc.value.code == ErrorCode.E_NETWORK
