"""Cardboard props: the three fakes the skeleton runs on.

Each satisfies a Protocol from `a2a_interfaces.ports` (rule 7), so the same wiring
later accepts the real adapters unchanged: FakeChain → chainmcp (M1.5), FakeNet →
netctl (M3.4). They are deliberately dumb — a dict, two balance numbers, a recorded
call-list. If a fake starts to look like a real Ethereum or a real router, it is a
bug (docs/01 M0.3 "watch for").

Bodies are added test-first; a method that raises NotImplementedError is one no test
has demanded yet.
"""

from __future__ import annotations

from collections.abc import Callable

from a2a_interfaces import (
    ApplyResult,
    BandwidthParams,
    EntitlementView,
    ResolvedNode,
    ResolvedPath,
    SignedOffer,
)


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
        """Punch the salt, move payment, mint the entitlement — all or nothing.

        Mirrors the contract's fulfill (M1.3): the buyer pays the provider and an
        entitlement is minted to the buyer in one motion. "Atomic" here means the
        Python sense — checks happen before any mutation, so a rejected fulfill
        leaves the world untouched. Returns the new entitlement id.
        """
        offer = signed.offer
        if offer.salt in self.consumed:  # checked before any mutation: all-or-nothing
            raise OfferAlreadyUsed(offer.salt)
        self.consumed.add(offer.salt)
        self.balances[buyer] -= int(offer.price)
        self.balances[offer.provider] += int(offer.price)
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


class FakeNet:
    """Records apply_*/teardown calls instead of touching a router (NetworkProvisioner)."""

    def __init__(self) -> None:
        self.applied: dict[str, dict] = {}
        self.torn_down: list[str] = []

    def apply_bandwidth(
        self,
        session_id: str,
        path: ResolvedPath,
        capacity_bps: int,
        qos_class: int,
    ) -> ApplyResult:
        self.applied[session_id] = {
            "path": path,
            "capacity_bps": capacity_bps,
            "qos_class": qos_class,
        }
        return ApplyResult(ok=True)

    def apply_telemetry(
        self,
        session_id: str,
        target: ResolvedNode,
        sensor_paths: list[str],
        collector_endpoint: str,
        sample_interval_s: int,
    ) -> ApplyResult:
        raise NotImplementedError

    def teardown(self, session_id: str) -> ApplyResult:
        # Idempotent (rule 8): pop with default, never raise on a second call.
        self.applied.pop(session_id, None)
        self.torn_down.append(session_id)
        return ApplyResult(ok=True)

    def health(self) -> bool:
        return True
