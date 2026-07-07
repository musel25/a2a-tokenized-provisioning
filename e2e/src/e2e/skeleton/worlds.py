"""Worlds: one lifecycle-test surface, three realities (SKELETON_PROFILE).

The lifecycle tests are the play's script; a World is the stage crew. `mock` wires the
M0.3 cardboard props; `chain` puts a live Anvil + the real contracts + ChainClients
under the SAME script (skeleton v1: the 10 TOK and ticket #7 become real on-chain
state); `chain+net` adds the real router (skeleton v2: the 50 Mbps becomes a real
policer on srl1). The play's lines never change — that is the whole point.

What a world must provide (duck-typed; all classes below):
  reader           EntitlementReader (what the controller sees)
  net              NetworkProvisioner (FakeNet until M3.4's chain+net)
  controller       StubController wired to (reader, net)
  provider/consumer  the scripted judgment slots
  quote_targeted(consumer)  a consumer-bound SignedOffer, PROPERLY signed — on a real
                   chain you cannot retarget after signing (that's BadSignature)
  fulfill(signed, buyer)  buyer redeems; raises the fakes' exception classes
  balance_of(addr) / salt_consumed(signed) / advance_time(s) / revoke(eid)
  provisioned(sid) / torn_down(sid)  network state, read from wherever it really lives

Deliberate mapping at the fulfill edge: ChainRevert names → the skeleton's exception
classes. The three shared names match one-for-one (that parity was built in M1.3);
the ERC-20 balance/allowance reverts are the chain's spelling of InsufficientFunds.
"""

from __future__ import annotations

import threading
import time

from a2a_interfaces import SignedOffer
from a2a_interfaces.fixtures import (
    ADA,
    BELL,
    CANONICAL_OFFER,
    PRICE_10_TOK,
    QOS_CLASS,
    TERMS_DOC,
    TICKET_ID,
    WINDOW,
)

from .fakes import (
    FakeChain,
    FakeClock,
    FakeNet,
    InsufficientFunds,
    OfferAlreadyUsed,
    OfferExpired,
    WrongConsumer,
)
from .scripted_agents import ScriptedConsumer, ScriptedProvider
from .stub_controller import StubController

SEED_TOK = int(PRICE_10_TOK) * 5  # Ada starts with plenty to spend
STORY_TIME = WINDOW.start - 1680  # ~13:32, just before the window — both worlds start here

# Anvil account #3: has ETH for gas, deliberately NEVER given TOK — the broke buyer
# in the underfunded deny path (both worlds treat an unknown address as TOK-broke).
MALLORY = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"


class MockWorld:
    """The M0.3 cardboard props, boxed behind the world surface."""

    def __init__(self) -> None:
        self.clock = FakeClock(STORY_TIME)
        self.chain = FakeChain(self.clock, balances={ADA: SEED_TOK, BELL: 0}, next_id=TICKET_ID)
        self.reader = self.chain
        self.net = FakeNet()
        self.controller = StubController(self.chain, self.net)
        self.provider = ScriptedProvider()
        self.consumer = ScriptedConsumer()

    def quote_targeted(self, consumer: str) -> SignedOffer:
        open_offer = self.provider.quote(None)
        return open_offer.model_copy(
            update={"offer": open_offer.offer.model_copy(update={"consumer": consumer})}
        )

    def fulfill(self, signed: SignedOffer, buyer: str) -> int:
        return self.chain.fulfill(signed, buyer=buyer)

    def balance_of(self, address: str) -> int:
        return self.chain.balances.get(address, 0)

    def salt_consumed(self, signed: SignedOffer) -> bool:
        return signed.offer.salt in self.chain.consumed

    def advance_time(self, seconds: int) -> None:
        self.clock.advance(seconds)

    def revoke(self, entitlement_id: int) -> None:
        self.chain.revoke(entitlement_id)

    def provisioned(self, session_id: str) -> dict | None:
        """What the network holds for this session, or None — the world-level view
        that lets one script assert against a recording fake AND a real router."""
        record = self.net.applied.get(session_id)
        if record is None:
            return None
        return {"capacity_bps": record["capacity_bps"], "qos_class": record["qos_class"]}

    def torn_down(self, session_id: str) -> bool:
        return session_id in self.net.torn_down and session_id not in self.net.applied

    def close(self) -> None:
        pass


class ChainWorld:
    """Skeleton v1: same play, real chain. Three ChainClients (one per key holder —
    rule 2: identity == client), the controller reading through its own keyless-in-
    spirit client, and FakeNet still playing the network (real routers are M3.4)."""

    _ERRORS = {
        "OfferExpired": OfferExpired,
        "WrongConsumer": WrongConsumer,
        "OfferAlreadyUsed": OfferAlreadyUsed,
        "ERC20InsufficientBalance": InsufficientFunds,
        "ERC20InsufficientAllowance": InsufficientFunds,
    }

    def __init__(self, anvil) -> None:
        from chainmcp.testing import ANVIL_KEYS

        make = _client_factory(anvil)
        self.ada = make(ANVIL_KEYS["ada"])
        self.bell = make(ANVIL_KEYS["bell"])
        self.carol = make(ANVIL_KEYS["carol"])
        # The controller's reader: Carol's key merely gives it an identity to read
        # from — it never signs or spends here. Accepted v1 shortcut: a keyless
        # read-only ChainClient doesn't exist yet; M4.5 (which wires the REAL
        # controller) must ship it — the controller holding any signing power, even
        # unused, is against rule 2's spirit.
        self._anvil = anvil
        self.reader = self.carol
        self.net = self._make_net()
        self.controller = StubController(self.reader, self.net)
        # Registered AFTER the controller's watcher: when this fires, the controller's
        # callback for the same event has already run (same polling thread, in order).
        self._revoked = threading.Event()
        self.reader.watch_revoked(lambda _id: self._revoked.set())
        self.provider = _SigningProvider(self.bell)
        self.consumer = ScriptedConsumer()
        self.mallory = make(ANVIL_KEYS["mallory"])  # the TOK-broke buyer of the deny paths
        self._clients = {ADA: self.ada, BELL: self.bell, MALLORY: self.mallory}

    def quote_targeted(self, consumer: str) -> SignedOffer:
        bound = CANONICAL_OFFER.model_copy(update={"consumer": consumer})
        return self.bell.sign_offer(bound, terms_doc=TERMS_DOC)

    def fulfill(self, signed: SignedOffer, buyer: str) -> int:
        _, entitlement_id = self._fulfill_as(self._clients[buyer], signed)
        return entitlement_id

    def _fulfill_as(self, client, signed: SignedOffer):
        from chainmcp import ChainRevert

        try:
            return client.approve_and_fulfill(signed)
        except ChainRevert as err:
            exc = self._ERRORS.get(err.name)
            if exc is not None:
                raise exc(err.name) from err
            raise

    def balance_of(self, address: str) -> int:
        return self.ada.tok_balance(address)

    def salt_consumed(self, signed: SignedOffer) -> bool:
        return self.ada.offer_consumed(signed.offer)

    def advance_time(self, seconds: int) -> None:
        self._anvil.increase_time(self.ada._w3, seconds)

    def revoke(self, entitlement_id: int) -> None:
        """Bell pulls the flag; block until the watcher delivered it (chain events are
        asynchronous — the play's script is not)."""
        self._revoked.clear()
        self.bell.revoke(entitlement_id)
        if not self._revoked.wait(timeout=5):
            raise TimeoutError("Revoked event not observed within 5s")
        # Same-thread callback ordering guarantees the controller acted before this
        # event fired; a beat for the state write to settle costs nothing.
        time.sleep(0.05)

    def _make_net(self):
        """FakeNet in skeleton v1; ChainNetWorld overrides with the real hands."""
        return FakeNet()

    def provisioned(self, session_id: str) -> dict | None:
        record = self.net.applied.get(session_id)
        if record is None:
            return None
        return {"capacity_bps": record["capacity_bps"], "qos_class": record["qos_class"]}

    def torn_down(self, session_id: str) -> bool:
        return session_id in self.net.torn_down and session_id not in self.net.applied

    def close(self) -> None:
        for client in (self.ada, self.bell, self.carol, self.mallory):
            client.close()


class ChainNetWorld(ChainWorld):
    """Skeleton v2: real chain AND real router — the same script now leaves a policer
    on srl1 and removes it at t1 (or at revocation). Only `_make_net` and the two
    network-inspection helpers differ from v1; the play's lines are untouched."""

    def _make_net(self):
        from netctl.connect import GnmiTarget
        from netctl.provisioner import GnmiProvisioner
        from netctl.testing import lab_ipv4

        ip = lab_ipv4()
        if ip is None:
            raise RuntimeError(
                "SKELETON_PROFILE=chain+net needs the live lab "
                "(containerlab deploy -t netlab/topology.clab.yml)"
            )
        self.provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=ip, tls_name="srl1")})
        return self.provisioner

    def provisioned(self, session_id: str) -> dict | None:
        """Read the session's policer OFF THE ROUTER — the assertion is against
        reality, not a recording."""
        from netctl import paths
        from netctl.provisioner import _denamespace

        client = self.provisioner._client("srl1")
        response = client.get(
            path=[paths.policer_template(f"a2a-{session_id}")],
            encoding="json_ietf",
            datatype="config",
        )
        for update in response["notification"][0].get("update") or []:
            policers = _denamespace(update["val"] or {}).get("policer", [])
            if policers:
                return {
                    "capacity_bps": policers[0]["peak-rate-kbps"] * 1000,
                    "qos_class": QOS_CLASS,  # single class in v0; not on the router
                }
        return None

    def torn_down(self, session_id: str) -> bool:
        return self.provisioned(session_id) is None

    def close(self) -> None:
        # Zombie-policer sweep (docs/01 M3.4 "watch for"): even a FAILED test must not
        # leave config on the router, or every later run measures a lie.
        from netctl import paths
        from netctl.provisioner import _denamespace

        try:
            client = self.provisioner._client("srl1")
            response = client.get(
                path=[paths.QOS_POLICER_TEMPLATES], encoding="json_ietf", datatype="config"
            )
            for update in response["notification"][0].get("update") or []:
                for template in _denamespace(update["val"] or {}).get("policer-template", []):
                    name = template.get("name", "")
                    if name.startswith("a2a-"):
                        self.provisioner.teardown(name.removeprefix("a2a-"))
        finally:
            self.provisioner.close()
            super().close()


class _SigningProvider:
    """Bell's judgment slot, still scripted — but the signature is real now."""

    def __init__(self, bell_client) -> None:
        self._bell = bell_client

    def quote(self, need) -> SignedOffer:
        return self._bell.sign_offer(CANONICAL_OFFER, terms_doc=TERMS_DOC)


def _client_factory(anvil):
    from chainmcp import ChainClient

    def make(key: str) -> ChainClient:
        return ChainClient(anvil.rpc_url, key, deployment=anvil.deployment, poll_interval=0.2)

    return make


def seed_chain(anvil) -> None:
    """One-time stage dressing, run before the first snapshot: fund the cast and make
    the story literally true — Bell sold six tickets before Ada's, so the canonical
    purchase in every test mints ticket #7 (the mock's next_id=7, made physical)."""
    from chainmcp.testing import ANVIL_KEYS

    make = _client_factory(anvil)
    ada, bell, carol = (make(ANVIL_KEYS[name]) for name in ("ada", "bell", "carol"))
    try:
        ada.faucet(SEED_TOK)
        carol.faucet(int(PRICE_10_TOK) * 6)
        for i in range(1, TICKET_ID):
            pre_sale = CANONICAL_OFFER.model_copy(update={"salt": "0x" + f"{i:064x}"})
            _, entitlement_id = carol.approve_and_fulfill(bell.sign_offer(pre_sale))
            assert entitlement_id == i
    finally:
        for client in (ada, bell, carol):
            client.close()
