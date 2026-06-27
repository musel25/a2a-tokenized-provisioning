"""The canonical example — one source of truth for story, docs, and tests.

Ada buys 50 Mbps from Bell for 10 TOK; the entitlement is ticket #7. These exact
numbers appear in docs/00-the-story.md and every test that needs a concrete case.
Change them here or not at all (CLAUDE.md conventions).

Anything cryptographic here (signature, terms_hash) is a syntactically-valid
*placeholder*: real signing and keccak hashing live in chainmcp (M1.5).
"""

from __future__ import annotations

from .models import (
    BandwidthNeed,
    BandwidthParams,
    DecisionOutput,
    EntitlementView,
    Offer,
    ResolvedPath,
    SignedOffer,
    TelemetryNeed,
    TimeWindow,
)

# --- the cast and the constants --------------------------------------------

ADA = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # consumer/buyer, owns #7 (anvil-0)
BELL = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # provider/issuer, paid (anvil-1)
ZERO_ADDRESS = "0x" + "0" * 40  # open offer: anyone may fulfill
MOCK_TOK = "0x5FbDB2315678afecb367f032d93F642f64180aa3"  # payment token (anvil deploy[0])

TICKET_ID = 7
PRICE_10_TOK = "10000000000000000000"  # 10 * 1e18, decimal string (§0)
CAPACITY_50_MBPS = 50_000_000  # bits per second
QOS_CLASS = 1

WINDOW = TimeWindow(start=1757944800, end=1757952000)  # absolute, unix seconds (§1.3)

# resource_id of #7, opaque 32-byte value; terms_hash/salt are placeholders.
RESOURCE_ID = "0x" + f"{TICKET_ID:064x}"
SALT = "0x" + f"{0x5A17:064x}"
TERMS_HASH = "0x" + "22" * 32

# ABI encoding of (uint64 capacityBps, uint8 qosClass): two right-aligned words.
BANDWIDTH_PARAMS_ABI = "0x" + f"{CAPACITY_50_MBPS:064x}" + f"{QOS_CLASS:064x}"

TERMS_DOC = {"sla": {"latency_ms": 20, "loss_pct": 0.1}, "notes": "best effort beyond rate"}


# --- canonical objects ------------------------------------------------------

BANDWIDTH_NEED = BandwidthNeed(
    src="hostA",
    dst="hostB",
    capacity_bps=CAPACITY_50_MBPS,
    qos_class=QOS_CLASS,
    window=WINDOW,
)

TELEMETRY_NEED = TelemetryNeed(
    target="leafA",
    sensor_paths=["/interface[name=ethernet-1/1]/statistics"],
    collector_endpoint="10.0.0.50:57000",
    sample_interval_s=10,
    window=WINDOW,
)

CANONICAL_OFFER = Offer(
    provider=BELL,
    consumer=ZERO_ADDRESS,  # open offer (v0 default, §1.2)
    service_type=0,
    resource_id=RESOURCE_ID,
    params=BANDWIDTH_PARAMS_ABI,
    start_time=WINDOW.start,
    end_time=WINDOW.end,
    payment_token=MOCK_TOK,
    price=PRICE_10_TOK,
    valid_until=1757946000,
    salt=SALT,
    terms_hash=TERMS_HASH,
)

CANONICAL_SIGNED_OFFER = SignedOffer(
    offer=CANONICAL_OFFER,
    signature="0x" + "ab" * 65,  # placeholder 65-byte signature (real one: chainmcp)
    terms_doc=TERMS_DOC,
)

# The entitlement as the controller reads it once #7 is minted (owner is ADA).
CANONICAL_ENTITLEMENT_VIEW = EntitlementView(
    id=TICKET_ID,
    issuer=BELL,
    service_type=0,
    resource_id=bytes.fromhex(RESOURCE_ID[2:]),
    params=BandwidthParams(capacity_bps=CAPACITY_50_MBPS, qos_class=QOS_CLASS),
    start_time=WINDOW.start,
    end_time=WINDOW.end,
    revoked=False,
    terms_hash=bytes.fromhex(TERMS_HASH[2:]),
)

# Where #7's resource_id resolves on the lab (the controller's job, not netctl's).
RESOLVED_PATH = ResolvedPath(device="srl1", ingress_if="ethernet-1/1", egress_if="ethernet-1/2")

DECISION_ACCEPT = DecisionOutput(accept=True, reason="meets need; price within budget")
