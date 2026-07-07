"""chainmcp as an MCP server (M5.4): the agent's key, exposed as tools — never leaked.

This is the custody rule (rule 2) made concrete: each agent runs ITS OWN chainmcp
instance, constructed with ITS key, and the graph reaches the chain only through these
tools. The key stays inside the process; the agent sees tool results (tx hashes,
entitlement ids, signed offers), never the key.

Built on FastMCP. The tool functions wrap an already-constructed `ChainClient`, so the
same object M1.5 tested is what answers here — the MCP layer is pure transport.

`build_chain_mcp(client)` returns a FastMCP server; `chain_tools(client)` returns the
same operations as plain callables (what tests and the in-process graph use, without a
stdio round-trip).
"""

from __future__ import annotations

from a2a_interfaces import Offer, SignedOffer

from .client import ChainClient


def chain_tools(client: ChainClient) -> dict:
    """The five §6.1 operations as plain callables over one agent's ChainClient.

    Kept separate from the FastMCP wrapper so the graphs can use them in-process (no
    stdio) and tests can call them directly — the MCP server is a thin shell over these.
    """

    def sign_offer(offer: dict) -> dict:
        signed = client.sign_offer(Offer.model_validate(offer))
        return signed.model_dump(mode="json")

    def fulfill_offer(signed_offer: dict) -> dict:
        tx_hash, entitlement_id = client.approve_and_fulfill(
            SignedOffer.model_validate(signed_offer)
        )
        return {"tx_hash": tx_hash, "entitlement_id": entitlement_id}

    def read_entitlement(entitlement_id: int) -> dict:
        return client.get(entitlement_id).model_dump(mode="json")

    def sign_activation_proof(
        entitlement_id: int, nonce: str, controller_id: str, expires_at: int
    ) -> dict:
        signature, address = client.sign_activation_proof(
            entitlement_id, nonce, controller_id, expires_at
        )
        return {"signature": signature, "address": address}

    def faucet(amount: int, to: str | None = None) -> dict:
        return {"tx_hash": client.faucet(amount, to)}

    return {
        "sign_offer": sign_offer,
        "fulfill_offer": fulfill_offer,
        "read_entitlement": read_entitlement,
        "sign_activation_proof": sign_activation_proof,
        "faucet": faucet,
    }


def build_chain_mcp(client: ChainClient, name: str = "chainmcp"):
    """A FastMCP server exposing this agent's chain operations (docs/03 §6.1)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)
    tools = chain_tools(client)

    @server.tool()
    def sign_offer(offer: dict) -> dict:
        """Sign a provider offer (EIP-712). Provider tool."""
        return tools["sign_offer"](offer)

    @server.tool()
    def fulfill_offer(signed_offer: dict) -> dict:
        """approve + fulfill a signed offer; returns {tx_hash, entitlement_id}. Consumer tool."""
        return tools["fulfill_offer"](signed_offer)

    @server.tool()
    def read_entitlement(entitlement_id: int) -> dict:
        """Read a minted entitlement as an EntitlementView. Any agent."""
        return tools["read_entitlement"](entitlement_id)

    @server.tool()
    def sign_activation_proof(
        entitlement_id: int, nonce: str, controller_id: str, expires_at: int
    ) -> dict:
        """EIP-191 proof of ownership for the controller. Consumer tool."""
        return tools["sign_activation_proof"](entitlement_id, nonce, controller_id, expires_at)

    @server.tool()
    def faucet(amount: int, to: str | None = None) -> dict:
        """Mint dev TOK (lab only). Any agent."""
        return tools["faucet"](amount, to)

    return server
