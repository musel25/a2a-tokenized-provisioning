"""Cross-boundary shapes — the published language (docs/03-interfaces.md §1-§6).

Every shape here is a *frozen* pydantic model: validated at the border, immutable
after construction, and JSON round-trippable. This package holds shapes only — no
signing, no keccak, no ABI codec, no I/O (those live in chainmcp / netctl). See
CLAUDE.md rules 1-4.

Field naming follows docs/03 exactly:
- A2A domain payloads (ServiceNeed) use snake_case on the wire.
- The `Offer` struct mirrors the Solidity EIP-712 struct, so it serializes to
  camelCase (`serviceType`, `resourceId`, ...) via an alias generator; in Python
  you still use snake_case attributes.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

V = 0  # protocol version; every cross-boundary payload carries "v" (docs/03 §0)

# --- constrained scalar types (docs/03 §0 conventions) ---------------------

# unsigned integers, by bit width (chain uses uint8/uint32/uint64)
Uint8 = Annotated[int, Field(ge=0, le=2**8 - 1)]
Uint32 = Annotated[int, Field(ge=0, le=2**32 - 1)]
Uint64 = Annotated[int, Field(ge=0, le=2**64 - 1)]

# 0x-prefixed hex. We validate the *pattern* only; EIP-55 checksum verification
# needs keccak and therefore belongs to chainmcp, not here.
Address = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
Bytes32Hex = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{64}$")]
Signature = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{130}$")]  # 65 bytes
HexData = Annotated[str, StringConstraints(pattern=r"^0x([0-9a-fA-F]{2})*$")]  # ABI blob

# Token amounts are decimal strings (wei-style, 18 decimals) — never floats (§0).
DecimalString = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]


class _Frozen(BaseModel):
    """Immutable, strict base: reject unknown fields, forbid mutation."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --- enums (§3.3, §3.4) ----------------------------------------------------


class SessionState(str, Enum):
    """Controller session lifecycle (docs/03 §3.3)."""

    REQUESTED = "requested"
    AUTHORIZED = "authorized"
    ACTIVE = "active"
    TORN_DOWN = "torn_down"
    FAILED = "failed"


class ErrorCode(str, Enum):
    """Shared error enum surfaced by the controller API and tools (docs/03 §3.4)."""

    E_UNKNOWN_ENTITLEMENT = "E_UNKNOWN_ENTITLEMENT"
    E_NOT_OWNER = "E_NOT_OWNER"
    E_BAD_PROOF = "E_BAD_PROOF"
    E_NONCE_REUSED = "E_NONCE_REUSED"
    E_NOT_STARTED = "E_NOT_STARTED"
    E_EXPIRED = "E_EXPIRED"
    E_REVOKED = "E_REVOKED"
    E_SCOPE = "E_SCOPE"
    E_CONFLICT = "E_CONFLICT"
    E_NETWORK = "E_NETWORK"


# --- service params (§4.2) -------------------------------------------------


class BandwidthParams(_Frozen):
    """serviceType 0 — decoded view of the on-chain `params` blob."""

    capacity_bps: Uint64
    qos_class: Uint8


class TelemetryParams(_Frozen):
    """serviceType 1 — decoded view of the on-chain `params` blob."""

    sensor_paths: list[str]
    collector_endpoint: str
    sample_interval_s: Uint32


# --- A2A layer: ServiceNeed (§1.3), discriminated on `kind` -----------------


class TimeWindow(_Frozen):
    """Absolute validity window, unix seconds UTC (§0, §1.3)."""

    start: Uint64
    end: Uint64


class BandwidthNeed(_Frozen):
    """A consumer's request for guaranteed bandwidth (docs/03 §1.3)."""

    v: Literal[0] = 0
    kind: Literal["bandwidth"] = "bandwidth"
    src: str  # provider-catalog name (from its card), not a device/topology name (§1.3)
    dst: str
    capacity_bps: Uint64
    qos_class: Uint8
    window: TimeWindow


class TelemetryNeed(_Frozen):
    """A consumer's request for a telemetry stream to its collector (docs/03 §1.3)."""

    v: Literal[0] = 0
    kind: Literal["telemetry"] = "telemetry"
    target: str  # provider-catalog name (from its card), not a device/topology name (§1.3)
    sensor_paths: list[str]
    collector_endpoint: str
    sample_interval_s: Uint32
    window: TimeWindow


# Discriminated union — pydantic selects the variant by the `kind` literal.
ServiceNeed = Annotated[Union[BandwidthNeed, TelemetryNeed], Field(discriminator="kind")]


# --- Settlement: the signed Offer (§1.4 / §2.1) ----------------------------


class Offer(BaseModel):
    """The twelve fields of the EIP-712 `Offer` struct, in order (docs/03 §1.4).

    Serializes to camelCase to mirror the Solidity struct byte-for-byte: the signed
    payload must equal what the contract verifies, field for field.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    provider: Address
    consumer: Address  # address(0) => open offer (anyone may fulfill)
    service_type: Uint8  # 0 = bandwidth, 1 = telemetry
    resource_id: Bytes32Hex
    params: HexData  # ABI-encoded per serviceType (§4.2)
    start_time: Uint64
    end_time: Uint64
    payment_token: Address
    price: DecimalString
    valid_until: Uint64
    salt: Bytes32Hex
    terms_hash: Bytes32Hex


class SignedOffer(_Frozen):
    """An Offer plus its signature and the human-readable SLA (docs/03 §1.4)."""

    v: Literal[0] = 0
    offer: Offer
    signature: Signature
    terms_doc: dict[str, Any]


# --- Activation API payloads (§3.1) — consumer agent ↔ controller -----------
# The §3.1 examples elide the "v" field for brevity; the §0 convention (every JSON
# payload carries v) wins here, as a validated default.


class ChallengeRequest(_Frozen):
    v: Literal[0] = 0
    entitlement_id: int


class ChallengeResponse(_Frozen):
    v: Literal[0] = 0
    nonce: str
    controller_id: str
    expires_at: Uint64  # chain time


class ActionPayload(_Frozen):
    kind: Literal["bandwidth", "telemetry"]


class ProofPayload(_Frozen):
    nonce: str
    signature: Signature


class ActivateRequest(_Frozen):
    v: Literal[0] = 0
    entitlement_id: int
    action: ActionPayload
    proof: ProofPayload


class SessionInfo(_Frozen):
    """Returned by activate and GET /v0/sessions/{id} (§3.1/§3.3)."""

    v: Literal[0] = 0
    session_id: str
    entitlement_id: int
    state: SessionState
    since: Uint64
    expires_at: Uint64


class TeardownRequest(_Frozen):
    v: Literal[0] = 0
    session_id: str


# --- LLM decision (§6.3): the only judgment slot ---------------------------


class DecisionOutput(_Frozen):
    """Consumer accept/reject — structured output, validated and retried in code."""

    accept: bool
    reason: str


# --- Entitlement read port view (§4.1) -------------------------------------


class EntitlementView(_Frozen):
    """Decoded, read-only view of one on-chain entitlement (docs/03 §4.1).

    `resource_id` / `terms_hash` are raw 32-byte values; they round-trip through
    JSON as hex strings.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        ser_json_bytes="hex",
        val_json_bytes="hex",
    )

    id: int
    issuer: Address
    service_type: Uint8  # 0 = bandwidth, 1 = telemetry
    resource_id: bytes  # 32 bytes, opaque here
    params: Union[BandwidthParams, TelemetryParams]
    start_time: Uint64
    end_time: Uint64
    revoked: bool
    terms_hash: bytes


# --- Provisioning port shapes (§5) -----------------------------------------


class TelemetrySample(_Frozen):
    """One streamed sensor sample, forwarder → consumer collector (§5.1, ADR-007).

    Producer: netctl's telemetry forwarder. Consumer: whatever listens at the
    entitlement's `collector_endpoint` (the e2e dummy collector, later the dashboard).
    One JSON line per sample on the wire.
    """

    v: Literal[0] = 0
    session_id: str
    path: str  # the subscribed sensor path this sample answers
    timestamp_ns: int  # the router's notification timestamp (unix ns)
    values: dict[str, Any]  # leaf path → value, as the router reported them


class ResolvedPath(_Frozen):
    """Concrete device + interfaces the controller hands to netctl (§5)."""

    device: str  # e.g. "srl1"
    ingress_if: str  # e.g. "ethernet-1/1"
    egress_if: str


class ResolvedNode(_Frozen):
    device: str


class ApplyResult(_Frozen):
    ok: bool
    detail: str = ""
