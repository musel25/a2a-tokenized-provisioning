"""Challenge–response auth (docs/03 §3.2, docs/05 §4): prove you hold the key that
owns the ticket, RIGHT NOW, without ever showing the controller a key.

The dance: controller issues a single-use nonce with a chain-time expiry; the owner
signs `a2a-activate|{controller_id}|{nonce}|{entitlement_id}|{expires_at}` with plain
EIP-191 personal_sign; the controller recovers the address from the signature and
compares it with `ownerOf(id)`. Replay dies on the burned nonce, theft dies on the
recover, staleness dies on chain time (ADR-004 — the expiry is judged against the
chain, never the wall clock).

Crypto here is verification only (eth_account.recover) — the controller never signs
(rule 2). This module is not domain.py: it may use crypto, but still no chain, no
network, no clock of its own; every fact comes in as an argument.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from eth_account import Account
from eth_account.messages import encode_defunct

from a2a_interfaces import ErrorCode

# One template, agreed in docs/03 §3.2. chainmcp builds the same string on the signing
# side; the two implementations are pinned against each other in e2e (cross-package
# parity — neither may import the other, both answer to the doc).
PROOF_TEMPLATE = "a2a-activate|{controller_id}|{nonce}|{entitlement_id}|{expires_at}"

NONCE_TTL_S = 300  # a challenge is good for five minutes of chain time


def proof_message(controller_id: str, nonce: str, entitlement_id: int, expires_at: int) -> str:
    return PROOF_TEMPLATE.format(
        controller_id=controller_id,
        nonce=nonce,
        entitlement_id=entitlement_id,
        expires_at=expires_at,
    )


@dataclass(frozen=True)
class Challenge:
    """What POST /v0/challenge returns (docs/03 §3.1)."""

    nonce: str
    controller_id: str
    expires_at: int  # chain time


class AuthStore:
    """The controller-local nonce ledger: issue single-use challenges, verify proofs.

    Purely in-memory (a restart voids outstanding challenges — the consumer just asks
    again; nothing durable is lost). Distinguishes reuse from staleness so the error
    codes teach the caller the right lesson: E_NONCE_REUSED means "ask for a fresh
    challenge", E_BAD_PROOF means "your proof itself is wrong".
    """

    def __init__(self, controller_id: str) -> None:
        self.controller_id = controller_id
        self._open: dict[str, tuple[int, int]] = {}  # nonce → (entitlement_id, expires_at)

    def issue(self, entitlement_id: int, now: int) -> Challenge:
        nonce = "0x" + secrets.token_hex(16)  # 16 random bytes, docs/03 §3.1's "0x…16B"
        expires_at = now + NONCE_TTL_S
        self._open[nonce] = (entitlement_id, expires_at)
        return Challenge(nonce=nonce, controller_id=self.controller_id, expires_at=expires_at)

    def verify(
        self,
        entitlement_id: int,
        nonce: str,
        signature: str,
        owner: str,
        now: int,
    ) -> ErrorCode | None:
        """None if the proof binds (owner, nonce, this controller, in time); else the
        first failing ErrorCode. The nonce burns on ANY verification attempt — a
        failed proof cannot be retried against the same challenge (no oracle)."""
        issued = self._open.pop(nonce, None)
        if issued is None:
            return ErrorCode.E_NONCE_REUSED  # unknown and reused look identical here, by design
        issued_for, expires_at = issued
        if issued_for != entitlement_id:
            return ErrorCode.E_BAD_PROOF  # a nonce is bound to ONE ticket
        if now > expires_at:
            return ErrorCode.E_BAD_PROOF  # stale challenge, judged on chain time
        message = proof_message(self.controller_id, nonce, entitlement_id, expires_at)
        try:
            signer = Account.recover_message(encode_defunct(text=message), signature=signature)
        except Exception:  # noqa: BLE001 — malformed bytes are just a bad proof
            return ErrorCode.E_BAD_PROOF
        if signer != owner:
            return ErrorCode.E_NOT_OWNER
        return None
