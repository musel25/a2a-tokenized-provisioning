"""A2A adapter — the ONLY file in `agents` that imports the a2a SDK (ADR-002).

The SDK is the envelope, never the letter: our domain payloads (`ServiceNeed`,
`SignedOffer`, `Decline`) travel as **structured JSON data parts inside A2A messages**,
and this module is the single seam that packs/unpacks them and builds the agent cards.
Everything else in `agents` speaks pydantic; confining the SDK here means a version bump
touches one file (the M5.5 version pin: a2a-sdk 0.3.26 — the JSON-card line matching
docs/03 §1.1, NOT the protobuf 1.x rewrite).

The integrity guarantee this layer inherits for free: a `SignedOffer` carries its own
EIP-712 signature, so tampering a field anywhere in transit is caught downstream by the
contract's `fulfill` (`BadSignature`, M1.3) — the wire needs no trust of its own.
"""

from __future__ import annotations

import json
from time import perf_counter

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from a2a_interfaces import Decline, ServiceNeed, SignedOffer
from a2a_interfaces.models import BandwidthNeed, TelemetryNeed

from .provider_graph import ProviderState

_JSON = ["application/json"]


def provider_card(name: str, url: str, service: str) -> AgentCard:
    """A bandwidth- or telemetry-provider's agent card (docs/03 §1.1/§1.2). Served at
    the well-known path so the consumer can discover the provider's one quote skill."""
    skill = AgentSkill(
        id=f"quote_{service}",
        name=f"Quote {service.title()}",
        description=f"Return a signed offer (or decline) for a {service} ServiceNeed.",
        tags=[service, "quote"],
    )
    return AgentCard(
        name=name,
        description=f"{service} provider — quotes and signs offers (chainmcp holds the key).",
        url=url,
        version="0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=_JSON,
        default_output_modes=_JSON,
        skills=[skill],
    )


# --- pack/unpack: domain payload <-> the JSON string carried in an A2A data part -------
# (The A2A Message/Part envelope is assembled by the server/client SDK glue; what crosses
#  is this exact JSON, so tests can verify the wire content directly and cheaply.)


def encode_need(need: ServiceNeed) -> str:
    return need.model_dump_json(by_alias=True)


def decode_need(payload: str) -> ServiceNeed:
    data = json.loads(payload)
    variant = BandwidthNeed if data.get("kind") == "bandwidth" else TelemetryNeed
    return variant.model_validate(data)


def encode_offer_or_decline(result: SignedOffer | Decline) -> str:
    return result.model_dump_json(by_alias=True)


def decode_offer_or_decline(payload: str) -> SignedOffer | Decline:
    data = json.loads(payload)
    if data.get("declined"):
        return Decline.model_validate(data)
    return SignedOffer.model_validate(data)


def provider_cards() -> list[AgentCard]:
    """Both products' cards, one quote skill each (docs/03 §1.1) — what a consumer
    discovers before step 1. Discovery binds nothing: every downstream check binds to
    the addresses inside the signed offer, not to how the provider was found."""
    return [
        provider_card("bandwidth-provider", "http://localhost:9101/", "bandwidth"),
        provider_card("telemetry-provider", "http://localhost:9102/", "telemetry"),
    ]


def loopback_quote(provider_graph, need: ServiceNeed) -> tuple[SignedOffer | Decline, dict[str, float]]:
    """One quote exchange with no live server: the need and the answer cross the SAME
    JSON codec a served A2A data part would carry, and the provider graph runs for
    real in between. This is the evaluated configuration's A2A hop — schema-level by
    design (docs/09 boundary: no message envelope is assembled, no transport is
    exercised); a served deployment swaps this function for the SDK client/server pair.

    Returns the decoded answer plus per-node wall times ({"admit_s", "quote_s"}), so
    the harness can split admission arithmetic from the judgment slot."""
    wire_need = encode_need(need)
    timings: dict[str, float] = {}
    final: dict = {}
    t_prev = perf_counter()
    for chunk in provider_graph.stream(
        ProviderState(need=decode_need(wire_need)), stream_mode="updates"
    ):
        node, delta = next(iter(chunk.items()))
        now = perf_counter()
        timings[f"{node}_s"] = now - t_prev
        t_prev = now
        if delta is not None:
            final.update(delta if isinstance(delta, dict) else vars(delta))
    wire_answer = encode_offer_or_decline(final["result"])
    return decode_offer_or_decline(wire_answer), timings
