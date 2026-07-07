"""One disposable Anvil for the whole test session; per-test isolation by snapshot.

Skips (never fails) when anvil or the forge artifacts are missing — CI installs
Foundry and builds contracts before pytest, so there the tests really run.
"""

from __future__ import annotations

import pytest

from a2a_interfaces.fixtures import WINDOW
from chainmcp import ChainClient
from chainmcp.testing import ANVIL_KEYS, launch_anvil

# Same story moment the mock skeleton uses: ~13:32, before Ada's window opens,
# so the canonical offer (validUntil 14:20) is fulfillable.
STORY_TIME = WINDOW.start - 1680


@pytest.fixture(scope="session")
def anvil():
    chain = launch_anvil(timestamp=STORY_TIME)
    yield chain
    chain.stop()


@pytest.fixture()
def ada(anvil):
    client = ChainClient(
        anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment, poll_interval=0.2
    )
    yield client
    client.close()


@pytest.fixture()
def bell(anvil):
    client = ChainClient(
        anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment, poll_interval=0.2
    )
    yield client
    client.close()


@pytest.fixture(autouse=True)
def _snapshot(request):
    """Rewind chain state (and warped time) after each chain test — cheap isolation.

    Deliberately does NOT depend on `anvil` itself: pure signing tests must not
    boot a chain just because this fixture is autouse.
    """
    if "anvil" not in request.fixturenames:
        yield
        return
    from web3 import Web3

    anvil = request.getfixturevalue("anvil")
    w3 = Web3(Web3.HTTPProvider(anvil.rpc_url))
    snap = w3.provider.make_request("evm_snapshot", [])["result"]
    yield
    w3.provider.make_request("evm_revert", [snap])
