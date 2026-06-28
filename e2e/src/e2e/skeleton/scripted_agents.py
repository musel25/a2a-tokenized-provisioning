"""Scripted agents: the two LLM judgment slots, hardcoded for the skeleton.

The only judgment in the system is the provider's quote/decline and the consumer's
accept/reject (CLAUDE.md rule 1). In v0 both are canned — the provider always quotes
the canonical offer, the consumer always accepts — so the lifecycle is deterministic.
The *shapes* (SignedOffer, DecisionOutput) are real; only the decision is fake. Real
LLM agents replace these at M5.x.
"""

from __future__ import annotations

from a2a_interfaces import DecisionOutput, ServiceNeed, SignedOffer
from a2a_interfaces.fixtures import CANONICAL_SIGNED_OFFER, DECISION_ACCEPT


class ScriptedProvider:
    def quote(self, need: ServiceNeed) -> SignedOffer:
        """Bell's slot: return a signed offer (canned; real signing is chainmcp)."""
        return CANONICAL_SIGNED_OFFER


class ScriptedConsumer:
    def decide(self, need: ServiceNeed, offer: SignedOffer) -> DecisionOutput:
        """Ada's slot: accept/reject (canned accept; real judgment is an LLM at M5.x)."""
        return DECISION_ACCEPT
