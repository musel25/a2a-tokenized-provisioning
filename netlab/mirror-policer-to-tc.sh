#!/usr/bin/env bash
# The lab's missing ASIC (ADR-006): containerized SR Linux ACCEPTS QoS policer config
# but its XDP datapath doesn't enforce it (and zeroes the policer's state). This script
# is one "hardware tick": read the router's COMMITTED policer config and materialize it
# as a tc shaper inside the router's own netns — so enforcement still happens at srl1,
# where the real ASIC would do it, and the gNMI-written config stays the single source
# of truth. No policer attached ⇒ shaper removed (idempotent both ways, rule 8).
#
# Mapping note: the config attaches an INGRESS policer to ethernet-1/1.0; the shaper is
# EGRESS tbf on e1-2, because tc-ingress on e1-1 sits behind XDP and never sees the
# packets (measured — docs/07 §6). For this two-port router and hostA→hostB flows the
# two are equivalent.
#
# M2.2 runs this by hand after each config change; M3.2's lab fixture loops it.
set -euo pipefail

NODE=${NODE:-clab-a2a-srl1}
EGRESS_IF=${EGRESS_IF:-e1-2}

# "info from running", not "from state": the unenforcing datapath reports rate 0 in state.
rate_kbps=$(docker exec "$NODE" sr_cli "info from running /qos policer-templates" 2>/dev/null |
    awk '/peak-rate-kbps/ {print $2; exit}')
attached=$(docker exec "$NODE" sr_cli "info from running /qos interfaces" 2>/dev/null |
    grep -c "policer-template" || true)

if [[ -n "${rate_kbps:-}" && "$attached" -gt 0 ]]; then
    docker exec "$NODE" tc qdisc replace dev "$EGRESS_IF" root \
        tbf rate "${rate_kbps}kbit" burst 125kb latency 50ms
    echo "shim: tbf ${rate_kbps}kbit on ${NODE}/${EGRESS_IF} (mirroring the committed policer)"
else
    docker exec "$NODE" tc qdisc del dev "$EGRESS_IF" root 2>/dev/null || true
    echo "shim: no policer attached — shaper removed"
fi
