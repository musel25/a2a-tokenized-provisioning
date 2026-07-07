"""Profile selection: SKELETON_PROFILE decides what reality the lifecycle runs on.

  mock       (default) the M0.3 cardboard props — what CI runs forever
  chain      skeleton v1: live Anvil + real contracts + ChainClients

`chain` needs anvil on PATH and forge-built artifacts; if you ask for it without
them, that's an error, not a skip — a profile you requested silently degrading to
mock would be a lie.
"""

from __future__ import annotations

import os

import pytest

from e2e.skeleton.worlds import STORY_TIME, ChainWorld, MockWorld, seed_chain

PROFILE = os.environ.get("SKELETON_PROFILE", "mock")


@pytest.fixture(scope="session")
def _anvil_session():
    from chainmcp.testing import anvil_available, artifacts_available, launch_anvil

    if not (anvil_available() and artifacts_available()):
        raise RuntimeError(
            "SKELETON_PROFILE=chain needs anvil on PATH and forge-built artifacts "
            "(cd contracts && forge build)"
        )
    chain = launch_anvil(timestamp=STORY_TIME)
    try:
        seed_chain(chain)  # six pre-sales + funding, once — every snapshot starts from here
    except BaseException:
        chain.stop()  # a failed seeding must not orphan the anvil it seeded
        raise
    yield chain
    chain.stop()


@pytest.fixture()
def world(request):
    if PROFILE == "mock":
        yield MockWorld()
        return
    if PROFILE != "chain":
        raise RuntimeError(f"unknown SKELETON_PROFILE={PROFILE!r} (mock | chain)")

    from web3 import Web3

    anvil = request.getfixturevalue("_anvil_session")
    w3 = Web3(Web3.HTTPProvider(anvil.rpc_url))
    snapshot = w3.provider.make_request("evm_snapshot", [])["result"]
    chain_world = ChainWorld(anvil)
    yield chain_world
    chain_world.close()
    w3.provider.make_request("evm_revert", [snapshot])
