"""M4.5 — skeleton v3, the showpiece: the REAL controller, wired to Anvil + srl1,
tears a live policer off the router when Bell revokes on-chain, mid-window.

This is the jury-gold moment as an automated test (docs/01 M4.5 / §G "never cut"):
a real ERC-721 revocation → the controller's watcher → gNMI delete → the policer
vanishes from the real SR Linux. Needs Anvil + the live lab; skips otherwise.
"""

from __future__ import annotations

import time

import pytest
from eth_account.messages import encode_defunct

from a2a_interfaces import SessionState
from a2a_interfaces.fixtures import CANONICAL_OFFER
from chainmcp import ChainClient
from chainmcp.testing import ANVIL_KEYS, anvil_available, artifacts_available, launch_anvil
from controller.auth import proof_message
from controller.wiring import build_runtime
from netctl import paths
from netctl.connect import GnmiTarget
from netctl.provisioner import GnmiProvisioner, _denamespace
from netctl.testing import lab_ipv4

from e2e.skeleton.worlds import STORY_TIME, seed_chain

pytestmark = pytest.mark.skipif(
    not (anvil_available() and artifacts_available() and lab_ipv4()),
    reason="skeleton v3 needs Anvil + forge artifacts + the live lab",
)


def _policer_on_router(provisioner, session_id: str) -> dict | None:
    client = provisioner._client("srl1")
    response = client.get(
        path=[paths.policer_template(f"a2a-{session_id}")], encoding="json_ietf", datatype="config"
    )
    for update in response["notification"][0].get("update") or []:
        policers = _denamespace(update["val"] or {}).get("policer", [])
        if policers:
            return {"peak_rate_kbps": policers[0]["peak-rate-kbps"]}
    return None


@pytest.fixture()
def stack():
    anvil = launch_anvil(timestamp=STORY_TIME)
    seed_chain(anvil)  # six pre-sales so Ada's ticket is #7
    provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=lab_ipv4(), tls_name="srl1")})
    runtime = build_runtime(
        anvil.rpc_url, provisioner, deployment=anvil.deployment, poll_interval=0.2
    )
    runtime.start_watchers(expiry_poll_s=0.5)
    ada = ChainClient(anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment)
    bell = ChainClient(anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment)
    ada.faucet(10**20)
    yield anvil, ada, bell, runtime, provisioner
    for closable in (runtime, ada, bell):
        closable.close()
    provisioner.teardown("ent7-a0")  # belt-and-braces sweep
    provisioner.close()
    anvil.stop()


def _activate_ticket_7(anvil, ada, bell, runtime) -> str:
    _, entitlement_id = ada.approve_and_fulfill(bell.sign_offer(CANONICAL_OFFER))
    assert entitlement_id == 7
    anvil.increase_time(ada._w3, 1800)  # 13:32 → 14:02, inside Ada's window
    challenge = runtime.service.challenge(7)
    message = proof_message(challenge.controller_id, challenge.nonce, 7, challenge.expires_at)
    signature = "0x" + ada._acct.sign_message(encode_defunct(text=message)).signature.hex()
    info = runtime.service.activate(7, "bandwidth", challenge.nonce, signature)
    assert info.state == SessionState.ACTIVE
    return info.session_id


def test_real_controller_provisions_ticket_7(stack):
    anvil, ada, bell, runtime, provisioner = stack
    session_id = _activate_ticket_7(anvil, ada, bell, runtime)
    policer = _policer_on_router(provisioner, session_id)
    assert policer == {"peak_rate_kbps": 50_000}, "the 50 Mbps policer is really on srl1"


def test_onchain_revoke_kills_the_live_session(stack):
    """THE showpiece: Bell revokes #7 on Anvil; the controller's watcher observes it
    and the policer disappears from the real router — no teardown call from the test."""
    anvil, ada, bell, runtime, provisioner = stack
    session_id = _activate_ticket_7(anvil, ada, bell, runtime)
    assert _policer_on_router(provisioner, session_id) is not None

    bell.revoke(7)  # on-chain, mid-window — the test does NOTHING else

    deadline = time.monotonic() + 10  # watcher polls at 0.2s
    while _policer_on_router(provisioner, session_id) is not None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert _policer_on_router(provisioner, session_id) is None, "revoke did not tear down"
    assert runtime.service.session(session_id).state == SessionState.TORN_DOWN


def test_expiry_timer_tears_down_at_t1(stack):
    """ADR-004 in code: warp chain time past endTime; the expiry timer (which re-reads
    chain time on every tick) ends the session with no external nudge."""
    anvil, ada, bell, runtime, provisioner = stack
    session_id = _activate_ticket_7(anvil, ada, bell, runtime)

    anvil.increase_time(ada._w3, 3 * 3600)  # jump past 16:00

    deadline = time.monotonic() + 10  # expiry timer polls at 0.5s
    while _policer_on_router(provisioner, session_id) is not None and time.monotonic() < deadline:
        time.sleep(0.3)
    assert _policer_on_router(provisioner, session_id) is None, "expiry did not tear down"
    assert runtime.service.session(session_id).state == SessionState.TORN_DOWN
