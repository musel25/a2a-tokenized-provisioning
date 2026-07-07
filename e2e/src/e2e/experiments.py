"""The evaluation harness (docs/09): the numbers that turn the PoC into an evaluation.

Each experiment answers one question a skeptical examiner would ask, and each runs the
REAL stack — real Anvil, real controller, real gNMI against SR Linux, real (deployed)
LLM when `--mode llm` — never a simulation of it:

  latency      Where does the time go? N full lifecycles (negotiate → settle → authorize
               → actuate → revoke), phase-timed, both service types, det and llm modes.
               Also yields gas per tx (E3) and the revocation kill-switch lag (E2).
  expiry       How fast does chain-time expiry become device deconfiguration? (ADR-004)
  baseline     What does the same provisioning cost WITHOUT agents/chain/controller —
               one direct netctl call? The delta is the price of trustlessness. (E6)
  adversarial  Can it be cheated? Ten attacks, each attributed to the layer that
               rejected it (contract revert vs controller ErrorCode). (E4)
  llm          How reliable is the judgment layer? Schema-validity, retries, latency,
               tokens, and decision ACCURACY against ground truth. (E5)

Usage (lab up; `.env` sourced for llm mode):
    uv run python -m e2e.experiments --exp all --n 20
    uv run python -m e2e.experiments --exp latency --n 5 --mode det   # quick smoke

Results: one JSONL per experiment + summary.json under --out (default e2e/runs/eval/).
The notebook `e2e/notebooks/evaluation_explore.ipynb` and docs/09 read these files.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import eth_abi
from eth_account.messages import encode_defunct

from a2a_interfaces import Offer
from a2a_interfaces.fixtures import (
    BANDWIDTH_NEED,
    BELL,
    CANONICAL_OFFER,
    MOCK_TOK,
    RESOLVED_PATH,
    TELEMETRY_NEED,
    TELEMETRY_RESOURCE_ID,
    TERMS_HASH,
    WINDOW,
)
from chainmcp import ChainClient, ChainReader
from chainmcp.client import ChainRevert
from chainmcp.testing import ANVIL_KEYS, launch_anvil
from controller.auth import AuthStore, proof_message
from controller.resource_map import load_resource_map
from controller.service import ControllerService, Denied
from netctl.connect import GnmiTarget
from netctl.provisioner import GnmiProvisioner, _denamespace
from netctl.testing import lab_ipv4

STORY_TIME = WINDOW.start - 1680  # 13:32 — before the window, same as the console
WATCH_POLL_S = 0.5  # the revocation watcher's poll interval (reported with E2 results)
CAPACITY = 50_000_000
QOS = 1


# --- plumbing ----------------------------------------------------------------


class TimingProvisioner:
    """The real GnmiProvisioner with clocks on it — same Protocol, same behavior
    (rule 7: nothing differs at the port), so the controller can't tell. Lets the
    harness split `activate()` into predicate/translate vs the gNMI Set."""

    def __init__(self, inner: GnmiProvisioner) -> None:
        self.inner = inner
        self.last: dict[str, float] = {}

    def apply_bandwidth(self, *a, **k):
        t0 = perf_counter()
        result = self.inner.apply_bandwidth(*a, **k)
        self.last["gnmi_apply_s"] = perf_counter() - t0
        return result

    def apply_telemetry(self, *a, **k):
        t0 = perf_counter()
        result = self.inner.apply_telemetry(*a, **k)
        self.last["gnmi_apply_s"] = perf_counter() - t0
        return result

    def teardown(self, *a, **k):
        t0 = perf_counter()
        result = self.inner.teardown(*a, **k)
        self.last["gnmi_teardown_s"] = perf_counter() - t0
        return result

    def health(self):
        return self.inner.health()

    def close(self):
        return self.inner.close()


@dataclass
class Stack:
    """One disposable evaluation stack: chain + clients + controller + timed gNMI."""

    anvil: object
    ada: ChainClient
    bell: ChainClient
    mallory: ChainClient
    reader: ChainReader
    provisioner: TimingProvisioner
    service: ControllerService
    nonce: int = 1000
    _watching: bool = False

    @classmethod
    def up(cls, lab_ip: str) -> Stack:
        anvil = launch_anvil(timestamp=STORY_TIME)
        ada = ChainClient(anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment,
                          poll_interval=0.05)
        bell = ChainClient(anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment,
                           poll_interval=0.05)
        mallory = ChainClient(anvil.rpc_url, ANVIL_KEYS["mallory"],
                              deployment=anvil.deployment, poll_interval=0.05)
        reader = ChainReader(anvil.rpc_url, deployment=anvil.deployment,
                             poll_interval=WATCH_POLL_S)
        ada.faucet(10_000 * 10**18)
        provisioner = TimingProvisioner(
            GnmiProvisioner({"srl1": GnmiTarget(host=lab_ip, tls_name="srl1")})
        )
        service = ControllerService(reader, provisioner, AuthStore("bw-ctrl-1"),
                                    load_resource_map())
        return cls(anvil, ada, bell, mallory, reader, provisioner, service)

    def watch(self) -> None:
        """Arm the real revocation watcher (the production mechanism, not a shortcut)."""
        if not self._watching:
            self.reader.watch_revoked(self.service.handle_revoked)
            self._watching = True

    def warp_into_window(self) -> None:
        self.anvil.increase_time(self.ada._w3, WINDOW.start + 120 - self.reader.chain_time())

    def fresh_offer(self, service: str, price_tok: int = 10) -> Offer:
        self.nonce += 1
        if service == "bandwidth":
            return CANONICAL_OFFER.model_copy(update={
                "salt": "0x" + f"{0xEA000 + self.nonce:064x}",
                "price": str(price_tok * 10**18),
            })
        params = eth_abi.encode(
            ["string[]", "string", "uint32"],
            [TELEMETRY_NEED.sensor_paths, TELEMETRY_NEED.collector_endpoint,
             TELEMETRY_NEED.sample_interval_s],
        )
        return Offer(
            provider=BELL, consumer="0x" + "0" * 40, service_type=1,
            resource_id=TELEMETRY_RESOURCE_ID, params="0x" + params.hex(),
            start_time=WINDOW.start, end_time=WINDOW.end, payment_token=MOCK_TOK,
            price=str(price_tok * 10**18), valid_until=WINDOW.end,
            salt="0x" + f"{0xEB000 + self.nonce:064x}", terms_hash=TERMS_HASH,
        )

    def proof(self, challenge, eid: int, key: str = "ada") -> str:
        msg = proof_message(challenge.controller_id, challenge.nonce, eid,
                            challenge.expires_at)
        acct = {"ada": self.ada, "bell": self.bell, "mallory": self.mallory}[key]._acct
        return "0x" + acct.sign_message(encode_defunct(text=msg)).signature.hex()

    def down(self) -> None:
        try:
            self.reader.close()
        except Exception:  # noqa: BLE001
            pass
        for c in (self.ada, self.bell, self.mallory):
            c.close()
        self.provisioner.close()
        self.anvil.stop()


def _policer_names(prov: TimingProvisioner) -> set[str]:
    client = prov.inner._client("srl1")
    got = client.get(path=["/qos/policer-templates"], encoding="json_ietf",
                     datatype="config")
    names = set()
    for update in got["notification"][0].get("update") or []:
        for t in _denamespace(update["val"] or {}).get("policer-template", []):
            names.add(t.get("name", ""))
    return names


def _telemetry_names(prov: TimingProvisioner) -> set[str]:
    return {d["name"] for d in prov.inner.telemetry_config("srl1")}


def _gas(client: ChainClient, tx_hash: str) -> int:
    return client._w3.eth.get_transaction_receipt(tx_hash)["gasUsed"]


# --- E1/E2/E3: the lifecycle, phase-timed ------------------------------------


def run_lifecycle(stack: Stack, service: str, mode: str, llm, budget_tok: int = 15) -> dict:
    phases: dict[str, float] = {}
    gas: dict[str, int] = {}

    # 1. negotiate — Bell prices, Ada judges (the two judgment slots, rule 1)
    if mode == "llm":
        from agents.provider_graph import QuoteDecision

        t0 = perf_counter()
        quote = llm.structured(
            "You are Bell, a network-service provider pricing one quote. Capacity is "
            "confirmed available; your canonical list price is 10 TOK. Quote a fair "
            "whole-TOK price between 5 and 25, or decline for a business reason.",
            f"NEED: {_need(service).model_dump_json()}", QuoteDecision)
        phases["quote_s"] = perf_counter() - t0
        price = max(1, min(40, quote.price_tok)) if quote.quote else 10
    else:
        price = 10 if service == "bandwidth" else 8

    offer = stack.fresh_offer(service, price)
    t0 = perf_counter()
    signed = stack.bell.sign_offer(offer)
    phases["sign_offer_s"] = perf_counter() - t0

    if mode == "llm":
        from agents.decision import decide

        t0 = perf_counter()
        verdict = decide(llm, _need(service), signed, budget_tok)
        phases["decide_s"] = perf_counter() - t0
        if not verdict.accept:
            return {"ok": False, "err": "llm declined a within-budget offer",
                    "phases": phases, "gas": gas, "service": service, "mode": mode}
    else:
        # the deterministic policy is one comparison; there is no det consumer graph to
        # time, so decide_s is definitionally ~0 (stated as such in docs/09, not sold as a
        # measured phase) — a plain if, not an assert (survives python -O)
        t0 = perf_counter()
        accept = price <= budget_tok
        phases["decide_s"] = perf_counter() - t0
        if not accept:
            return {"ok": False, "err": "det declined a within-budget offer",
                    "phases": phases, "gas": gas, "service": service, "mode": mode}

    # 2. settle — approve + fulfill, atomically minting the ticket
    t0 = perf_counter()
    tx, eid = stack.ada.approve_and_fulfill(signed)
    phases["settle_s"] = perf_counter() - t0
    gas["fulfill"] = _gas(stack.ada, tx)
    try:  # the approve tx landed in the immediately preceding auto-mined block
        receipt = stack.ada._w3.eth.get_transaction_receipt(tx)
        prev = stack.ada._w3.eth.get_block(receipt["blockNumber"] - 1)
        if prev["transactions"]:
            gas["approve"] = stack.ada._w3.eth.get_transaction_receipt(
                prev["transactions"][0])["gasUsed"]
    except Exception:  # noqa: BLE001 — approve gas is contextual, not load-bearing
        pass

    # 3. authorize + actuate — challenge → proof → activate (predicate + gNMI inside)
    t0 = perf_counter()
    challenge = stack.service.challenge(eid)
    phases["challenge_s"] = perf_counter() - t0
    t0 = perf_counter()
    sig = stack.proof(challenge, eid)
    phases["sign_proof_s"] = perf_counter() - t0
    stack.provisioner.last.clear()
    t0 = perf_counter()
    info = stack.service.activate(eid, service, challenge.nonce, sig)
    phases["activate_s"] = perf_counter() - t0
    phases["gnmi_apply_s"] = stack.provisioner.last.get("gnmi_apply_s", 0.0)

    # 4. verify — the config is ON the device (read back over gNMI)
    names = _policer_names if service == "bandwidth" else _telemetry_names
    t0 = perf_counter()
    present = f"a2a-{info.session_id}" in names(stack.provisioner)
    phases["verify_readback_s"] = perf_counter() - t0
    if not present:
        return {"ok": False, "err": "config not found on device after activate",
                "phases": phases, "gas": gas, "service": service, "mode": mode}

    # 5. revoke — the kill switch; lag = tx mined → config gone from the device,
    #    via the REAL watcher thread (poll interval WATCH_POLL_S)
    t0 = perf_counter()
    rtx = stack.bell.revoke(eid)  # blocks until mined
    t_mined = perf_counter()  # anchor immediately — before any extra RPC (harness-reviewer a)
    phases["revoke_tx_s"] = t_mined - t0
    deadline = t_mined + 15
    while f"a2a-{info.session_id}" in names(stack.provisioner):
        if perf_counter() > deadline:
            return {"ok": False, "err": "revocation not enforced within 15s",
                    "phases": phases, "gas": gas, "service": service, "mode": mode}
        time.sleep(0.05)
    phases["revocation_lag_s"] = perf_counter() - t_mined
    gas["revoke"] = _gas(stack.bell, rtx)  # receipt is immutable; fetch off the hot path

    phases["e2e_request_to_enforced_s"] = sum(
        phases.get(k, 0.0) for k in
        ("quote_s", "sign_offer_s", "decide_s", "settle_s", "challenge_s",
         "sign_proof_s", "activate_s"))
    return {"ok": True, "phases": phases, "gas": gas, "service": service, "mode": mode}


def exp_latency(n: int, modes: list[str], out: Path) -> list[dict]:
    lab = _require_lab()
    samples = []
    for mode in modes:
        llm = _llm() if mode == "llm" else None
        if mode == "llm" and llm is None:
            print("  ! llm mode requested but endpoint not up — skipping llm runs")
            continue
        stack = Stack.up(lab)
        try:
            stack.warp_into_window()
            stack.watch()
            for service in ("bandwidth", "telemetry"):
                for i in range(n):
                    sample = run_lifecycle(stack, service, mode, llm)
                    sample.update({"exp": "latency", "run": i})
                    samples.append(sample)
                    _p(f"  latency {mode}/{service} {i + 1}/{n} "
                       f"{'ok' if sample['ok'] else 'FAIL ' + sample['err']} "
                       f"e2e={sample['phases'].get('e2e_request_to_enforced_s', 0):.2f}s "
                       f"revlag={sample['phases'].get('revocation_lag_s', 0):.2f}s")
        finally:
            stack.down()
    _write(out / "latency.jsonl", samples)
    return samples


# --- E2b: expiry — chain time passes end_time → device deconfigured ----------


def exp_expiry(n: int, out: Path) -> list[dict]:
    lab = _require_lab()
    samples = []
    for i in range(n):
        stack = Stack.up(lab)  # fresh chain per trial: warping past end is one-way
        try:
            stack.warp_into_window()
            offer = stack.fresh_offer("bandwidth")
            _, eid = stack.ada.approve_and_fulfill(stack.bell.sign_offer(offer))
            challenge = stack.service.challenge(eid)
            info = stack.service.activate(eid, "bandwidth", challenge.nonce,
                                          stack.proof(challenge, eid))
            stack.anvil.increase_time(stack.ada._w3,
                                      WINDOW.end - stack.reader.chain_time() + 5)
            t0 = perf_counter()
            stack.service.tick()  # re-checks chain time and tears down SYNCHRONOUSLY
            lag = perf_counter() - t0  # tick() returns after the gNMI delete completes
            # confirm (not time) the device is clear — the readback would otherwise inflate
            # tick_to_deconfig by a full gNMI round-trip (harness-reviewer e)
            assert f"a2a-{info.session_id}" not in _policer_names(stack.provisioner)
            samples.append({"exp": "expiry", "run": i, "ok": True,
                            "tick_to_deconfig_s": lag})
            _p(f"  expiry {i + 1}/{n} tick→deconfig {lag * 1000:.0f}ms")
        finally:
            stack.down()
    _write(out / "expiry.jsonl", samples)
    return samples


# --- E6: baseline — the same actuation with no agents, no chain, no controller


def exp_baseline(n: int, out: Path) -> list[dict]:
    lab = _require_lab()
    prov = GnmiProvisioner({"srl1": GnmiTarget(host=lab, tls_name="srl1")})
    samples = []
    try:
        for i in range(n):
            t0 = perf_counter()
            assert prov.apply_bandwidth(f"base-{i}", RESOLVED_PATH, CAPACITY, QOS).ok
            apply_s = perf_counter() - t0
            t0 = perf_counter()
            assert prov.teardown(f"base-{i}").ok
            teardown_s = perf_counter() - t0
            samples.append({"exp": "baseline", "run": i, "ok": True,
                            "apply_s": apply_s, "teardown_s": teardown_s})
            _p(f"  baseline {i + 1}/{n} apply {apply_s:.3f}s teardown {teardown_s:.3f}s")
    finally:
        prov.close()
    _write(out / "baseline.jsonl", samples)
    return samples


# --- E4: adversarial — every attack, and WHICH layer rejected it -------------


def exp_adversarial(out: Path) -> list[dict]:
    lab = _require_lab()
    stack = Stack.up(lab)
    results = []

    def attempt(attack: str, expect_layer: str, fn) -> None:
        try:
            fn()
            results.append({"exp": "adversarial", "attack": attack, "rejected": False,
                            "layer": None, "code": None})
            _p(f"  !! {attack}: NOT REJECTED")
        except ChainRevert as err:
            results.append({"exp": "adversarial", "attack": attack, "rejected": True,
                            "layer": "contract", "code": getattr(err, "name", str(err)),
                            "expected_layer": expect_layer})
            _p(f"  {attack}: rejected by contract ({getattr(err, 'name', err)})")
        except Denied as err:
            results.append({"exp": "adversarial", "attack": attack, "rejected": True,
                            "layer": "controller", "code": err.code.value,
                            "expected_layer": expect_layer})
            _p(f"  {attack}: rejected by controller ({err.code.value})")
        except KeyError:
            results.append({"exp": "adversarial", "attack": attack, "rejected": True,
                            "layer": "chain-read", "code": "unknown id",
                            "expected_layer": expect_layer})
            _p(f"  {attack}: rejected at the chain read (unknown id)")

    try:
        # -- before the window opens (chain is at 13:32) --------------------------
        offer0 = stack.fresh_offer("bandwidth")
        _, eid0 = stack.ada.approve_and_fulfill(stack.bell.sign_offer(offer0))
        ch0 = stack.service.challenge(eid0)
        attempt("activate before window start", "controller",
                lambda: stack.service.activate(eid0, "bandwidth", ch0.nonce,
                                               stack.proof(ch0, eid0)))

        stack.warp_into_window()

        # -- contract layer --------------------------------------------------------
        used = stack.fresh_offer("bandwidth")
        signed_used = stack.bell.sign_offer(used)
        stack.ada.approve_and_fulfill(signed_used)
        attempt("replay a consumed offer (same salt)", "contract",
                lambda: stack.ada.approve_and_fulfill(signed_used))

        forged = stack.fresh_offer("bandwidth")
        fake = stack.mallory.sign_offer(forged.model_copy(update={"provider": BELL}))
        attempt("forged provider signature", "contract",
                lambda: stack.ada.approve_and_fulfill(fake))

        stale = stack.fresh_offer("bandwidth").model_copy(
            update={"valid_until": stack.reader.chain_time() - 10})
        attempt("fulfill a lapsed offer (valid_until past)", "contract",
                lambda: stack.ada.approve_and_fulfill(stack.bell.sign_offer(stale)))

        # -- controller layer ------------------------------------------------------
        offer1 = stack.fresh_offer("bandwidth")
        _, eid1 = stack.ada.approve_and_fulfill(stack.bell.sign_offer(offer1))

        ch = stack.service.challenge(eid1)
        attempt("activation proof signed by a non-owner", "controller",
                lambda: stack.service.activate(eid1, "bandwidth", ch.nonce,
                                               stack.proof(ch, eid1, key="mallory")))

        ch_g = stack.service.challenge(eid1)
        attempt("garbage activation signature", "controller",
                lambda: stack.service.activate(eid1, "bandwidth", ch_g.nonce,
                                               "0x" + "ab" * 65))

        ch2 = stack.service.challenge(eid1)
        good = stack.proof(ch2, eid1)
        info1 = stack.service.activate(eid1, "bandwidth", ch2.nonce, good)
        attempt("replay a consumed challenge nonce", "controller",
                lambda: stack.service.activate(eid1, "bandwidth", ch2.nonce, good))

        ch2b = stack.service.challenge(eid1)
        attempt("activate the same ticket twice (double-booking)", "controller",
                lambda: stack.service.activate(eid1, "bandwidth", ch2b.nonce,
                                               stack.proof(ch2b, eid1)))

        # NOT an attack the controller guards: a SECOND ticket on the same resource
        # activates fine — per-resource capacity is the provider's CapacityLedger's
        # job at quote time (M5.2); the controller's E_CONFLICT is per-ticket. Record
        # it honestly as allowed-by-design so the report can discuss the layering.
        offer2 = stack.fresh_offer("bandwidth")
        _, eid2 = stack.ada.approve_and_fulfill(stack.bell.sign_offer(offer2))
        ch3 = stack.service.challenge(eid2)
        try:
            info2 = stack.service.activate(eid2, "bandwidth", ch3.nonce,
                                           stack.proof(ch3, eid2))
            results.append({"exp": "adversarial",
                            "attack": "second ticket on the same resource",
                            "rejected": False, "layer": None, "code": None,
                            "by_design": "capacity is guarded at the provider's "
                                         "CapacityLedger (quote time), not the "
                                         "controller; E_CONFLICT is per-ticket"})
            _p("  second ticket on the same resource: allowed (by design — "
               "provider-ledger guards capacity)")
            stack.service.teardown(info2.session_id)
        except Denied as err:  # would indicate the semantics changed under us
            results.append({"exp": "adversarial",
                            "attack": "second ticket on the same resource",
                            "rejected": True, "layer": "controller",
                            "code": err.code.value})
        stack.service.teardown(info1.session_id)  # clean slate for the next cases

        offer3s = stack.fresh_offer("bandwidth")
        _, eid3s = stack.ada.approve_and_fulfill(stack.bell.sign_offer(offer3s))
        ch_scope = stack.service.challenge(eid3s)
        attempt("telemetry action on a bandwidth ticket (scope)", "controller",
                lambda: stack.service.activate(eid3s, "telemetry", ch_scope.nonce,
                                               stack.proof(ch_scope, eid3s)))

        stack.bell.revoke(eid3s)
        ch4 = stack.service.challenge(eid3s)
        attempt("activate a revoked ticket", "controller",
                lambda: stack.service.activate(eid3s, "bandwidth", ch4.nonce,
                                               stack.proof(ch4, eid3s)))

        attempt("challenge for a nonexistent ticket", "controller",
                lambda: stack.service.challenge(999))

        # -- after the window (one-way warp; keep last). The challenge is issued
        # AFTER the warp so it is itself fresh — the ticket's expiry, not the
        # challenge's, must be what denies.
        offer3 = stack.fresh_offer("bandwidth")
        _, eid3 = stack.ada.approve_and_fulfill(stack.bell.sign_offer(offer3))
        stack.anvil.increase_time(stack.ada._w3,
                                  WINDOW.end - stack.reader.chain_time() + 5)
        ch5 = stack.service.challenge(eid3)
        attempt("activate after window end", "controller",
                lambda: stack.service.activate(eid3, "bandwidth", ch5.nonce,
                                               stack.proof(ch5, eid3)))
    finally:
        stack.down()
    _write(out / "adversarial.jsonl", results)
    return results


# --- E5: LLM judgment robustness + accuracy ----------------------------------


def exp_llm(out: Path) -> list[dict]:
    llm = _llm(measure_cold=True)
    if llm is None:
        print("  ! LLM endpoint not reachable — skipping (set .env / A2A_LIVE_LLM=1)")
        return []
    from agents.decision import decide
    from agents.llm import StructuredError
    from agents.provider_graph import QuoteDecision

    samples = []

    # quote slot: 10 needs of varying size — schema validity + price-range compliance
    for i, mbps in enumerate((10, 20, 30, 50, 80, 100, 150, 200, 300, 500)):
        need = BANDWIDTH_NEED.model_copy(update={"capacity_bps": mbps * 1_000_000})
        t0 = perf_counter()
        try:
            q = llm.structured(
                "You are Bell, a network-service provider pricing one quote. Capacity "
                "is confirmed available; your canonical list price is 10 TOK. Quote a "
                "fair whole-TOK price between 5 and 25, or decline for a business "
                "reason.", f"NEED: {need.model_dump_json()}", QuoteDecision)
            samples.append({"exp": "llm", "slot": "quote", "case": f"{mbps}mbps",
                            "ok": True, "latency_s": perf_counter() - t0,
                            "attempts": llm.last_attempts, "usage": llm.last_usage,
                            "quoted": q.price_tok if q.quote else None,
                            "in_range": bool(q.quote and 5 <= q.price_tok <= 25)})
        except StructuredError as err:
            samples.append({"exp": "llm", "slot": "quote", "case": f"{mbps}mbps",
                            "ok": False, "latency_s": perf_counter() - t0,
                            "attempts": len(err.attempts)})
        _p(f"  llm quote {i + 1}/10 {samples[-1]}")

    # decide slot: ground-truth accuracy — accept iff the offer meets the need AND
    # price ≤ budget. Boundary (price == budget) tagged so the report can split it out.
    cases = [(5, 15, True), (9, 15, True), (14, 15, True), (15, 15, True),
             (16, 15, False), (20, 15, False), (40, 15, False), (10, 8, False),
             (8, 8, True), (25, 30, True), (31, 30, False), (12, 12, True)]
    for i, (price, budget, expect) in enumerate(cases):
        offer = stack_free_offer(price)
        t0 = perf_counter()
        try:
            verdict = decide(llm, BANDWIDTH_NEED, offer, budget)
            samples.append({
                "exp": "llm", "slot": "decide", "case": f"p{price}b{budget}",
                "ok": True, "latency_s": perf_counter() - t0,
                "attempts": llm.last_attempts, "usage": llm.last_usage,
                "expected": expect, "got": verdict.accept,
                "correct": verdict.accept == expect, "boundary": price == budget,
                "reason": verdict.reason[:120]})
        except StructuredError as err:
            samples.append({"exp": "llm", "slot": "decide", "case": f"p{price}b{budget}",
                            "ok": False, "latency_s": perf_counter() - t0,
                            "attempts": len(err.attempts), "expected": expect})
        _p(f"  llm decide {i + 1}/{len(cases)} "
           f"{'ok' if samples[-1].get('correct') else samples[-1]}")

    _write(out / "llm.jsonl", samples)
    return samples


def stack_free_offer(price_tok: int):
    """A signed offer without a chain: sign_offer only needs the key + domain params,
    so a throwaway Anvil-free signer would do — but reusing the fixture keeps the offer
    byte-identical to the lifecycle ones. Signature validity is NOT under test here."""
    from types import SimpleNamespace

    offer = CANONICAL_OFFER.model_copy(update={"price": str(price_tok * 10**18)})
    return SimpleNamespace(offer=offer, signature="0x" + "11" * 65,
                           model_dump_json=lambda **k: json.dumps(
                               {"offer": offer.model_dump(mode="json")}))


# --- E7: the authorization predicate, isolated (the sharpest feasibility number) ---


def exp_predicate(out: Path) -> list[dict]:
    """`controller.domain.predicate` is a pure function over an EntitlementView — zero I/O
    (rule 4). Time it in isolation across all seven outcomes so docs/09 can state the core
    contribution's cost without the chain reads and gNMI that `activate_s` bundles."""
    import timeit

    from a2a_interfaces.fixtures import CANONICAL_ENTITLEMENT_VIEW as V
    from controller.domain import predicate

    owner = "0x" + "a" * 40
    mid = WINDOW.start + 60
    cases = {
        "allow": (V, owner, owner, mid, set()),
        "E_NOT_OWNER": (V, owner, "0x" + "b" * 40, mid, set()),
        "E_NOT_STARTED": (V, owner, owner, WINDOW.start - 10, set()),
        "E_EXPIRED": (V, owner, owner, WINDOW.end + 10, set()),
        "E_REVOKED": (V.model_copy(update={"revoked": True}), owner, owner, mid, set()),
        "E_SCOPE": (V.model_copy(update={"service_type": 9}), owner, owner, mid, set()),
        "E_CONFLICT": (V, owner, owner, mid, {V.id}),
    }
    samples = []
    loops = 200_000
    for name, args in cases.items():
        secs = timeit.timeit(lambda a=args: predicate(*a), number=loops)
        ns = secs / loops * 1e9
        samples.append({"exp": "predicate", "outcome": name, "ns_per_call": ns, "loops": loops})
        _p(f"  predicate {name:14} {ns:7.0f} ns/call")
    _write(out / "predicate.jsonl", samples)
    return samples


# --- E9: revocation-lag sensitivity to the watcher poll interval -------------


def exp_revlag_sweep(out: Path, polls=(0.1, 0.25, 0.5, 1.0, 2.0), per=6) -> list[dict]:
    """Answers the objection 'your 0.5 s lag is just your polling choice': sweep the poll
    interval and show lag ≈ poll/2 + a fixed actuation floor. Only the settle→activate→
    revoke portion, reusing the real watcher."""
    lab = _require_lab()
    samples = []
    for poll in polls:
        for i in range(per):
            stack = Stack.up(lab)
            stack.reader._poll_interval = poll  # the watcher reads this each loop
            try:
                stack.warp_into_window()
                stack.watch()
                _, eid = stack.ada.approve_and_fulfill(
                    stack.bell.sign_offer(stack.fresh_offer("bandwidth")))
                ch = stack.service.challenge(eid)
                info = stack.service.activate(eid, "bandwidth", ch.nonce, stack.proof(ch, eid))
                stack.bell.revoke(eid)
                t = perf_counter()
                while f"a2a-{info.session_id}" in _policer_names(stack.provisioner):
                    time.sleep(0.02)
                lag = perf_counter() - t
                samples.append({"exp": "revlag_sweep", "poll_s": poll, "run": i,
                                "revocation_lag_s": lag})
            finally:
                stack.down()
        got = [s["revocation_lag_s"] for s in samples if s["poll_s"] == poll]
        _p(f"  poll={poll:>4}s  lag median {statistics.median(got) * 1000:.0f} ms  (n={len(got)})")
    _write(out / "revlag_sweep.jsonl", samples)
    return samples


# --- helpers ------------------------------------------------------------------


def _need(service: str):
    return BANDWIDTH_NEED if service == "bandwidth" else TELEMETRY_NEED


def _require_lab() -> str:
    lab = lab_ipv4()
    if lab is None:
        raise SystemExit("experiments need the SR Linux lab: "
                         "containerlab deploy -t netlab/topology.clab.yml")
    return lab


_COLD_START: dict = {}


def _llm(measure_cold: bool = False):
    from agents.llm import LLMClient, LLMConfig, llm_up

    cfg = LLMConfig.from_env()
    if "localhost" in cfg.base_url and not llm_up(cfg, timeout=5.0):
        return None
    # A booting scale-to-zero container can answer one probe with a transient non-200;
    # retry the bounded probe rather than declaring the endpoint absent on one miss.
    t0 = perf_counter()
    for _ in range(4):
        if llm_up(cfg, timeout=120.0):
            break
        time.sleep(5)
    else:
        return None
    warm = perf_counter() - t0
    # time-to-probe-success, quantized to the 5 s retry sleep — an "endpoint ready" figure,
    # NOT time-to-first-token (harness-reviewer nit e)
    if measure_cold and warm > 5.0 and "cold_start_probe_s" not in _COLD_START:
        _COLD_START["cold_start_probe_s"] = round(warm, 1)
        _p(f"  (endpoint became ready after ~{warm:.0f}s — scale-to-zero cold start)")
    return LLMClient(cfg)


def _p(msg: str) -> None:
    print(msg, flush=True)


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    _p(f"  wrote {len(rows)} rows → {path}")


def _stats(values: list[float]) -> dict:
    """median + spread. NOTE on p95: at n=20 a percentile is barely more than the max, so
    we report [min,max] as the honest spread and a *nearest-rank* p95 (ceil(0.95n)-1, which
    is NOT the max — the earlier int(0.95n) bug made it the max) only as a hint. docs/09
    cites median + range, not p95, at these sample sizes (methodology-critic)."""
    import math

    if not values:
        return {}
    ordered = sorted(values)
    n = len(ordered)
    return {"n": n, "median": statistics.median(ordered), "mean": statistics.fmean(ordered),
            "p95_nearest_rank": ordered[min(n - 1, math.ceil(0.95 * n) - 1)],
            "min": ordered[0], "max": ordered[-1]}


def summarize(out: Path) -> dict:
    summary: dict = {"generated_by": "e2e.experiments", "watch_poll_s": WATCH_POLL_S}
    summary.update(_COLD_START)
    lat = _read(out / "latency.jsonl")
    if lat:
        by: dict = {}
        for mode in ("det", "llm"):
            for service in ("bandwidth", "telemetry"):
                rows = [r for r in lat if r["mode"] == mode and r["service"] == service
                        and r["ok"]]
                if not rows:
                    continue
                keys = sorted({k for r in rows for k in r["phases"]})
                by[f"{mode}/{service}"] = {
                    k: _stats([r["phases"][k] for r in rows if k in r["phases"]])
                    for k in keys}
        summary["latency"] = by
        # gas PER SERVICE — fulfill is bimodal (telemetry offers carry larger ABI params),
        # so a pooled median matches no real tx (methodology-critic)
        summary["gas"] = {}
        for svc in ("bandwidth", "telemetry"):
            grows = [r["gas"] for r in lat if r["ok"] and r.get("gas") and r["service"] == svc]
            summary["gas"][svc] = {k: _stats([g[k] for g in grows if k in g])
                                   for k in ("approve", "fulfill", "revoke")}
        summary["runs_total"] = len(lat)
        summary["runs_ok"] = sum(r["ok"] for r in lat)
        summary["failures"] = [r for r in lat if not r["ok"]]
    exp = _read(out / "expiry.jsonl")
    if exp:
        summary["expiry_tick_to_deconfig_s"] = _stats(
            [r["tick_to_deconfig_s"] for r in exp if r["ok"]])
    base = _read(out / "baseline.jsonl")
    if base:
        summary["baseline"] = {
            "apply_s": _stats([r["apply_s"] for r in base if r["ok"]]),
            "teardown_s": _stats([r["teardown_s"] for r in base if r["ok"]])}
    adv = _read(out / "adversarial.jsonl")
    if adv:
        summary["adversarial"] = {
            "total": len(adv),
            "rejected": sum(r["rejected"] for r in adv),
            "allowed_by_design": sum(1 for r in adv if r.get("by_design")),
            "rows": adv}
    llm = _read(out / "llm.jsonl")
    if llm:
        quotes = [r for r in llm if r["slot"] == "quote"]
        decides = [r for r in llm if r["slot"] == "decide"]
        graded = [r for r in decides if r["ok"]]
        nonboundary = [r for r in graded if not r.get("boundary")]
        summary["llm"] = {
            "quote": {"n": len(quotes), "valid": sum(r["ok"] for r in quotes),
                      "in_range": sum(bool(r.get("in_range")) for r in quotes),
                      "latency_s": _stats([r["latency_s"] for r in quotes if r["ok"]]),
                      "attempts": _stats([float(r["attempts"]) for r in quotes])},
            "decide": {"n": len(decides), "valid": len(graded),
                       "correct": sum(r["correct"] for r in graded),
                       "correct_nonboundary": sum(r["correct"] for r in nonboundary),
                       "n_nonboundary": len(nonboundary),
                       "quoted_values": sorted({r.get("quoted") for r in quotes if r.get("ok")}),
                       "latency_s": _stats([r["latency_s"] for r in graded]),
                       "tokens_per_call": _stats([
                           float(r["usage"]["prompt_tokens"]
                                 + r["usage"]["completion_tokens"])
                           for r in graded if r.get("usage")])},
        }
        # E8: cost per negotiation = quote + decide tokens, priced at two rates. Report
        # tokens as primary; USD depends on the deployment (self-host GPU-hour vs public API).
        q_tok = _stats([float(r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"])
                        for r in quotes if r.get("ok") and r.get("usage")])
        neg_tokens = q_tok.get("median", 0) + summary["llm"]["decide"]["tokens_per_call"].get("median", 0)
        summary["llm"]["cost_per_negotiation"] = {
            "quote_tokens_median": q_tok.get("median"),
            "decide_tokens_median": summary["llm"]["decide"]["tokens_per_call"].get("median"),
            "total_tokens_median": neg_tokens,
            "usd_at_0.20_per_Mtok": round(neg_tokens / 1e6 * 0.20, 6),  # ~ small open model, public API
            "usd_at_2.00_per_Mtok": round(neg_tokens / 1e6 * 2.00, 6),  # ~ mid-tier hosted
        }
    pred = _read(out / "predicate.jsonl")
    if pred:
        summary["predicate"] = {r["outcome"]: round(r["ns_per_call"], 1) for r in pred}
    sweep = _read(out / "revlag_sweep.jsonl")
    if sweep:
        polls = sorted({r["poll_s"] for r in sweep})
        summary["revlag_sweep"] = {
            str(p): _stats([r["revocation_lag_s"] for r in sweep if r["poll_s"] == p])
            for p in polls}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    _p(f"summary → {out / 'summary.json'}")
    return summary


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", default="all",
                        choices=["all", "latency", "expiry", "baseline", "adversarial",
                                 "llm", "predicate", "revlag_sweep", "summarize"])
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--mode", default="both", choices=["det", "llm", "both"])
    parser.add_argument("--out", type=Path,  # e2e/runs/eval — beside the console's runs/
                        default=Path(__file__).resolve().parents[2] / "runs" / "eval")
    args = parser.parse_args()
    modes = ["det", "llm"] if args.mode == "both" else [args.mode]

    if args.exp in ("all", "latency"):
        _p(f"== latency (n={args.n} per mode×service) ==")
        exp_latency(args.n, modes, args.out)
    if args.exp in ("all", "expiry"):
        _p("== expiry (n=10) ==")
        exp_expiry(min(args.n, 10), args.out)
    if args.exp in ("all", "baseline"):
        _p(f"== baseline (n={args.n}) ==")
        exp_baseline(args.n, args.out)
    if args.exp in ("all", "adversarial"):
        _p("== adversarial ==")
        exp_adversarial(args.out)
    if args.exp in ("all", "llm"):
        _p("== llm judgment ==")
        exp_llm(args.out)
    if args.exp in ("all", "predicate"):
        _p("== predicate microbenchmark ==")
        exp_predicate(args.out)
    if args.exp in ("all", "revlag_sweep"):
        _p("== revocation-lag poll sweep ==")
        exp_revlag_sweep(args.out)
    summarize(args.out)


if __name__ == "__main__":
    main()
