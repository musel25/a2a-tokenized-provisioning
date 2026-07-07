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

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from a2a_interfaces import Decline, ServiceNeed, SignedOffer
from a2a_interfaces.models import BandwidthNeed, TelemetryNeed

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
