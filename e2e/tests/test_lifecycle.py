"""Walking skeleton lifecycle (M0.3 → M1.5).

These tests are the whole play: Ada buys 50 Mbps from Bell, the controller honors
ticket #7, and the session is torn down at chain time t1. The `world` fixture decides
what's real (conftest): profile `mock` is the M0.3 cardboard, profile `chain` is
skeleton v1 — a live Anvil where the same script mints a real ERC-721 and moves real
TOK. The script itself does not change between realities; that is the point.

Run with `-s` to see the narration lines print as the lifecycle executes.
`SKELETON_PROFILE=chain uv run pytest e2e/` runs it against the real contracts.

Balance assertions are DELTAS, not absolutes: on the chain profile Bell already
earned 60 TOK selling tickets #1–#6 (the seeding that makes Ada's ticket literally
the seventh), and pinning absolutes would couple the script to stage dressing.
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
)
from e2e.skeleton.fakes import (
    FakeChain,
    FakeClock,
    FakeNet,
    InsufficientFunds,
    OfferAlreadyUsed,
    OfferExpired,
    WrongConsumer,
)
from e2e.skeleton.stub_controller import Denied, StubController
from e2e.skeleton.worlds import MALLORY

PRICE = int(PRICE_10_TOK)


def narrate(line: str) -> None:
    """Print one epilogue line as the play runs (visible under `pytest -s`)."""
    print(line)


def test_fakes_satisfy_ports():
    """Rule 7: a mock implements the SAME Protocol as the real adapter.

    (The real adapter's side of this promise is chainmcp's
    test_client_satisfies_the_reader_port — same Protocol, both directions.)
    """
    chain = FakeChain(FakeClock(0), balances={})
    net = FakeNet()
    assert isinstance(chain, EntitlementReader)
    assert isinstance(net, NetworkProvisioner)


def test_happy_path_lifecycle(world):
    need = BANDWIDTH_NEED

    # 1-3. Discover -> quote -> decide (all off-chain messages).
    narrate(f"13:31  Ada needs {need.capacity_bps // 1_000_000} Mbps {need.src}->{need.dst}")
    signed = world.provider.quote(need)
    decision = world.consumer.decide(need, signed)
    assert decision.accept
    narrate(f'13:32  Bell signs 50 Mbps/10 TOK; Ada: {{"accept": {decision.accept}}}')

    # 4. Redeem on-chain: the one write. Salt punched, payment moved, ticket minted.
    ada_before = world.balance_of(ADA)
    bell_before = world.balance_of(BELL)
    eid = world.fulfill(signed, buyer=ADA)
    narrate(f"13:32  fulfill(): ticket #{eid} -> Ada, 10 TOK -> Bell")
    assert eid == TICKET_ID
    assert world.reader.owner_of(eid) == ADA
    assert world.balance_of(BELL) == bell_before + PRICE
    assert world.balance_of(ADA) == ada_before - PRICE
    assert world.salt_consumed(signed)

    # 5-8. Activation: challenge -> proof -> predicate -> provision.
    world.advance_time(1800)  # 14:02 — now inside the window
    nonce = world.controller.challenge(eid)
    sid = world.controller.activate(eid, requester=ADA, nonce=nonce)
    narrate("14:02  checklist passed; gNMI Set: police 50,000 kbps")
    assert world.controller.state(sid) == SessionState.ACTIVE
    provisioned = world.provisioned(sid)
    assert provisioned is not None  # in chain+net this is read OFF the router
    assert provisioned["capacity_bps"] == CAPACITY_50_MBPS
    assert provisioned["qos_class"] == QOS_CLASS

    # 9. Teardown at chain time t1 (ADR-004: the controller re-checks chain_time).
    view = world.reader.get(eid)
    world.advance_time(view.end_time - world.reader.chain_time())
    world.controller.tick()
    narrate("16:00  chain time >= endTime -> torn down")
    assert world.controller.state(sid) == SessionState.TORN_DOWN
    assert world.torn_down(sid)


def test_replayed_offer_is_rejected(world):
    signed = world.provider.quote(BANDWIDTH_NEED)
    bell_before = world.balance_of(BELL)

    eid = world.fulfill(signed, buyer=ADA)
    narrate(f"13:32  fulfill(): ticket #{eid} minted, salt punched")

    # The same signed offer cannot be spent twice — the salt ledger punches it once.
    with pytest.raises(OfferAlreadyUsed):
        world.fulfill(signed, buyer=ADA)
    narrate("13:33  replay of the same offer -> rejected")

    # The rejected replay changed nothing: Bell was paid once, no second ticket minted.
    assert world.balance_of(BELL) == bell_before + PRICE
    with pytest.raises(KeyError):
        world.reader.owner_of(eid + 1)


def test_revocation_tears_down_active_session(world):
    eid = world.fulfill(world.provider.quote(BANDWIDTH_NEED), buyer=ADA)

    world.advance_time(1800)  # inside the window
    sid = world.controller.activate(eid, requester=ADA, nonce=world.controller.challenge(eid))
    assert world.controller.state(sid) == SessionState.ACTIVE

    # Bell revokes #7 mid-window; the chain fires watch_revoked and the controller
    # tears the session down without waiting for the window to end (event-driven).
    world.revoke(eid)
    narrate("15:10  Bell revokes #7 -> session torn down mid-window")
    assert world.controller.state(sid) == SessionState.TORN_DOWN
    assert world.torn_down(sid)


class _FailingNet(FakeNet):
    """A provisioner whose apply_bandwidth refuses — the netctl-said-no joint."""

    def apply_bandwidth(
        self, session_id: str, path: ResolvedPath, capacity_bps: int, qos_class: int
    ) -> ApplyResult:
        return ApplyResult(ok=False, detail="lab unreachable")


def test_activation_denied_when_provisioner_fails(world):
    eid = world.fulfill(world.provider.quote(BANDWIDTH_NEED), buyer=ADA)
    world.advance_time(1800)  # inside the window, so only the net can fail

    # Same reader, sabotaged hands: a controller wired to a refusing provisioner.
    controller = StubController(world.reader, _FailingNet())
    with pytest.raises(Denied) as exc:
        controller.activate(eid, requester=ADA, nonce=controller.challenge(eid))
    assert exc.value.code == ErrorCode.E_NETWORK


# --- fulfill deny paths: one test per check, in the contract's revert order ------


def _assert_fulfill_left_no_trace(world, signed, ada_before: int, bell_before: int) -> None:
    """The atomicity claim (I3): a rejected fulfill mutated nothing."""
    assert not world.salt_consumed(signed)
    assert world.balance_of(ADA) == ada_before
    assert world.balance_of(BELL) == bell_before
    with pytest.raises(KeyError):
        world.reader.owner_of(TICKET_ID)  # nothing was minted


def test_expired_offer_is_rejected(world):
    signed = world.provider.quote(BANDWIDTH_NEED)
    ada_before, bell_before = world.balance_of(ADA), world.balance_of(BELL)

    world.advance_time(signed.offer.valid_until - world.reader.chain_time() + 1)
    with pytest.raises(OfferExpired):
        world.fulfill(signed, buyer=ADA)
    _assert_fulfill_left_no_trace(world, signed, ada_before, bell_before)


def test_targeted_offer_rejects_any_other_buyer(world):
    # Bell writes Ada's name on the ticket — and SIGNS it that way (on a real chain
    # you cannot retarget an offer after signing; that would be BadSignature).
    targeted = world.quote_targeted(ADA)
    ada_before, bell_before = world.balance_of(ADA), world.balance_of(BELL)

    with pytest.raises(WrongConsumer):
        world.fulfill(targeted, buyer=BELL)
    _assert_fulfill_left_no_trace(world, targeted, ada_before, bell_before)

    assert world.reader.owner_of(world.fulfill(targeted, buyer=ADA)) == ADA  # she still can


def test_underfunded_buyer_is_rejected(world):
    signed = world.provider.quote(BANDWIDTH_NEED)
    ada_before, bell_before = world.balance_of(ADA), world.balance_of(BELL)
    assert world.balance_of(MALLORY) == 0  # gas money, yes; TOK, none

    # Mallory grabs the open offer without the 10 TOK to pay for it — in the chain
    # profile this is the ERC-20 balance revert wearing the fake's exception name.
    with pytest.raises(InsufficientFunds):
        world.fulfill(signed, buyer=MALLORY)
    _assert_fulfill_left_no_trace(world, signed, ada_before, bell_before)


def test_proof_template_agrees_across_packages():
    """Cross-package parity: chainmcp builds the activation-proof string the controller
    parses. Neither may import the other (import direction!), so both answer to
    docs/03 §3.2 — and this test, the only place both sides meet."""
    from chainmcp import activation_proof_message
    from controller.auth import proof_message

    assert activation_proof_message("bw-ctrl-1", "0xabcd", 7, 1757945100) == proof_message(
        "bw-ctrl-1", "0xabcd", 7, 1757945100
    )
