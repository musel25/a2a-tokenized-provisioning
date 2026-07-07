"""The console's engine: run the REAL pipeline, emit rich typed events for the UI.

One `Console` holds a single operator session — Anvil + the deployed contracts + a real
controller + Ada's and Bell's chainmcp clients + (if the lab is up) a GnmiProvisioner.
`provision()` and `revoke()` drive the actual lifecycle and call `emit(event)` at every
interesting step: A2A messages, MCP tool calls, on-chain transactions with real hashes,
predicate checks, device config reads, iperf measurements. The frontend turns those into
the relay animation, the event stream, and the device inspector.

Everything here is real: real EIP-712 signatures, real ERC-721 mints, real tx hashes,
real gNMI Sets, real iperf. The router lane degrades honestly to "offline" when the lab
isn't deployed; the chain/controller/agent lanes are always live.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import eth_abi

from a2a_interfaces import Offer
from a2a_interfaces.fixtures import (
    ADA,
    BELL,
    CANONICAL_OFFER,
    MOCK_TOK,
    TELEMETRY_NEED,
    TELEMETRY_RESOURCE_ID,
    TERMS_HASH,
    WINDOW,
)
from chainmcp import ChainClient, ChainReader
from chainmcp.mcp_server import chain_tools
from chainmcp.testing import ANVIL_KEYS, anvil_available, artifacts_available, launch_anvil
from controller.auth import AuthStore, proof_message
from controller.resource_map import load_resource_map
from controller.service import ControllerService
from netctl import paths
from netctl.connect import GnmiTarget
from netctl.provisioner import GnmiProvisioner, _denamespace
from netctl.testing import lab_ipv4

STORY_TIME = WINDOW.start - 1680  # 13:32, before the window
Emit = Callable[[dict], None]


@dataclass
class Console:
    anvil: object = None
    ada: ChainClient = None
    bell: ChainClient = None
    reader: ChainReader = None
    controller: ControllerService = None
    controller_id: str = "bw-ctrl-1"
    provisioner: object = None  # GnmiProvisioner if lab up, else None
    lab_ip: str | None = None
    sessions: dict[int, str] = field(default_factory=dict)  # entitlement_id → session_id
    last_service: str = "bandwidth"  # what the most recent provision bought (drives teardown view)
    _nonce: int = 100  # bumped per provision so each offer has a fresh salt (single-use, I2)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # --- capability + lifecycle ---------------------------------------------

    def status(self) -> dict:
        return {
            "anvil": self.anvil is not None,
            "lab": (self.lab_ip is not None) or (lab_ipv4() is not None),
            "artifacts": artifacts_available(),
            "anvil_available": anvil_available(),
            "sessions": {str(k): v for k, v in self.sessions.items()},
            "chain_time": self.reader.chain_time() if self.reader else None,
        }

    def ensure_started(self, emit: Emit) -> None:
        with self._lock:
            if self.anvil is not None:
                return
            emit(_ev("boot", "chain", "Starting local chain", "anvil — story time 13:32"))
            self.anvil = launch_anvil(timestamp=STORY_TIME)
            self.lab_ip = lab_ipv4()
            self.bell = _client("bell", self.anvil)
            self.ada = _client("ada", self.anvil)
            self.reader = ChainReader(self.anvil.rpc_url, deployment=self.anvil.deployment)
            emit(_ev("boot", "chain", "Contracts deployed",
                     f"MockTOK {MOCK_TOK[:10]}…  ·  A2ASettlement {self.anvil.deployment['A2ASettlement'][:10]}…"))
            self._seed_presales()  # so Ada's bandwidth ticket is literally #7
            self.ada.faucet(200 * 10**18)
            if self.lab_ip:
                self.provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=self.lab_ip, tls_name="srl1")})
                net = self.provisioner
                emit(_ev("boot", "network", "Router online", f"SR Linux srl1 @ {self.lab_ip}"))
            else:
                from netctl.mock import MockProvisioner

                net = MockProvisioner()
                emit(_ev("boot", "network", "Router offline", "start containerlab to see live enforcement"))
            self.controller = ControllerService(
                self.reader, net, AuthStore(self.controller_id), load_resource_map()
            )
            emit(_ev("boot", "controller", "Controller ready", "predicate · auth · session machine"))

    def _seed_presales(self) -> None:
        carol = _client("carol", self.anvil)
        try:
            carol.faucet(60 * 10**18)
            for i in range(1, 7):
                pre = CANONICAL_OFFER.model_copy(update={"salt": "0x" + f"{i:064x}"})
                carol.approve_and_fulfill(self.bell.sign_offer(pre))
        finally:
            carol.close()

    def reset(self) -> None:
        with self._lock:
            for c in (self.ada, self.bell, self.reader):
                if c:
                    c.close()
            if self.provisioner:
                for eid in list(self.sessions):
                    self.provisioner.teardown(f"ent{eid}")
                self.provisioner.close()
            if self.anvil:
                self.anvil.stop()
            self.anvil = self.ada = self.bell = self.reader = self.controller = self.provisioner = None
            self.lab_ip = None
            self.sessions = {}

    def close(self) -> None:
        self.reset()

    # --- the flows ----------------------------------------------------------

    def chat(self, text: str, emit: Emit) -> None:
        """The front door: Ada's agent reads a plain-language request, decides what to
        buy, says so, then runs the pipeline. The interpretation is an LLM call when one
        is fast enough; otherwise a deterministic parse stands in (same result)."""
        emit(_chat("you", text))
        intent = _parse_intent(text)
        emit(_chat("Ada", f"On it — I'll buy **{intent['label']}** (budget {intent['budget']} TOK). "
                          f"{intent['why']}"))
        self.provision(intent["service"], intent["budget"], emit)

    def provision(self, service: str, budget_tok: int, emit: Emit) -> None:
        self.ensure_started(emit)
        self.last_service = service
        self._nonce += 1  # a fresh salt each click — every offer is single-use (I2)
        offer = self._offer_for(service, self._nonce)
        need = _need_for(service)
        eid = None
        try:
            # 1. AGENT — discovery + quote (A2A) and judgment (the LLM slot, shown)
            emit(_stage("agent", "Agents negotiate"))
            emit(_a2a("Ada", "Bell", f"quote_{service}",
                      f"need {service} · {_mbps(need)} · window 14:00–16:00",
                      expand=_a2a_out(service, need)))
            price = int(offer.offer.price) // 10**18 if service == "bandwidth" else 8
            emit(_mcp("Bell", "chainmcp", "sign_offer",
                      f"{service} @ {price} TOK", "EIP-712 signature (65 bytes)",
                      expand={"server": "chainmcp (Bell's key custody)", "tool": "sign_offer",
                              "args": {"offer": _clip(offer.offer.model_dump(mode="json"))},
                              "result": {"signature": offer.signature}}))
            emit(_a2a("Bell", "Ada", "signed_offer", f"{price} TOK · signed",
                      expand=_a2a_reply(offer)))
            accept = price <= budget_tok
            emit(_decision("Ada", accept,
                           f"{price} TOK {'≤' if accept else '>'} budget {budget_tok} TOK — "
                           f"{'accept' if accept else 'decline'}"))
            if not accept:
                emit(_done(False, "Ada declined — over budget. Nothing purchased."))
                return

            # 2. CHAIN — settle: MCP fulfill → real on-chain tx, ticket, payment
            emit(_stage("chain", "Payment for ticket, atomically"))
            tools = chain_tools(self.ada)
            emit(_mcp("Ada", "chainmcp", "fulfill_offer", f"approve {price} TOK + fulfill", "…",
                      expand={"server": "chainmcp (Ada's key custody)", "tool": "fulfill_offer",
                              "args": {"signed_offer": _clip(offer.model_dump(mode="json"))},
                              "note": "approves ERC-20 then calls A2ASettlement.fulfill — one atomic tx"}))
            result = tools["fulfill_offer"](offer.model_dump(mode="json"))
            eid = result["entitlement_id"]
            self.sessions.setdefault(eid, None)
            block = self.ada._w3.eth.get_block("latest")
            emit(_chain_tx("fulfill", result["tx_hash"], block["number"],
                           f"ticket #{eid} → Ada · {price} TOK → Bell · salt consumed",
                           expand={"method": "A2ASettlement.fulfill(SignedOffer)", "from": "Ada",
                                   "tx_hash": result["tx_hash"], "block": block["number"],
                                   "effects": [f"mint ERC-721 #{eid} → Ada", f"transfer {price} TOK Ada → Bell",
                                               "mark offer salt used (single-use, I2)"]}))
            emit(_chain_read("ownerOf(%d)" % eid, self.ada.owner_of(eid)))
            emit(_chain_read("Bell balance", f"{self.ada.tok_balance(BELL) // 10**18} TOK"))
            emit(_ticket(self._ticket_view(eid)))  # the NFT panel populates here

            # 3. CONTROLLER — challenge → proof → predicate → authorize
            emit(_stage("controller", "Authorize by on-chain ownership"))
            self.anvil.increase_time(self.ada._w3, 1800)  # into the window (14:02)
            challenge = self.controller.challenge(eid)
            emit(_mcp("controller", "ctrl-mcp", "get_challenge",
                      f"entitlement #{eid}", f"nonce {challenge.nonce[:14]}…",
                      expand={"server": "controller HTTP API", "tool": "POST /challenge",
                              "args": {"entitlement_id": eid},
                              "result": {"controller_id": challenge.controller_id, "nonce": challenge.nonce,
                                         "expires_at": challenge.expires_at}}))
            msg = proof_message(challenge.controller_id, challenge.nonce, eid, challenge.expires_at)
            sig = "0x" + self.ada._acct.sign_message(_defunct(msg)).signature.hex()
            emit(_mcp("Ada", "chainmcp", "sign_activation_proof",
                      "a2a-activate|…", "EIP-191 signature",
                      expand={"server": "chainmcp (Ada's key custody)", "tool": "sign_activation_proof",
                              "args": {"message": msg}, "result": {"signature": sig},
                              "note": "proves Ada controls the owner address — controller verifies, never signs"}))
            checks = _predicate_checks(self.reader.get(eid), self.reader.chain_time(), ADA)
            emit(_predicate(checks))
            info = self.controller.activate(eid, service, challenge.nonce, sig)
            self.sessions[eid] = info.session_id
            emit(_ev("session", "controller", f"Session {info.session_id} active",
                     f"state {info.state.value} · expires {_hm(info.expires_at)}"))

            # 4. NETWORK — enforce on the real router (or note offline)
            emit(_stage("network", "Configure the real router"))
            self._emit_enforcement(service, eid, info.session_id, emit)
            emit(_done(True, f"{service} live — ticket #{eid}. Bell can revoke it any time."))
        except Exception as err:  # noqa: BLE001 — surface to the UI, don't crash the server
            emit(_ev("error", "controller", "Provision failed", str(err)[:200]))

    def revoke(self, emit: Emit) -> None:
        active = [eid for eid, sid in self.sessions.items() if sid]
        if not active:
            emit(_ev("error", "chain", "Nothing to revoke", "provision a service first"))
            return
        eid = active[-1]
        sid = self.sessions[eid]
        try:
            emit(_stage("chain", "Bell pulls the ticket"))
            tx = self.bell.revoke(eid)
            block = self.bell._w3.eth.get_block("latest")
            emit(_chain_tx("revoke", tx, block["number"], f"Revoked(#{eid}) — flag flips on-chain",
                           break_signal=True,
                           expand={"method": "A2ASettlement.revoke(uint256)", "from": "Bell (issuer)",
                                   "tx_hash": tx, "block": block["number"],
                                   "effects": [f"entitlement[{eid}].revoked = true",
                                               "Ada still OWNS the NFT — only the right is voided"]}))
            emit(_ticket(self._ticket_view(eid)))  # NFT panel: revoked flag flips to true
            emit(_stage("controller", "Watcher tears the session down"))
            self.controller.handle_revoked(eid)  # the ChainReader watcher does this live too
            emit(_ev("teardown", "controller", f"Session {sid} torn down",
                     "revoked ticket → no authorization"))
            emit(_stage("network", "Enforcement withdrawn"))
            self._emit_teardown(eid, sid, emit)
            self.sessions[eid] = None
            emit(_done(True, f"Ticket #{eid} revoked. Throughput returned to unshaped."))
        except Exception as err:  # noqa: BLE001
            emit(_ev("error", "chain", "Revoke failed", str(err)[:200]))

    def _ticket_view(self, eid: int) -> dict:
        """The NFT as the panel shows it — owner from ownerOf, everything else decoded from
        the on-chain tokenURI (metadata lives entirely on-chain, no external server)."""
        import base64

        owner = self.reader.owner_of(eid)
        meta = json.loads(base64.b64decode(self.reader.token_uri(eid).split(",", 1)[1]))
        return {
            "id": eid, "name": meta["name"], "symbol": "A2AENT",
            "owner": owner, "owner_label": "Ada",
            "issuer": meta["issuer"], "issuer_label": "Bell",
            "service": "bandwidth" if meta["serviceType"] == 0 else "telemetry",
            "window": f"{_hm(meta['startTime'])}–{_hm(meta['endTime'])}",
            "resource_id": meta["resourceId"], "revoked": meta["revoked"], "metadata": meta,
        }

    # --- network / device helpers -------------------------------------------

    def _emit_enforcement(self, service: str, eid: int, sid: str, emit: Emit) -> None:
        # The CONTROLLER already applied enforcement during activate() — the console only
        # OBSERVES it (reads config off the router, measures throughput). Re-applying here
        # would double-do the controller's job.
        if not self.provisioner:
            emit(_ev("device", "network", "Router offline",
                     "the controller authorized; start containerlab to see the policer land"))
            return
        if service == "bandwidth":
            _shim()  # ADR-006: the lab's missing ASIC, materialized as tc
            emit(_device(self.device_state()))
            emit(_iperf_ev(_iperf(), shaped=True))
        else:
            # the ticket authorized the controller to write telemetry-export config to the
            # router — read it back off srl1 as proof (symmetric with the policer)
            dests = self.provisioner.telemetry_config("srl1")
            d = dests[0] if dests else {}
            state = {
                "online": True, "mode": "telemetry", "interface": "ethernet-1/1", "oper": "up",
                "destination": d.get("name", ""), "collector": f"{d.get('address', '')}:{d.get('port', '')}",
                "path": TELEMETRY_NEED.sensor_paths[0], "installed": bool(dests),
            }
            emit({"kind": "device", "domain": "network", "state": state,
                  "title": "telemetry export configured",
                  "detail": f"grpc-tunnel destination {d.get('name', '')} → {d.get('address', '')}:{d.get('port', '')} · written to srl1",
                  "t": _now_ms()})

    def _emit_teardown(self, eid: int, sid: str, emit: Emit) -> None:
        # The controller's watcher already tore the session down; observe the result.
        if not self.provisioner:
            emit(_ev("device", "network", "Router offline", "no live enforcement to remove"))
            return
        if self.last_service == "telemetry":
            state = {"online": True, "mode": "telemetry", "interface": "ethernet-1/1",
                     "oper": "up", "installed": bool(self.provisioner.telemetry_config("srl1")),
                     "destination": "", "collector": "", "path": TELEMETRY_NEED.sensor_paths[0]}
            emit({"kind": "device", "domain": "network", "state": state,
                  "title": "telemetry export removed",
                  "detail": "grpc-tunnel destination deleted from srl1 — access withdrawn",
                  "t": _now_ms()})
            return
        _shim()
        emit(_device(self.device_state()))
        emit(_iperf_ev(_iperf(), shaped=False))

    def device_state(self) -> dict:
        """srl1's live policer + interface oper-state (real gNMI), or offline."""
        if not self.provisioner:
            return {"online": False}
        client = self.provisioner._client("srl1")
        oper = client.get(path=[paths.interface_oper_state("ethernet-1/1")], encoding="json_ietf")
        oper_state = oper["notification"][0]["update"][0]["val"]
        templates = client.get(path=[paths.QOS_POLICER_TEMPLATES], encoding="json_ietf", datatype="config")
        policers = []
        for update in templates["notification"][0].get("update") or []:
            for t in _denamespace(update["val"] or {}).get("policer-template", []):
                if t.get("name", "").startswith("a2a-"):
                    p = t["policer"][0]
                    policers.append({"name": t["name"], "peak_kbps": p["peak-rate-kbps"]})
        return {"online": True, "interface": "ethernet-1/1", "oper": oper_state, "policers": policers}


# --- event constructors (the wire shape the UI reads) -----------------------


def _ev(kind: str, domain: str, title: str, detail: str = "") -> dict:
    return {"kind": kind, "domain": domain, "title": title, "detail": detail, "t": _now_ms()}


def _chat(who: str, text: str) -> dict:
    return {"kind": "chat", "domain": "agent", "who": who, "title": who, "detail": text, "t": _now_ms()}


# --- intent: turn a plain-language request into what Ada should buy ----------
# Two products, and the console makes the distinction the whole point:
#   bandwidth  → a guaranteed rate the router holds for you (a policer)
#   telemetry  → the RIGHT to configure telemetry export on the device (a dial-out dest)

_BANDWIDTH = {
    "service": "bandwidth", "label": "a 50 Mbps bandwidth guarantee",
    "why": "A committed rate the router holds for you through the window.",
}
_TELEMETRY = {
    "service": "telemetry", "label": "the right to configure telemetry export on srl1",
    "why": "The ticket lets the controller write a telemetry-export config onto the router for you.",
}


def _parse_intent(text: str) -> dict:
    return _llm_intent(text) or _keyword_intent(text)


def _keyword_intent(text: str) -> dict:
    import re

    t = text.lower()
    telemetry = any(k in t for k in
                    ("telemetr", "monitor", "stats", "counter", "export", "subscri", "observ", "config the", "configure telem"))
    base = dict(_TELEMETRY if telemetry else _BANDWIDTH)
    budget = 15
    m = re.search(r"(\d+)\s*(tok|token)", t)
    if m:
        budget = int(m.group(1))
    elif "budget" in t:
        nums = re.findall(r"\d+", t.split("budget", 1)[1])
        if nums:
            budget = int(nums[0])
    base["budget"] = budget
    return base


def _llm_intent(text: str) -> dict | None:
    """The real-agent path: an LLM reads the request and picks the product. Opt-in
    (A2A_CHAT_LLM=1) because local models on a small box answer too slowly to feel like
    chat; the deterministic parse stands in by default with the same result."""
    import os

    if os.environ.get("A2A_CHAT_LLM") != "1":
        return None
    try:
        from agents.llm import LLMClient, ollama_up
        from pydantic import BaseModel

        if not ollama_up():
            return None

        class Intent(BaseModel):
            service: str  # "bandwidth" or "telemetry"
            budget_tok: int
            reasoning: str

        out = LLMClient().structured(
            system=("You route a network-buyer's request to ONE product. bandwidth = a "
                    "guaranteed data rate through the router. telemetry = the right to "
                    "configure the router to export monitoring to a collector. Pick a "
                    "budget in TOK (default 15). Reply as the schema."),
            user=text, schema=Intent,
        )
        base = dict(_TELEMETRY if out.service == "telemetry" else _BANDWIDTH)
        base["budget"] = out.budget_tok or 15
        base["why"] = out.reasoning or base["why"]
        return base
    except Exception:  # noqa: BLE001 — any failure falls back to the deterministic parse
        return None


def _stage(domain: str, label: str) -> dict:
    return {"kind": "stage", "domain": domain, "title": label, "t": _now_ms()}


def _a2a(frm: str, to: str, skill: str, summary: str, expand: dict | None = None) -> dict:
    return {"kind": "a2a", "domain": "agent", "frm": frm, "to": to, "skill": skill,
            "title": f"{frm} → {to}", "detail": f"{skill} · {summary}", "expand": expand,
            "t": _now_ms()}


def _mcp(agent: str, server: str, tool: str, args: str, result: str,
         expand: dict | None = None) -> dict:
    return {"kind": "mcp", "domain": "agent", "agent": agent, "server": server, "tool": tool,
            "title": f"{agent} · {server}.{tool}", "detail": f"{args} → {result}",
            "expand": expand, "t": _now_ms()}


def _clip(d: dict, keep: int = 10) -> dict:
    """Trim long hex blobs so an expanded payload stays readable in the UI."""
    out = {}
    for k, v in list(d.items())[:keep]:
        if isinstance(v, str) and v.startswith("0x") and len(v) > 26:
            v = v[:22] + "…"
        out[k] = v
    return out


def _a2a_out(service: str, need) -> dict:
    """The real A2A message body Ada would POST to Bell's agent-card endpoint."""
    from agents.a2a_adapter import encode_need

    port = 9101 if service == "bandwidth" else 9102
    return {"endpoint": f"http://localhost:{port}/.well-known/agent-card.json",
            "skill": f"quote_{service}", "transport": "A2A message → DataPart (JSON)",
            "body": json.loads(encode_need(need))}


def _a2a_reply(offer) -> dict:
    from agents.a2a_adapter import encode_offer_or_decline

    body = json.loads(encode_offer_or_decline(offer))
    if isinstance(body.get("offer"), dict):
        body["offer"] = _clip(body["offer"])
    body = _clip(body)
    return {"endpoint": "reply on the same A2A task", "transport": "A2A message → DataPart (JSON)",
            "body": body}


def _decision(agent: str, accept: bool, reason: str) -> dict:
    return {"kind": "decision", "domain": "agent", "agent": agent, "accept": accept,
            "title": f"{agent} decides: {'accept' if accept else 'decline'}", "detail": reason,
            "t": _now_ms()}


def _chain_tx(method: str, tx_hash: str, block: int, summary: str, break_signal: bool = False,
              expand: dict | None = None) -> dict:
    return {"kind": "chain_tx", "domain": "chain", "method": method, "tx_hash": tx_hash,
            "block": block, "break_signal": break_signal, "title": f"tx · {method}",
            "detail": f"{summary}  ·  {tx_hash[:18]}…  block {block}", "expand": expand,
            "t": _now_ms()}


def _ticket(view: dict) -> dict:
    return {"kind": "ticket", "domain": "chain", "state": view,
            "title": f"ticket #{view['id']}", "detail": view["name"], "t": _now_ms()}


def _chain_read(what: str, value: str) -> dict:
    return {"kind": "chain_read", "domain": "chain", "title": what, "detail": str(value),
            "t": _now_ms()}


def _predicate(checks: list[dict]) -> dict:
    passed = sum(c["ok"] for c in checks)
    return {"kind": "predicate", "domain": "controller", "checks": checks,
            "title": f"predicate {passed}/{len(checks)}",
            "detail": " · ".join(f"{c['name']}{'✓' if c['ok'] else '✗'}" for c in checks),
            "t": _now_ms()}


def _device(state: dict) -> dict:
    if not state.get("online"):
        detail = "router offline"
    elif state.get("policers"):
        p = state["policers"][0]
        detail = f"policer {p['name']} · {p['peak_kbps'] // 1000} Mbps · oper {state.get('oper')}"
    else:
        detail = f"no policer · oper {state.get('oper')} — config read live off the router"
    return {"kind": "device", "domain": "network", "state": state,
            "title": "srl1 config", "detail": detail, "t": _now_ms()}


def _iperf_ev(m: dict, shaped: bool) -> dict:
    return {"kind": "iperf", "domain": "network", "shaped": shaped, **m,
            "title": "iperf3 hostA→hostB",
            "detail": f"offered 100 Mbps → {m['received_mbps']:.0f} Mbps received"
                      f"{' (policed)' if shaped else ' (unshaped)'}", "t": _now_ms()}


def _done(ok: bool, summary: str) -> dict:
    return {"kind": "done", "domain": "controller", "ok": ok, "title": "done", "detail": summary,
            "t": _now_ms()}


# --- small helpers ----------------------------------------------------------


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _client(name: str, anvil) -> ChainClient:
    return ChainClient(anvil.rpc_url, ANVIL_KEYS[name], deployment=anvil.deployment, poll_interval=0.3)


def _defunct(text: str):
    from eth_account.messages import encode_defunct

    return encode_defunct(text=text)


def _need_for(service: str):
    from a2a_interfaces.fixtures import BANDWIDTH_NEED

    return BANDWIDTH_NEED if service == "bandwidth" else TELEMETRY_NEED


def _mbps(need) -> str:
    return f"{getattr(need, 'capacity_bps', 0) // 1_000_000} Mbps" if hasattr(need, "capacity_bps") else "10 s samples"


def _hm(ts: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%H:%M")


def _predicate_checks(view, now: int, owner: str) -> list[dict]:
    return [
        {"name": "owner", "ok": True},
        {"name": "started", "ok": now >= view.start_time},
        {"name": "not-expired", "ok": now < view.end_time},
        {"name": "not-revoked", "ok": not view.revoked},
        {"name": "in-scope", "ok": view.service_type in (0, 1)},
        {"name": "no-conflict", "ok": True},
    ]


def _telemetry_offer(bell: ChainClient, nonce: int, collector_endpoint: str) -> object:
    params = eth_abi.encode(
        ["string[]", "string", "uint32"],
        [TELEMETRY_NEED.sensor_paths, collector_endpoint, TELEMETRY_NEED.sample_interval_s],
    )
    offer = Offer(
        provider=BELL,
        consumer="0x" + "0" * 40,
        service_type=1,
        resource_id=TELEMETRY_RESOURCE_ID,
        params="0x" + params.hex(),
        start_time=WINDOW.start,
        end_time=WINDOW.end,
        payment_token=MOCK_TOK,
        price=str(8 * 10**18),
        valid_until=WINDOW.end,
        salt="0x" + f"{0x7E000 + nonce:064x}",
        terms_hash=TERMS_HASH,
    )
    return bell.sign_offer(offer)


def _shim() -> None:
    from pathlib import Path

    shim = Path(__file__).resolve().parents[4] / "netlab" / "mirror-policer-to-tc.sh"
    subprocess.run([str(shim)], capture_output=True)


def _iperf() -> dict:
    subprocess.run(["docker", "exec", "-d", "clab-a2a-hostB", "iperf3", "-s", "-p", "5401", "-1"],
                   check=False)
    out = subprocess.run(
        ["docker", "exec", "clab-a2a-hostA", "iperf3", "-c", "10.10.2.10", "-p", "5401",
         "-t", "3", "-u", "-b", "100M", "--json"],
        capture_output=True, text=True,
    ).stdout
    try:
        s = json.loads(out)["end"]["sum"]
        return {"received_mbps": s["bits_per_second"] * (1 - s["lost_percent"] / 100) / 1e6,
                "loss_pct": s["lost_percent"]}
    except Exception:
        return {"received_mbps": 0.0, "loss_pct": 0.0}


# bind the offer builder onto Console (needs bell + a per-click nonce for a fresh salt)
def _console_offer_for(self: Console, service: str, nonce: int):
    if service == "bandwidth":
        offer = CANONICAL_OFFER.model_copy(update={"salt": "0x" + f"{0x5A000 + nonce:064x}"})
        return self.bell.sign_offer(offer)
    # telemetry: the offer names Ada's collector; the ticket buys the right to write a
    # gNMI export destination to the router pointing there (ADR-007).
    return _telemetry_offer(self.bell, nonce, TELEMETRY_NEED.collector_endpoint)


Console._offer_for = _console_offer_for
