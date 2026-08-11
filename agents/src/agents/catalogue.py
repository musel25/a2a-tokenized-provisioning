"""The provider's product catalogue — per-service knowledge, quarantined (R12).

The agent layer above this file is service-generic: the graphs do control flow, the
ledger does arithmetic, the tools sign and settle — none of them knows what is sold.
Everything that IS service-specific on the provider's side lives in this one table:
how much of the pool a need consumes, the list price the deterministic slot quotes,
which resource an offer names, and how its params serialize for the chain. It is the
agent-layer twin of `controller/translators.py`, which quarantines the same knowledge
on the enforcement side. Selling a third service means adding a row here, a translator
there, and a resource-map entry — nothing above either file changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import eth_abi

from a2a_interfaces.fixtures import RESOURCE_ID, TELEMETRY_RESOURCE_ID


@dataclass(frozen=True)
class ServiceDesc:
    """One sellable product: everything the generic machinery must look up by kind."""

    kind: str
    service_type: int  # the on-chain enum (0 = bandwidth, 1 = telemetry)
    list_price_tok: int  # what the deterministic quote slot charges
    pool: int  # the resource pool the ledger guards, in `demand` units
    demand: Callable[[Any], int]  # need -> units this sale would reserve
    fmt: Callable[[int], str]  # units -> human-readable, for transcripts
    resource_id: str  # the resource an offer for this product names
    encode_params: Callable[[Any], str]  # need -> 0x-hex ABI params blob


def _bandwidth_params(need: Any) -> str:
    # ABI encoding of (uint64 capacityBps, uint8 qosClass): two right-aligned words.
    return "0x" + f"{need.capacity_bps:064x}" + f"{need.qos_class:064x}"


def _telemetry_params(need: Any) -> str:
    return "0x" + eth_abi.encode(
        ["string[]", "string", "uint32"],
        [list(need.sensor_paths), need.collector_endpoint, need.sample_interval_s],
    ).hex()


CATALOGUE: dict[str, ServiceDesc] = {
    "bandwidth": ServiceDesc(
        kind="bandwidth",
        service_type=0,
        list_price_tok=10,
        pool=1_000_000_000,  # the 1 Gbps line rate of the sold port
        demand=lambda need: need.capacity_bps,
        fmt=lambda n: f"{n // 1_000_000} Mbps",
        resource_id=RESOURCE_ID,
        encode_params=_bandwidth_params,
    ),
    "telemetry": ServiceDesc(
        kind="telemetry",
        service_type=1,
        list_price_tok=8,
        pool=8,  # collector destinations the provider will configure at once
        demand=lambda need: 1,  # one subscription = one destination slot
        fmt=lambda n: f"{n} collector slot" + ("s" if n != 1 else ""),
        resource_id=TELEMETRY_RESOURCE_ID,
        encode_params=_telemetry_params,
    ),
}


def service_for(kind: str) -> ServiceDesc:
    return CATALOGUE[kind]
