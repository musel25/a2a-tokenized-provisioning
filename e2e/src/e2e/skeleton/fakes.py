"""Cardboard props: the three fakes the skeleton runs on.

Each satisfies a Protocol from `a2a_interfaces.ports` (rule 7), so the same wiring
later accepts the real adapters unchanged: FakeChain → chainmcp (landed M1.5),
FakeNet → netctl (landed M3.2/M3.4; the class itself now lives in netctl.mock).
They are deliberately dumb — a dict, two balance numbers, a recorded call-list. If a
fake starts to look like a real Ethereum or a real router, it is a bug (docs/01 M0.3
"watch for").

Bodies are added test-first; a method that raises NotImplementedError is one no test
has demanded yet.
"""

from __future__ import annotations

from collections.abc import Callable

from a2a_interfaces import (
    BandwidthParams,
    EntitlementView,
    SignedOffer,
)
from netctl.mock import MockProvisioner


def _decode_bandwidth_params(params: str) -> BandwidthParams:
    """Slice the two ABI words back into a BandwidthParams.

    Stand-in for chainmcp's ABI decoder (rule 2): the on-chain `params` blob is
    `0x` + capacity_bps (32 bytes) + qos_class (32 bytes), both big-endian. This is
    the only place the fake reads the blob, and it is two int() calls, not a codec.
    """
    body = params[2:]  # drop "0x"
    return BandwidthParams(
        capacity_bps=int(body[0:64], 16),
        qos_class=int(body[64:128], 16),
    )


class OfferAlreadyUsed(Exception):
    """A salt has already been fulfilled. Mirrors the contract's revert at M1.3."""


class OfferExpired(Exception):
    """Chain time is past the offer's valid_until. Mirrors the contract's revert at M1.3."""


class WrongConsumer(Exception):
    """A targeted offer (consumer != 0) fulfilled by someone else. Mirrors M1.3."""


class InsufficientFunds(Exception):
    """The buyer cannot pay. On the real chain this is the ERC-20 transferFrom revert."""


class FakeClock:
    """The chain clock you can advance. `now()` stands in for block.timestamp."""

    def __init__(self, now: int) -> None:
        self._now = now

    def now(self) -> int:
        return self._now

    def advance(self, seconds: int) -> None:
        self._now += seconds


class FakeChain:
    """Settlement + entitlement registry as a dict (satisfies EntitlementReader)."""

    def __init__(
        self,
        clock: FakeClock,
        balances: dict[str, int],
        next_id: int = 1,
    ) -> None:
        self._clock = clock
        self.balances = balances
        self._next_id = next_id
        self.consumed: set[str] = set()  # offer salts already fulfilled (single-use)
        self._owners: dict[int, str] = {}
        self._entitlements: dict[int, EntitlementView] = {}
        self._watchers: list[Callable[[int], None]] = []

    # --- write side: the one chain mutation, fulfill() ---------------------

    def fulfill(self, signed: SignedOffer, buyer: str) -> int:
        """Check everything, then punch the salt, move payment, mint — all or nothing.

        Mirrors the contract's fulfill (M1.3), checking in the contract's planned
        revert order: expired → consumer binding → salt → funds (signature checks
        stay out — fakes don't verify). The real chain gets atomicity for free — a
        revert rolls back every storage write in the transaction, whatever the
        order. Python has no rollback, so this fake earns "all or nothing" by
        ordering alone: every check precedes the first mutation, and a rejected
        fulfill leaves the world untouched. Returns the new entitlement id.
        """
        offer = signed.offer
        if offer.service_type != 0:  # this fake decodes bandwidth params only
            raise NotImplementedError("telemetry offers arrive with M3.3")
        if self._clock.now() > offer.valid_until:
            raise OfferExpired(offer.valid_until)
        if int(offer.consumer, 16) != 0 and offer.consumer != buyer:
            raise WrongConsumer(buyer)
        if offer.salt in self.consumed:
            raise OfferAlreadyUsed(offer.salt)
        if self.balances.get(buyer, 0) < int(offer.price):
            raise InsufficientFunds(buyer)
        # checks done — nothing below can fail, so mutation order no longer matters
        self.consumed.add(offer.salt)
        self.balances[buyer] = self.balances.get(buyer, 0) - int(offer.price)
        self.balances[offer.provider] = self.balances.get(offer.provider, 0) + int(offer.price)
        entitlement_id = self._next_id
        self._next_id += 1
        self._owners[entitlement_id] = buyer
        self._entitlements[entitlement_id] = EntitlementView(
            id=entitlement_id,
            issuer=offer.provider,
            service_type=offer.service_type,
            resource_id=bytes.fromhex(offer.resource_id[2:]),
            params=_decode_bandwidth_params(offer.params),
            start_time=offer.start_time,
            end_time=offer.end_time,
            revoked=False,
            terms_hash=bytes.fromhex(offer.terms_hash[2:]),
        )
        return entitlement_id

    def revoke(self, entitlement_id: int) -> None:
        """Flip the revoked flag (never a burn — I5) and notify watchers."""
        view = self._entitlements[entitlement_id]
        self._entitlements[entitlement_id] = view.model_copy(update={"revoked": True})
        for callback in self._watchers:
            callback(entitlement_id)

    # --- read side: the EntitlementReader port -----------------------------

    def owner_of(self, entitlement_id: int) -> str:
        return self._owners[entitlement_id]

    def get(self, entitlement_id: int) -> EntitlementView:
        return self._entitlements[entitlement_id]

    def chain_time(self) -> int:
        return self._clock.now()

    def watch_revoked(self, callback: Callable[[int], None]) -> None:
        self._watchers.append(callback)


# The recording provisioner grew up and moved out (M3.2): it now lives in netctl
# beside the real GnmiProvisioner, and both run the same contract suite (rule 7).
# The skeleton keeps its stage name.
FakeNet = MockProvisioner
