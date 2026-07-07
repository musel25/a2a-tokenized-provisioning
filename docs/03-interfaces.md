# 03 — Interfaces: the published language (v0)

> **Status:** draft v0 — sketched thin, not frozen. These schemas are the *only* things two
> packages may share. Any change here = bump the `v` field + grep every consumer.
> Owner: `interfaces/`. Consumers: all packages.

The sections follow the lifecycle: discovery (A2A) → settlement (chain) → activation
(controller API) → enforcement ports (chain-read, network). §7 lists the open flip-points
deliberately carried in v0.

---

## 0. Conventions

- Cross-boundary payloads are **JSON**, except on-chain data, which is **ABI-encoded**.
- Addresses: `0x`-prefixed, checksummed hex. Token amounts: **decimal strings** in JSON
  (wei-style, 18 decimals), never floats.
- Times: **unix seconds, UTC, uint64**. The canonical clock for all validity decisions is
  **chain time** (`block.timestamp`) — see ADR-004. OS clocks only schedule wake-ups;
  every action re-verifies against chain time.
- Every JSON payload carries `"v": 0`.
- JSON field names are **snake_case**, with one deliberate exception: the `offer`
  sub-object (§1.4) is **camelCase**, because it mirrors the Solidity EIP-712 struct
  byte-for-byte (what is signed must equal what the contract verifies).
- Error codes are one shared enum (§3.4), used by the controller API and surfaced by tools.
- Payment: mock ERC-20 `TOK` (18 decimals) with a public `faucet()`. Single chain: Anvil,
  `chainId = 31337`.

---

## 1. A2A layer — discovery and offers

Providers run A2A servers (official `a2a-sdk`, version pinned in `agents/`). The consumer
is an A2A client. Domain payloads below travel as **structured data parts inside A2A
messages**; the SDK is only the envelope (ADR-002).

### 1.1 Discovery

- Each provider publishes an **agent card** at the A2A well-known path
  (`/.well-known/agent-card.json` per A2A ≥ 0.3 — verify against the pinned SDK version).
- v0 registry = a static file the consumer reads:

```json
// e2e/registry.json
{
  "v": 0,
  "providers": [
    { "name": "bandwidth-provider", "card_url": "http://localhost:9101/.well-known/agent-card.json" },
    { "name": "telemetry-provider", "card_url": "http://localhost:9102/.well-known/agent-card.json" }
  ]
}
```

### 1.2 Skills (per provider card)

| Provider | Skill id | Input | Output |
|---|---|---|---|
| bandwidth-provider | `quote_bandwidth` | `ServiceNeed` (kind=bandwidth) | `SignedOffer` |
| telemetry-provider | `quote_telemetry` | `ServiceNeed` (kind=telemetry) | `SignedOffer` |

A provider may answer a quote request with a **decline** (`{"v":0, "declined": true, "reason": "..."}`)
when admission control says it cannot commit. Declining is the provider's overselling guard.

### 1.3 `ServiceNeed`

`src`/`dst`/`target` are names from the **provider's** catalog (listed in its card
description). The consumer never sees topology.

```json
// bandwidth
{
  "v": 0,
  "kind": "bandwidth",
  "src": "hostA",
  "dst": "hostB",
  "capacity_bps": 50000000,
  "qos_class": 1,
  "window": { "start": 1757944800, "end": 1757952000 }
}
```

```json
// telemetry
{
  "v": 0,
  "kind": "telemetry",
  "target": "leafA",
  "sensor_paths": ["/interface[name=ethernet-1/1]/statistics"],
  "collector_endpoint": "10.0.0.50:57000",
  "sample_interval_s": 10,
  "window": { "start": 1757944800, "end": 1757952000 }
}
```

### 1.4 `SignedOffer`

The `offer` object mirrors the EIP-712 struct **field for field** (§2.1) — what is signed
is exactly what the contract verifies. `terms_doc` is the human-readable SLA; its canonical
form (JSON, keys sorted, no insignificant whitespace, UTF-8) hashes (keccak256) to
`termsHash`.

```json
{
  "v": 0,
  "offer": {
    "provider":     "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "consumer":     "0x0000000000000000000000000000000000000000",
    "serviceType":  0,
    "resourceId":   "0x0000000000000000000000000000000000000000000000000000000000000007",
    "params":       "0x..02faf080..01 — abi(capacityBps=50000000, qosClass=1), §4.2",
    "startTime":    1757944800,
    "endTime":      1757952000,
    "paymentToken": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    "price":        "10000000000000000000",
    "validUntil":   1757946000,
    "salt":         "0x0000000000000000000000000000000000000000000000000000000000005a17",
    "termsHash":    "0x2222222222222222222222222222222222222222222222222222222222222222"
  },
  "signature": "0x...65bytes",
  "terms_doc": { "sla": { "latency_ms": 20, "loss_pct": 0.1 }, "notes": "best effort beyond rate" }
}
```

- These are the canonical fixture values (`a2a_interfaces.fixtures`): Bell `0x7099…79C8` is
  the provider, `0x5FbD…0aa3` the token, ticket #7's `resourceId` is `0x…0007`, price 10 TOK.
  Story and tests reuse them — change them in one place or not at all.
- `consumer = address(0)` ⇒ **open offer** (anyone may fulfill before `validUntil`). v0 default.
- `serviceType`: `0` = bandwidth, `1` = telemetry.
- Windows are **absolute** in v0 (flip-point §7).

---

## 2. Settlement — on-chain interface

### 2.1 EIP-712

- Domain: `{ name: "A2AProvisioning", version: "0", chainId: 31337, verifyingContract: <settlement addr> }`
- Typed struct `Offer` = the twelve fields of §1.4 `offer`, in that order.

### 2.2 Functions (external surface)

The record `entitlements(id)` returns — the Solidity twin of the Python `EntitlementView`
(§4.1), holding only the **enforceable** fields (the descriptive SLA lives off-chain behind
`termsHash`):

```solidity
struct Entitlement {
    address issuer;        // the provider who signed the offer (e.g. Bell)
    uint8   serviceType;   // 0 = bandwidth, 1 = telemetry
    bytes32 resourceId;    // opaque handle; the controller maps it to topology (ADR-005)
    bytes   params;        // abi-encoded per serviceType (§4.2)
    uint64  startTime;
    uint64  endTime;
    bool    revoked;
    bytes32 termsHash;     // keccak256 of the canonical terms_doc
}
// the entitlement id is the ERC-721 tokenId; the owner is the current holder (ownerOf).
```

```solidity
function fulfill(Offer calldata offer, bytes calldata signature) external returns (uint256 entitlementId);
// pulls offer.price of offer.paymentToken via transferFrom (consumer must approve() first),
// verifies signature against offer.provider, requires offerHash unused, mints entitlement,
// pays provider — all in this one transaction, or reverts entirely.

function revoke(uint256 entitlementId) external;        // issuer-only; sets flag, never burns
function entitlements(uint256 id) external view returns (Entitlement memory);
// NB: implemented as a public mapping, so the compiled auto-getter returns the eight
// fields FLATTENED (address,uint8,bytes32,bytes,uint64,uint64,bool,bytes32), not one
// tuple — load the real ABI from contracts/out/ (§2.4), never hand-code this signature.
function ownerOf(uint256 id) external view returns (address);   // ERC-721
function tokenURI(uint256 id) external view returns (string memory); // on-chain data: URI
```

### 2.3 Events

```solidity
event EntitlementMinted(uint256 indexed id, address indexed issuer, uint8 serviceType, address indexed consumer);
event OfferConsumed(bytes32 offerHash);
event Revoked(uint256 indexed id);
```

The controller subscribes to `Revoked` for mid-session teardown; everything else is read by
polling/view calls at decision time.

### 2.4 Deployment artifact (producer: `contracts/script/Deploy.s.sol` · consumers: chainmcp, e2e)

`just deploy-local` leaves `contracts/deployments/anvil.json` — how every Python package
finds the chain (machine-local, gitignored; regenerate at will):

```json
{
  "v": 0,
  "chainId": 31337,
  "MockTOK": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
  "A2ASettlement": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
}
```

The addresses are deterministic on a fresh Anvil (deployer + nonce; MockTOK deploys first,
which is what lets `fixtures.MOCK_TOK` be a constant). ABIs are *not* duplicated here —
readers load them from `contracts/out/` (regenerated by forge, never copy-pasted).

---

## 3. Activation API — consumer agent ↔ controller (HTTP/JSON)

Replay-safe binding of off-chain enforcement to on-chain ownership. The consumer's key
never leaves `chainmcp`; the controller only ever sees a signature.

### 3.1 Endpoints

```
POST /v0/challenge          { "entitlement_id": 7 }
  → 200 { "nonce": "0x...16B", "controller_id": "bw-ctrl-1", "expires_at": 1757945100 }

POST /v0/activate           { "entitlement_id": 7, "action": { "kind": "bandwidth" },
                              "proof": { "nonce": "0x...", "signature": "0x..." } }
  → 200 { "session_id": "ent7-a1", "state": "active", "expires_at": 1757952000 }
  → 4xx { "error": "E_..." }            // codes in §3.4

POST /v0/teardown           { "session_id": "ent7-a1" }      // idempotent
  → 200 { "state": "torn_down" }

GET  /v0/sessions/{id}
  → 200 { "session_id": "...", "entitlement_id": 7, "state": "active",
          "since": 1757944810, "expires_at": 1757952000 }
```

### 3.2 Proof construction (v0: EIP-191 personal_sign — flip-point §7)

Message string, signed by the entitlement's current owner:

```
a2a-activate|{controller_id}|{nonce}|{entitlement_id}|{expires_at}
```

Controller verifies: signature recovers to `ownerOf(entitlement_id)` **and** nonce is fresh
(single-use, controller-local store) **and** `expires_at` not passed (chain time).

### 3.3 Session states

`requested → authorized → active → torn_down`, with `failed` reachable from any state.
Auto-teardown triggers: chain time ≥ `endTime`; `Revoked(id)` observed.

### 3.4 Error codes (shared enum)

`E_UNKNOWN_ENTITLEMENT · E_NOT_OWNER · E_BAD_PROOF · E_NONCE_REUSED · E_NOT_STARTED ·
E_EXPIRED · E_REVOKED · E_SCOPE · E_CONFLICT · E_NETWORK`

`E_SCOPE` = requested action exceeds terms. `E_CONFLICT` = a conflicting active session
exists (controller-local metering).

---

## 4. Entitlement read port — controller domain ↔ chain adapter

The controller's pure core depends on this Python `Protocol`, never on web3 directly:

```python
class EntitlementReader(Protocol):
    def owner_of(self, entitlement_id: int) -> str: ...
    def get(self, entitlement_id: int) -> EntitlementView: ...
    def chain_time(self) -> int: ...                       # latest block.timestamp
    def watch_revoked(self, callback: Callable[[int], None]) -> None: ...
```

### 4.1 `EntitlementView`

```python
# Implemented as a frozen pydantic model (a2a_interfaces.models); the port-side
# shapes below are likewise frozen pydantic models, not stdlib dataclasses.
class EntitlementView(BaseModel):  # frozen
    id: int
    issuer: str
    service_type: int            # 0 | 1
    resource_id: bytes           # 32 bytes, opaque here
    params: BandwidthParams | TelemetryParams
    start_time: int
    end_time: int
    revoked: bool
    terms_hash: bytes
```

### 4.2 `params` ABI schemas (per `serviceType`)

| serviceType | ABI encoding | Python view |
|---|---|---|
| 0 bandwidth | `(uint64 capacityBps, uint8 qosClass)` | `BandwidthParams(capacity_bps, qos_class)` |
| 1 telemetry | `(string[] sensorPaths, string collectorEndpoint, uint32 sampleIntervalS)` | `TelemetryParams(sensor_paths, collector_endpoint, sample_interval_s)` |

---

## 5. Provisioning port — controller ↔ netctl

`netctl` is topology-agnostic "gNMI hands" (ADR-005). The **controller** resolves
`resource_id` to concrete targets via its `resource_map.yaml` and passes them in.

```python
class NetworkProvisioner(Protocol):
    def apply_bandwidth(self, session_id: str, path: ResolvedPath,
                        capacity_bps: int, qos_class: int) -> ApplyResult: ...
    def apply_telemetry(self, session_id: str, target: ResolvedNode,
                        sensor_paths: list[str], collector_endpoint: str,
                        sample_interval_s: int) -> ApplyResult: ...
    def teardown(self, session_id: str) -> ApplyResult: ...   # MUST be idempotent
    def health(self) -> bool: ...

class ResolvedPath(BaseModel):  # frozen
    device: str            # e.g. "srl1"
    ingress_if: str        # e.g. "ethernet-1/1"
    egress_if: str

class ResolvedNode(BaseModel):  # frozen
    device: str

class ApplyResult(BaseModel):  # frozen
    ok: bool
    detail: str = ""
```

```yaml
# controller/resource_map.yaml (example)
"0xabc...":               # resourceId hex
  kind: path
  device: srl1
  ingress_if: ethernet-1/1
  egress_if: ethernet-1/2
"0xdef...":
  kind: node
  device: srl1
```

The mock provisioner implements the same `Protocol` and records calls for test assertions.
An optional MCP wrapper over `netctl` exists for manual debugging only — it is **not** on
the agent path.

### 5.1 Telemetry delivery (ADR-007) — `TelemetrySample`

Producer: netctl's provider-side forwarder (it subscribes to the router over gNMI and
flips the direction). Consumer: whatever listens at the entitlement's
`collector_endpoint` — the e2e dummy collector, later the dashboard. Wire format: **one
JSON line per sample** over TCP.

```json
{
  "v": 0,
  "session_id": "ent7-a1",
  "path": "srl_nokia-interfaces:interface[name=ethernet-1/1]/statistics",
  "timestamp_ns": 1783394038730008273,
  "values": { "…/statistics": { "in-octets": "832824572", "out-octets": "8277852" } }
}
```

`timestamp_ns` is the router's own notification timestamp. `values` maps the update's
paths to reported values verbatim — for a container subscription the router answers
with one value holding the whole statistics dict (counters one level down).

---

## 6. MCP tool schemas — agents ↔ tools

Two MCP servers sit on the agent path. Key custody rule: **all private keys live in
`chainmcp`**; `ctrl-mcp` and the controller never hold or see a key.

### 6.1 `chainmcp` (per-agent instance, configured with that agent's key)

| Tool | Input | Output | Used by |
|---|---|---|---|
| `sign_offer` | `offer` (§1.4 fields) | `SignedOffer` | providers |
| `fulfill_offer` | `SignedOffer` | `{ tx_hash, entitlement_id }` (handles `approve` first) | consumer |
| `read_entitlement` | `{ entitlement_id }` | `EntitlementView` as JSON | any |
| `sign_activation_proof` | `{ entitlement_id, nonce, controller_id, expires_at }` | `{ signature, address }` | consumer |
| `faucet` | `{ address }` | `{ tx_hash }` (dev only) | any |

### 6.2 `ctrl-mcp` (thin wrapper over §3)

| Tool | Wraps |
|---|---|
| `get_challenge` | `POST /v0/challenge` |
| `submit_activation` | `POST /v0/activate` |
| `get_session` | `GET /v0/sessions/{id}` |

Activation is deliberately **three tool calls** in the consumer graph:
`get_challenge` → `sign_activation_proof` → `submit_activation`.

### 6.3 LLM decision schema (the only judgment slot)

The consumer's accept/reject decision is structured output, validated and retried in code:

```json
{ "accept": true, "reason": "meets need; price within budget" }
```

---

## 7. Open flip-points carried in v0 (defaults stated)

| Question | v0 default | Alternative |
|---|---|---|
| Offer audience | open (`consumer = 0x0`) | consumer-bound offers |
| Validity window | absolute timestamps in offer | window relative to purchase time |
| Owner proof | EIP-191 personal_sign string | full SIWE / EIP-4361 message |
| Activation scope | full grant (`action.kind` only) | partial scope (e.g. fewer Mbps) |
| `tokenURI` | on-chain `data:` URI | IPFS |
| Transferability | transferable ERC-721 | soulbound |

---

*Change protocol: edit → bump `v` → update `docs/03` → grep consumers → green CI.*
