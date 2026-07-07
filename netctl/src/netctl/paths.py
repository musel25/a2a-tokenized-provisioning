"""Every YANG path netctl touches, in one file — the M3.1 explain-back made real.

Paths are stringly-typed and silently version-dependent: a typo'd or renamed path
doesn't fail loudly, it just matches nothing. Keeping them here means one place to
diff against the router's schema when SR Linux upgrades, and zero copies drifting
inside function bodies. Derived from the M2.2/M2.3 recipes (docs/07 §6–§7).
"""

from __future__ import annotations

# --- QoS policer (the bandwidth product, docs/07 §6.1) -----------------------

QOS_POLICER_TEMPLATES = "/qos/policer-templates"
QOS_INTERFACES = "/qos/interfaces"


def policer_template(name: str) -> str:
    return f"/qos/policer-templates/policer-template[name={name}]"


def qos_interface(subinterface: str) -> str:
    """The attachment point; `subinterface` is e.g. "ethernet-1/1.0"."""
    return f"/qos/interfaces/interface[interface-id={subinterface}]"


# --- telemetry export config (the right the telemetry ticket buys, ADR-007) --
# SR Linux's gNMI dial-out: configure the router to export toward a collector. Writing
# this IS honoring the telemetry ticket — symmetric with installing a policer.

TELEMETRY_DESTINATIONS = "/system/grpc-tunnel"


def telemetry_destination(name: str) -> str:
    return f"/system/grpc-tunnel/destination[name={name}]"


# --- interface state / telemetry (docs/07 §7) --------------------------------


def interface_statistics(interface: str) -> str:
    return f"/interface[name={interface}]/statistics"


def interface_oper_state(interface: str) -> str:
    return f"/interface[name={interface}]/oper-state"
