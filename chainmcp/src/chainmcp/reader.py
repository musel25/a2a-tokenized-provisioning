"""ChainReader — the keyless read side of the chain (the M1.5 deferral, paid at M4.5).

The controller must never hold signing power (rule 2's spirit): it verifies, it reads,
it never spends. `ChainReader` is `ChainClient` with the write half amputated — it
satisfies the `EntitlementReader` Protocol (owner_of / get / chain_time / watch_revoked)
and NOTHING else. No `Account`, no signing middleware, no `sign_*`, no `fulfill`.

It reuses `ChainClient`'s read + watch code by composition rather than inheritance, so
there is no path — not even an unused one — from a controller to a private key.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from web3 import Web3
from web3.exceptions import ContractLogicError

from a2a_interfaces import BandwidthParams, TelemetryParams

from .artifacts import error_selectors, find_contracts_dir, load_abi, load_deployment
from .client import ChainClient


class ChainReader:
    """Read-only EntitlementReader — construct with no key, ever."""

    def __init__(
        self,
        rpc_url: str,
        deployment: dict | None = None,
        contracts_dir: Path | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))  # no signing middleware injected
        contracts = contracts_dir or find_contracts_dir()
        deploy = deployment or load_deployment(contracts)
        settlement_abi = load_abi("A2ASettlement", contracts)
        self._settlement = self._w3.eth.contract(
            address=Web3.to_checksum_address(deploy["A2ASettlement"]), abi=settlement_abi
        )
        self._errors = error_selectors(settlement_abi)
        self._poll_interval = poll_interval
        import threading

        self._watch_callbacks: list[Callable[[int], None]] = []
        self._watcher: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_seen = 0
        self.last_watch_error: Exception | None = None

    # The read + watch methods ARE ChainClient's — same code, borrowed, no key in sight.
    owner_of = ChainClient.owner_of
    get = ChainClient.get
    chain_time = ChainClient.chain_time
    watch_revoked = ChainClient.watch_revoked
    _watch_loop = ChainClient._watch_loop
    close = ChainClient.close

    # get() needs these names on self; spell the decode helpers ChainClient's get uses.
    _BandwidthParams = BandwidthParams
    _TelemetryParams = TelemetryParams

    def _revert_name(self, err: ContractLogicError) -> str:
        return ChainClient._revert_name(self, err)

    def _as_chain_revert(self, err: ContractLogicError):
        return ChainClient._as_chain_revert(self, err)
