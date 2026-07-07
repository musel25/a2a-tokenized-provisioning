"""M4.2 — auth: every way a proof can fail, plus the one way it binds."""

from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct

from a2a_interfaces import ErrorCode

from controller.auth import NONCE_TTL_S, AuthStore, proof_message

NOW = 1757944800  # 14:00, chain time
OWNER_KEY = Account.create("controller-auth-tests")  # throwaway; never a real identity
OWNER = OWNER_KEY.address


def _sign(store: AuthStore, challenge, entitlement_id: int, key=OWNER_KEY) -> str:
    message = proof_message(
        store.controller_id, challenge.nonce, entitlement_id, challenge.expires_at
    )
    return key.sign_message(encode_defunct(text=message)).signature.hex()


def test_happy_path_binds():
    store = AuthStore("bw-ctrl-1")
    challenge = store.issue(7, now=NOW)
    signature = _sign(store, challenge, 7)
    assert store.verify(7, challenge.nonce, signature, owner=OWNER, now=NOW + 5) is None


def test_replayed_proof_is_E_NONCE_REUSED():
    # The plan's headline test: the same valid proof, twice.
    store = AuthStore("bw-ctrl-1")
    challenge = store.issue(7, now=NOW)
    signature = _sign(store, challenge, 7)
    assert store.verify(7, challenge.nonce, signature, OWNER, NOW + 5) is None
    assert store.verify(7, challenge.nonce, signature, OWNER, NOW + 6) == ErrorCode.E_NONCE_REUSED


def test_never_issued_nonce_is_E_NONCE_REUSED():
    store = AuthStore("bw-ctrl-1")
    assert store.verify(7, "0x" + "ab" * 16, "0x00", OWNER, NOW) == ErrorCode.E_NONCE_REUSED


def test_stale_challenge_is_E_BAD_PROOF():
    store = AuthStore("bw-ctrl-1")
    challenge = store.issue(7, now=NOW)
    signature = _sign(store, challenge, 7)
    late = NOW + NONCE_TTL_S + 1  # chain time passed the challenge's shelf life
    assert store.verify(7, challenge.nonce, signature, OWNER, late) == ErrorCode.E_BAD_PROOF


def test_nonce_bound_to_its_ticket():
    # A challenge for #7 cannot activate #8, even with a valid signature.
    store = AuthStore("bw-ctrl-1")
    challenge = store.issue(7, now=NOW)
    signature = _sign(store, challenge, 8)
    assert store.verify(8, challenge.nonce, signature, OWNER, NOW) == ErrorCode.E_BAD_PROOF


def test_wrong_signer_is_E_NOT_OWNER():
    store = AuthStore("bw-ctrl-1")
    challenge = store.issue(7, now=NOW)
    thief = Account.create("someone-else")
    signature = _sign(store, challenge, 7, key=thief)
    assert store.verify(7, challenge.nonce, signature, OWNER, NOW) == ErrorCode.E_NOT_OWNER


def test_garbage_signature_is_E_BAD_PROOF():
    store = AuthStore("bw-ctrl-1")
    challenge = store.issue(7, now=NOW)
    assert store.verify(7, challenge.nonce, "0xdeadbeef", OWNER, NOW) == ErrorCode.E_BAD_PROOF


def test_failed_attempt_burns_the_nonce():
    # No oracle: a thief may not keep probing the same challenge.
    store = AuthStore("bw-ctrl-1")
    challenge = store.issue(7, now=NOW)
    thief = Account.create("still-someone-else")
    assert store.verify(7, challenge.nonce, _sign(store, challenge, 7, thief), OWNER, NOW) == (
        ErrorCode.E_NOT_OWNER
    )
    good = _sign(store, challenge, 7)
    assert store.verify(7, challenge.nonce, good, OWNER, NOW) == ErrorCode.E_NONCE_REUSED


def test_controller_id_is_inside_the_signature():
    # A proof minted for controller A must not open controller B's door.
    store_a, store_b = AuthStore("ctrl-A"), AuthStore("ctrl-B")
    challenge = store_a.issue(7, now=NOW)
    signature = _sign(store_a, challenge, 7)
    store_b._open[challenge.nonce] = (7, challenge.expires_at)  # smuggle the nonce over
    assert store_b.verify(7, challenge.nonce, signature, OWNER, NOW) == ErrorCode.E_NOT_OWNER