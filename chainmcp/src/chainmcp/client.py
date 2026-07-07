"""ChainClient — the first real adapter: the chain as one agent sees it.

Satisfies the `EntitlementReader` Protocol (docs/03 §4) on the read side, and carries
that agent's write operations (faucet, approve+fulfill, revoke, signing). One client =
one identity: the private key given at construction never leaves this object (rule 2 —
callers see addresses and signatures, never the key).

Read-side port parity with the skeleton's FakeChain is deliberate and pinned by tests:
unknown ids raise KeyError (the fake's dict behavior), because the Protocol's callers
were written against that. On-chain "unknown" means `ownerOf` reverts
(ERC721NonexistentToken) — never a zero-struct read (see EXPLORE-settlement.md §1).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError
from web3.middleware import SignAndSendRawMiddlewareBuilder

from a2a_interfaces import BandwidthParams, EntitlementView, Offer, SignedOffer, TelemetryParams

from .artifacts import error_selectors, find_contracts_dir, load_abi, load_deployment
from .signing import (
    activation_proof_message,
    eip712_domain,
    offer_digest,
    offer_to_message,
    OFFER_TYPES,
)


class ChainRevert(Exception):
    """A transaction or call reverted with a decoded custom error.

    `name` carries the Solidity error name ("OfferExpired", "NotIssuer",
    "ERC20InsufficientAllowance", …) so callers can branch without importing ABI
    machinery; e2e maps these names onto the skeleton's exception classes.
    """

    def __init__(self, name: str, data: str = "") -> None:
        super().__init__(name)
        self.name = name
        self.data = data


class ChainClient:
    """One agent's window onto the settlement chain (reader port + writes)."""

    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        deployment: dict | None = None,
        contracts_dir: Path | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        self._acct = Account.from_key(private_key)
        # After this, contract .transact() calls sign locally with our key and go out
        # as raw transactions — the key stays inside this process.
        self._w3.middleware_onion.inject(SignAndSendRawMiddlewareBuilder.build(self._acct), layer=0)
        self._w3.eth.default_account = self._acct.address

        contracts = contracts_dir or find_contracts_dir()
        deploy = deployment or load_deployment(contracts)
        settlement_abi = load_abi("A2ASettlement", contracts)
        tok_abi = load_abi("MockTOK", contracts)
        self._settlement = self._w3.eth.contract(
            address=Web3.to_checksum_address(deploy["A2ASettlement"]), abi=settlement_abi
        )
        self._tok = self._w3.eth.contract(
            address=Web3.to_checksum_address(deploy["MockTOK"]), abi=tok_abi
        )
        self._chain_id = deploy["chainId"]
        self._errors = error_selectors(settlement_abi, tok_abi)

        self._poll_interval = poll_interval
        self._watch_callbacks: list[Callable[[int], None]] = []
        self._watcher: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_seen = 0  # set synchronously by watch_revoked before the thread starts
        self.last_watch_error: Exception | None = None  # observability for swallowed errors

    @property
    def address(self) -> str:
        return self._acct.address

    # --- EntitlementReader (docs/03 §4) -------------------------------------

    def owner_of(self, entitlement_id: int) -> str:
        try:
            return self._settlement.functions.ownerOf(entitlement_id).call()
        except ContractLogicError as err:
            # Port parity: FakeChain's dict raises KeyError for unknown ids, and the
            # Protocol's callers rely on that; ERC721NonexistentToken IS "unknown id".
            if self._revert_name(err) == "ERC721NonexistentToken":
                raise KeyError(entitlement_id) from err
            raise self._as_chain_revert(err) from err

    def token_uri(self, entitlement_id: int) -> str:
        """The ERC-721 tokenURI: a self-contained data:application/json;base64 URI whose
        metadata (issuer, serviceType, window, revoked…) lives entirely on-chain (M1.2)."""
        return self._settlement.functions.tokenURI(entitlement_id).call()

    def get(self, entitlement_id: int) -> EntitlementView:
        self.owner_of(entitlement_id)  # existence gate — the struct read can't tell (M1.2)
        (
            issuer,
            service_type,
            resource_id,
            params_blob,
            start_time,
            end_time,
            revoked,
            terms_hash,
        ) = self._settlement.functions.entitlements(entitlement_id).call()
        if service_type == 0:
            capacity_bps, qos_class = self._w3.codec.decode(["uint64", "uint8"], params_blob)
            params = BandwidthParams(capacity_bps=capacity_bps, qos_class=qos_class)
        elif service_type == 1:
            sensor_paths, collector, interval = self._w3.codec.decode(
                ["string[]", "string", "uint32"], params_blob
            )
            params = TelemetryParams(
                sensor_paths=list(sensor_paths),
                collector_endpoint=collector,
                sample_interval_s=interval,
            )
        else:
            # The contract mints ANY signed serviceType (params are opaque to it), so an
            # unknown type must fail here as a named refusal, not as a raw eth-abi
            # decode crash inside whoever called get().
            raise ValueError(
                f"entitlement #{entitlement_id} has serviceType {service_type}; "
                "docs/03 §4.2 defines decoders for 0 (bandwidth) and 1 (telemetry) only"
            )
        return EntitlementView(
            id=entitlement_id,
            issuer=issuer,
            service_type=service_type,
            resource_id=resource_id,
            params=params,
            start_time=start_time,
            end_time=end_time,
            revoked=revoked,
            terms_hash=terms_hash,
        )

    def chain_time(self) -> int:
        """Latest block timestamp — the one clock that counts (ADR-004)."""
        return self._w3.eth.get_block("latest")["timestamp"]

    def watch_revoked(self, callback: Callable[[int], None]) -> None:
        """Deliver every Revoked(id) after this call to `callback`, from a polling thread.

        ~`poll_interval` seconds of latency; background-thread delivery means the
        callback must be thread-tolerant (the stub controller's teardown is).
        Delivery is AT-LEAST-ONCE: `_last_seen` only advances after a block's events
        were handed to every callback, so a crash mid-delivery re-delivers rather than
        skips — the right trade for teardown, which is idempotent (rule 8).
        """
        if self._stop.is_set():
            raise RuntimeError("client is closed; build a new ChainClient to watch again")
        self._watch_callbacks.append(callback)
        if self._watcher is None:
            # Baseline read HERE, synchronously: "after this call" is measured from the
            # registration, not from whenever the OS schedules the thread — an event
            # mined in that gap must not be skippable.
            self._last_seen = self._w3.eth.block_number
            self._watcher = threading.Thread(target=self._watch_loop, daemon=True)
            self._watcher.start()

    def _watch_loop(self) -> None:
        while not self._stop.wait(self._poll_interval):
            try:
                head = self._w3.eth.block_number
                if head <= self._last_seen:
                    continue
                events = self._settlement.events.Revoked().get_logs(
                    from_block=self._last_seen + 1, to_block=head
                )
            except Exception as err:  # noqa: BLE001 — transient RPC hiccup: retry next tick
                self.last_watch_error = err
                continue
            for event in events:
                for callback in self._watch_callbacks:
                    try:
                        callback(event["args"]["id"])
                    except Exception as err:  # noqa: BLE001 — one bad callback must not
                        self.last_watch_error = err  # starve the others or kill the loop
            self._last_seen = head

    def close(self) -> None:
        """Stop the watcher thread; idempotent. The client stays readable/writable but
        can no longer watch — watch_revoked after close raises rather than silently
        starting a thread whose stop flag is already set."""
        self._stop.set()
        if self._watcher is not None:
            self._watcher.join(timeout=self._poll_interval * 3)
            self._watcher = None

    # --- extra reads (not in the port; used by e2e worlds, tools, notebooks) --

    def tok_balance(self, address: str) -> int:
        return self._tok.functions.balanceOf(Web3.to_checksum_address(address)).call()

    def offer_consumed(self, offer: Offer) -> bool:
        return self._settlement.functions.consumed(self.offer_digest(offer)).call()

    def offer_digest(self, offer: Offer) -> bytes:
        """Python-computed EIP-712 digest (the cross-stack test proves it equals
        the contract's hashOffer)."""
        return offer_digest(offer, self._chain_id, self._settlement.address)

    # --- write side: this agent acts ----------------------------------------

    def faucet(self, amount: int, to: str | None = None) -> str:
        """Mint lab TOK (dev only). Defaults to topping up this agent itself."""
        recipient = Web3.to_checksum_address(to or self.address)
        return self._transact(self._tok.functions.faucet(recipient, amount))

    def sign_offer(self, offer: Offer, terms_doc: dict | None = None) -> SignedOffer:
        """Sign as the provider: the promise leaves here as 65 bytes, key stays."""
        signed = self._acct.sign_typed_data(
            domain_data=eip712_domain(self._chain_id, self._settlement.address),
            message_types=OFFER_TYPES,
            message_data=offer_to_message(offer),
        )
        return SignedOffer(
            offer=offer,
            signature="0x" + signed.signature.hex(),
            terms_doc=terms_doc or {},
        )

    def approve_and_fulfill(self, signed: SignedOffer) -> tuple[str, int]:
        """The purchase, as the buyer: allowance for exactly the price, then fulfill.

        Returns (tx_hash, entitlement_id). Raises ChainRevert("OfferExpired" /
        "WrongConsumer" / "OfferAlreadyUsed" / "BadSignature" / ERC20 errors) —
        the same names the contract (and, for the shared three, FakeChain) uses.
        """
        offer = signed.offer
        price = int(offer.price)
        # v0 has exactly one payment token; approving MockTOK for an offer priced in
        # some other token would burn allowance and still revert in fulfill.
        if offer.payment_token.lower() != self._tok.address.lower():
            raise ValueError(f"offer pays in {offer.payment_token}, client only knows MockTOK")
        self._transact(self._tok.functions.approve(self._settlement.address, price))
        try:
            receipt = self._transact_raw(
                self._settlement.functions.fulfill(
                    self._offer_tuple(offer), bytes.fromhex(signed.signature[2:])
                )
            )
        except ChainRevert:
            # The approve is its own mined transaction, so the contract's atomicity (I3)
            # cannot cover it: a refused fulfill would leave a standing allowance.
            # Withdraw it (best-effort) so a rejected purchase truly leaves no trace.
            try:
                self._transact(self._tok.functions.approve(self._settlement.address, 0))
            except ChainRevert:
                pass  # the original refusal is the story worth raising
            raise
        from web3.logs import DISCARD  # the receipt also holds Transfer logs; skip them

        minted = self._settlement.events.EntitlementMinted().process_receipt(
            receipt, errors=DISCARD
        )
        return receipt["transactionHash"].to_0x_hex(), minted[0]["args"]["id"]

    def revoke(self, entitlement_id: int) -> str:
        """Issuer-only kill switch; ChainRevert("NotIssuer") for anyone else."""
        return self._transact(self._settlement.functions.revoke(entitlement_id))

    def sign_activation_proof(
        self, entitlement_id: int, nonce: str, controller_id: str, expires_at: int
    ) -> tuple[str, str]:
        """EIP-191 personal_sign of the docs/03 §3.2 string → (signature, address)."""
        from eth_account.messages import encode_defunct

        message = activation_proof_message(controller_id, nonce, entitlement_id, expires_at)
        signed = self._acct.sign_message(encode_defunct(text=message))
        return "0x" + signed.signature.hex(), self.address

    # --- reverts → ChainRevert, Offer → calldata tuple (docs/03 §1.4 order) ---

    def _offer_tuple(self, offer: Offer) -> tuple:
        """Offer → the ABI tuple, in struct order (the contract's calldata shape)."""
        message = offer_to_message(offer)
        return tuple(message[field["name"]] for field in OFFER_TYPES["Offer"])

    def _transact(self, fn) -> str:
        return self._transact_raw(fn)["transactionHash"].to_0x_hex()

    def _transact_raw(self, fn):
        try:
            tx_hash = fn.transact()
        except ContractLogicError as err:
            raise self._as_chain_revert(err) from err
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] != 1:  # estimation passed but execution failed — rare
            raise ChainRevert("TransactionFailed", data=receipt["transactionHash"].to_0x_hex())
        return receipt

    def _revert_name(self, err: ContractLogicError) -> str:
        data = err.data if isinstance(err.data, str) else ""
        if data.startswith("0x") and len(data) >= 10:
            return self._errors.get(bytes.fromhex(data[2:10]), data[:10])
        return str(err)

    def _as_chain_revert(self, err: ContractLogicError) -> ChainRevert:
        data = err.data if isinstance(err.data, str) else ""
        return ChainRevert(self._revert_name(err), data=data)
