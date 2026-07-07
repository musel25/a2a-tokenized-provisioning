"""The MCP-server surface (M5.4): `build_chain_mcp` is the "MCP server" in chainmcp's name.

`chain_tools(client)` (the in-process dict the console + agents use) is covered elsewhere;
this asserts the FastMCP wrapper around it registers the five chain tools, so the package's
namesake capability is exercised, not just documented."""

from __future__ import annotations

import asyncio

import pytest

from chainmcp.mcp_server import build_chain_mcp
from chainmcp.testing import anvil_available, artifacts_available

pytestmark = pytest.mark.skipif(
    not (anvil_available() and artifacts_available()),
    reason="needs anvil on PATH and forge-built artifacts",
)


def test_build_chain_mcp_registers_the_chain_tools(bell):
    server = build_chain_mcp(bell)
    assert server.name == "chainmcp"
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert tools == {
        "sign_offer", "fulfill_offer", "read_entitlement",
        "sign_activation_proof", "faucet",
    }, tools
