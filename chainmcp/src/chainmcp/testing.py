"""Test/lab plumbing: launch a throwaway Anvil and deploy the settlement onto it.

Shared by chainmcp's own tests, the e2e `chain` profile, and the exploration
notebooks — one way to stand up a chain, everywhere. Not imported by production
code paths.

Requires `anvil` on PATH and built artifacts in `contracts/out/` (run `forge build`
once); tests that can't find them should skip, not fail (CI installs Foundry).
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from eth_account import Account
from web3 import Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder

from .artifacts import find_contracts_dir, load_abi, load_bytecode

# Anvil's well-known dev accounts — public constants, not secrets, but still keys:
# they live HERE and nowhere else (rule 2 applies to the pattern, not just to real
# secrets — a key literal in e2e today becomes one in agents/ tomorrow). #0/#1/#2 are
# the story's cast (Ada, Bell, Carol); #3 "mallory" is the TOK-broke buyer of the
# underfunded deny paths.
ANVIL_KEYS = {
    "ada": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "bell": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "carol": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "mallory": "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
}


def anvil_available() -> bool:
    return shutil.which("anvil") is not None


def artifacts_available(contracts_dir: Path | None = None) -> bool:
    try:
        load_abi("A2ASettlement", contracts_dir)
        return True
    except FileNotFoundError:
        return False


@dataclass
class AnvilChain:
    """A running disposable chain + its deployment, ready for ChainClients."""

    process: subprocess.Popen
    rpc_url: str
    deployment: dict  # docs/03 §2.4 shape

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=5)

    # Chain-time control belongs to tests/labs only — production never warps time.
    def increase_time(self, w3: Web3, seconds: int) -> None:
        w3.provider.make_request("evm_increaseTime", [seconds])
        w3.provider.make_request("evm_mine", [])


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def launch_anvil(timestamp: int, port: int | None = None) -> AnvilChain:
    """Start anvil pinned to `timestamp` (chain time is story time — ADR-004) and
    deploy MockTOK + A2ASettlement exactly like script/Deploy.s.sol: MockTOK first,
    from account #0, so the fixture address 0x5FbD…0aa3 holds."""
    port = port or _free_port()
    rpc_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        ["anvil", "--port", str(port), "--timestamp", str(timestamp), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    deadline = time.monotonic() + 10
    while True:
        try:
            w3.eth.chain_id
            break
        except Exception:
            if time.monotonic() > deadline:
                process.terminate()
                raise RuntimeError("anvil did not come up on " + rpc_url) from None
            time.sleep(0.05)

    try:
        deployer = Account.from_key(ANVIL_KEYS["ada"])
        w3.middleware_onion.inject(SignAndSendRawMiddlewareBuilder.build(deployer), layer=0)
        w3.eth.default_account = deployer.address
        contracts = find_contracts_dir()
        addresses = {}
        for name in ("MockTOK", "A2ASettlement"):  # order matters: deploy[0] = the token
            contract = w3.eth.contract(
                abi=load_abi(name, contracts), bytecode=load_bytecode(name, contracts)
            )
            tx_hash = contract.constructor().transact()
            addresses[name] = w3.eth.wait_for_transaction_receipt(tx_hash)["contractAddress"]
    except BaseException:
        # A deploy failure (stale artifacts, half-built out/) must not orphan the
        # silent anvil we just started — nobody else holds its handle yet.
        process.terminate()
        raise

    deployment = {"v": 0, "chainId": w3.eth.chain_id, **addresses}
    return AnvilChain(process=process, rpc_url=rpc_url, deployment=deployment)
