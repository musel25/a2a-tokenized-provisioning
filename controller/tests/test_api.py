"""M4.4 — the HTTP API over cardboard: httpx drives docs/03 §3 end to end.

The service runs on the M0.3 fakes (dependency injection is the whole point); only
the AuthStore and the keys are real, because auth IS this layer's judgment.
"""

from __future__ import annotations

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from a2a_interfaces.fixtures import BANDWIDTH_NEED, TICKET_ID, WINDOW
from e2e.skeleton.fakes import FakeChain, FakeClock
from e2e.skeleton.scripted_agents import ScriptedProvider
from netctl.mock import MockProvisioner

from controller.app import build_app
from controller.auth import AuthStore, proof_message
from controller.resource_map import load_resource_map
from controller.service import ControllerService

ADA_KEY = Account.create("api-tests-ada")


@pytest.fixture()
def world():
    clock = FakeClock(WINDOW.start - 1680)
    chain = FakeChain(clock, balances={ADA_KEY.address: 10**20}, next_id=TICKET_ID)
    chain.fulfill(ScriptedProvider().quote(BANDWIDTH_NEED), buyer=ADA_KEY.address)
    clock.advance(1800)  # 14:02 — inside the window
    net = MockProvisioner()
    service = ControllerService(chain, net, AuthStore("bw-ctrl-1"), load_resource_map())
    return clock, chain, net, service, TestClient(build_app(service))


def _activate(client, entitlement_id: int, key=ADA_KEY):
    challenge = client.post("/v0/challenge", json={"entitlement_id": entitlement_id}).json()
    message = proof_message(
        challenge["controller_id"], challenge["nonce"], entitlement_id, challenge["expires_at"]
    )
    signature = "0x" + key.sign_message(encode_defunct(text=message)).signature.hex()
    return client.post(
        "/v0/activate",
        json={
            "entitlement_id": entitlement_id,
            "action": {"kind": "bandwidth"},
            "proof": {"nonce": challenge["nonce"], "signature": signature},
        },
    )


def test_happy_path_over_http(world):
    clock, chain, net, service, client = world

    response = _activate(client, TICKET_ID)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "active"
    assert net.applied[body["session_id"]]["capacity_bps"] == 50_000_000

    fetched = client.get(f"/v0/sessions/{body['session_id']}").json()
    assert fetched["entitlement_id"] == TICKET_ID
    assert fetched["expires_at"] == WINDOW.end

    down = client.post("/v0/teardown", json={"session_id": body["session_id"]})
    assert down.json() == {"state": "torn_down"}
    assert client.post("/v0/teardown", json={"session_id": body["session_id"]}).json() == {
        "state": "torn_down"  # idempotent over HTTP too
    }


def test_unknown_entitlement_is_404(world):
    *_, client = world
    assert client.post("/v0/challenge", json={"entitlement_id": 99}).status_code == 404
    assert client.get("/v0/sessions/nope").status_code == 404


def test_replayed_nonce_is_401(world):
    *_, client = world
    challenge = client.post("/v0/challenge", json={"entitlement_id": TICKET_ID}).json()
    message = proof_message(
        challenge["controller_id"], challenge["nonce"], TICKET_ID, challenge["expires_at"]
    )
    signature = "0x" + ADA_KEY.sign_message(encode_defunct(text=message)).signature.hex()
    payload = {
        "entitlement_id": TICKET_ID,
        "action": {"kind": "bandwidth"},
        "proof": {"nonce": challenge["nonce"], "signature": signature},
    }
    assert client.post("/v0/activate", json=payload).status_code == 200
    second = client.post("/v0/activate", json=payload)
    assert second.status_code == 401
    assert second.json() == {"error": "E_NONCE_REUSED"}


def test_thiefs_proof_is_403_not_owner(world):
    *_, client = world
    response = _activate(client, TICKET_ID, key=Account.create("thief"))
    assert response.status_code == 403
    assert response.json() == {"error": "E_NOT_OWNER"}


def test_expired_ticket_is_403(world):
    clock, *_, client = world
    clock.advance(3 * 3600)  # chain time past 16:00
    response = _activate(client, TICKET_ID)
    assert (response.status_code, response.json()) == (403, {"error": "E_EXPIRED"})


def test_wrong_action_kind_is_403_scope(world):
    *_, client = world
    challenge = client.post("/v0/challenge", json={"entitlement_id": TICKET_ID}).json()
    message = proof_message(
        challenge["controller_id"], challenge["nonce"], TICKET_ID, challenge["expires_at"]
    )
    signature = "0x" + ADA_KEY.sign_message(encode_defunct(text=message)).signature.hex()
    response = client.post(
        "/v0/activate",
        json={
            "entitlement_id": TICKET_ID,
            "action": {"kind": "telemetry"},  # a telemetry action on a bandwidth ticket
            "proof": {"nonce": challenge["nonce"], "signature": signature},
        },
    )
    assert (response.status_code, response.json()) == (403, {"error": "E_SCOPE"})


def test_double_booking_is_403_conflict(world):
    *_, client = world
    assert _activate(client, TICKET_ID).status_code == 200
    response = _activate(client, TICKET_ID)
    assert (response.status_code, response.json()) == (403, {"error": "E_CONFLICT"})


def test_provisioner_failure_is_502_and_cleans_up(world):
    clock, chain, net, service, client = world

    class _Refusing(MockProvisioner):
        def apply_bandwidth(self, session_id, path, capacity_bps, qos_class):
            from a2a_interfaces import ApplyResult

            return ApplyResult(ok=False, detail="lab unreachable")

    refusing = _Refusing()
    service._net = refusing  # sabotage the hands, keep everything else
    response = _activate(client, TICKET_ID)
    assert (response.status_code, response.json()) == (502, {"error": "E_NETWORK"})
    assert refusing.torn_down  # the half-applied session was swept immediately


def test_tick_ends_sessions_at_chain_t1(world):
    clock, chain, net, service, client = world
    body = _activate(client, TICKET_ID).json()
    clock.advance(WINDOW.end - clock.now())  # jump to exactly 16:00
    assert service.tick() == [body["session_id"]]
    assert client.get(f"/v0/sessions/{body['session_id']}").json()["state"] == "torn_down"


def test_revocation_event_ends_the_session(world):
    clock, chain, net, service, client = world
    body = _activate(client, TICKET_ID).json()
    chain.revoke(TICKET_ID)  # FakeChain notifies synchronously...
    service.handle_revoked(TICKET_ID)  # ...and M4.5 wires this to watch_revoked
    assert client.get(f"/v0/sessions/{body['session_id']}").json()["state"] == "torn_down"
