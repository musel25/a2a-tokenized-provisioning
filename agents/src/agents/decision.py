"""The consumer's accept/reject — ONE of the two LLM judgment slots (rule 1).

`decide(need, offer)` is where an LLM earns its place: it weighs a signed offer against
what the consumer needs and a budget, and returns a validated `DecisionOutput`. The
schema guard means the caller always gets `{accept: bool, reason: str}` or a safe
default — the graph never branches on a hallucinated shape.
"""

from __future__ import annotations

from a2a_interfaces import DecisionOutput, ServiceNeed, SignedOffer

from .llm import LLMClient, StructuredError

_SYSTEM = (
    "You are a procurement agent buying network services for your principal. You are given "
    "a NEED and a signed OFFER. Accept only if the offer meets the need (right service, "
    "enough capacity, correct window) AND the price is within budget. Be decisive."
)


def decide(
    client: LLMClient,
    need: ServiceNeed,
    offer: SignedOffer,
    budget_tok: int,
) -> DecisionOutput:
    """Judge the offer. On a schema failure after retries, DECLINE safely (a procurement
    agent that can't read an offer must not accept it)."""
    price_tok = int(offer.offer.price) // 10**18
    user = (
        f"NEED: {need.model_dump_json()}\n"
        f"OFFER terms: {offer.offer.model_dump_json()}\n"
        f"Price: {price_tok} TOK.  Budget: {budget_tok} TOK.\n"
        "Decide accept or reject with a one-sentence reason."
    )
    try:
        return client.structured(_SYSTEM, user, DecisionOutput)
    except StructuredError:
        return DecisionOutput(accept=False, reason="could not obtain a valid decision; declining")
