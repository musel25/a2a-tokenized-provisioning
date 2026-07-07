# 07 — netlab: the miniature internet, and how to drive it by hand

> **Status:** living — the deliverable of Phase 2. Every recipe here was derived on the
> real CLI and captured verbatim; if a recipe and the lab disagree, the lab is right and
> this file gets fixed. **Companions:** `netlab/topology.clab.yml` (the lab itself) ·
> story ch. 6 (why a flight simulator) · `docs/01` Phase 2 (the milestone map).
>
> Grown by: **M2.1** (topology + this file) · M2.2 (the bandwidth recipe) · M2.3 (the
> telemetry recipe).

---

## 1. Why this lab exists (and why we drive it by hand first)

Everything before Phase 2 traded *promises about* bandwidth — the ticket, the payment,
the signature. None of it touched a router. This lab is where promises become physics:
one real (containerized) **Nokia SR Linux** router between two Linux hosts, so that
"Ada bought 50 Mbps" can eventually mean *this iperf3 stream plateaus at 50 Mbps*.

The recipes are derived **manually before any automation** because you cannot automate a
device you cannot drive: M3.x's `netctl` will replay, over gNMI, exactly the changes we
first make by hand here — and when it misbehaves, this file is what you debug against.

## 2. The topology (M2.1)

```
hostA ──eth1───e1-1┐            ┌e1-2───eth1── hostB
10.10.1.10/24      │    srl1    │      10.10.2.10/24
                   │ 10.10.1.1  │
                   │ 10.10.2.1  │
                   └────────────┘
```

Two /24s, one router. hostA→hostB traffic **must transit srl1** — that transit is the
whole point: it's the choke point where M2.2's policer will squeeze and where M2.3's
counters tick.

| Node | Image | Address | Role |
|---|---|---|---|
| srl1 | `ghcr.io/nokia/srlinux` | e1-1 `10.10.1.1/24` · e1-2 `10.10.2.1/24` | the provider's router — the thing Ada's ticket buys a slice of |
| hostA | `ghcr.io/hellt/network-multitool` | eth1 `10.10.1.10/24`, gw `.1` | Ada's side (iperf3 client) |
| hostB | same | eth1 `10.10.2.10/24`, gw `.1` | the far end (iperf3 server) |

Hosts get static routes to the far /24 via srl1 (`exec` lines in the topology file).

## 3. Bring-up and tear-down

```sh
containerlab deploy  -t netlab/topology.clab.yml     # ~1 min: SR Linux takes ~40 s to boot
containerlab inspect -t netlab/topology.clab.yml     # all three nodes "running"
containerlab destroy -t netlab/topology.clab.yml --cleanup
```

No sudo on this machine: the containerlab binary is SUID and the user is in
`clab_admins` + `docker`. (Anywhere else, prefix with sudo.)

**Verify the data path** (the M2.1 acceptance test — real output):

```sh
$ docker exec clab-a2a-hostA ping -c 4 10.10.2.10
4 packets transmitted, 4 received, 0% packet loss
$ docker exec clab-a2a-hostA traceroute -n 10.10.2.10
 1  10.10.1.1    0.75 ms      ← the packet really visits srl1
 2  10.10.2.10   0.05 ms
```

## 4. srl1's base config — what it is and how it's applied

`netlab/srl1-init.cli` holds the minimum for a ping and *nothing else* (no QoS, no
telemetry — a provisioner can't prove it provisions if the config is pre-baked):

- both interfaces + subinterface 0 admin-enabled, IPv4 enabled and addressed;
- both subinterfaces attached to the `default` network-instance (SR Linux's name for a
  routing table; interfaces don't route until they're in one).

**How it's applied — and the trap we hit.** Containerlab's `startup-config:` for SR
Linux fails on this machine's sudoless (SUID) install: the post-deploy overlay task dies
with `/tmp/clab-overlay-config: No such file or directory` and the router boots
unconfigured — interfaces admin-down, silent. The topology therefore mounts the CLI file
and replays it after boot instead:

```yaml
binds: [srl1-init.cli:/tmp/srl1-init.cli:ro]
exec:  [bash -c '{ echo "enter candidate"; grep -v "^#" /tmp/srl1-init.cli; echo "commit now"; } | sr_cli']
```

Same effect, sturdier plumbing, and it teaches the real thing anyway: SR Linux config
changes are **transactional** — you edit a *candidate* config and `commit` it (the
model gNMI Set will use too, M3.x).

## 5. Driving srl1 by hand — the survival kit

```sh
docker exec -it clab-a2a-srl1 sr_cli          # interactive CLI (or: ssh admin@clab-a2a-srl1)
```

Inside (the five commands worth knowing before M2.2):

```
show interface brief                          # admin/oper state of every port
show interface ethernet-1/1                   # one port, with addresses
show network-instance default route-table     # the routing table
enter candidate                               # begin a transaction...
  set / interface ethernet-1/1 description "hello"
commit now                                    # ...apply it (or: discard now)
info from state interface ethernet-1/1        # the STATE tree (what gNMI reads)
```

Default credentials `admin` / `NokiaSrl1!` (SSH; the docker-exec path skips auth).

## 6. Bandwidth, by hand (M2.2): the policer, and the lab's missing ASIC

**The goal:** make "Ada bought 50 Mbps" physically true — an iperf3 stream from hostA
that plateaus at ≈ 50 Mbps *because the router says so*.

### 6.1 The recipe (what M3.2's `apply_bandwidth` will replay over gNMI)

Two `set` groups: a **policer template** (the rate) and its **attachment** to the
customer-facing subinterface's input (the edge where Ada's traffic enters the provider's
network — you police at the border, not in the core):

```
enter candidate
set / qos policer-templates policer-template police-50m policer 1 \
      peak-rate-kbps 50000 committed-rate-kbps 50000 \
      maximum-burst-size 125000 committed-burst-size 125000 violate-action drop
set / qos interfaces interface ethernet-1/1.0 interface-ref interface ethernet-1/1
set / qos interfaces interface ethernet-1/1.0 interface-ref subinterface 0
set / qos interfaces interface ethernet-1/1.0 input policer-templates policer-template police-50m
commit now
```

Undo (teardown — M3.2 needs this idempotent):

```
enter candidate
delete / qos interfaces interface ethernet-1/1.0
delete / qos policer-templates policer-template police-50m
commit now
```

**The trap that cost the most time:** attaching with only the list key —
`set / qos interfaces interface ethernet-1/1.0 input policer-templates …` — fails with
the (misspelled, misleading) error *"Attachment of policier-templates, not permitted for
interfaces"*. That is not a platform restriction: the YANG `must` demands the
`interface-ref { interface, subinterface }` leaves be populated; the list key alone
isn't enough. Two extra `set` lines fix it. (Found by grepping the image's YANG:
`srl_nokia-acl-policers.yang`.)

### 6.2 The discovery: the container accepts the config but doesn't enforce it

With the policer committed, a 100 Mbit/s UDP blast sailed through untouched:

```
$ docker exec clab-a2a-hostA iperf3 -c 10.10.2.10 -u -b 100M
[  5]  0.00-8.04 sec  95.4 MBytes  99.5 Mbits/sec  0/69053 (0%)   receiver   ← no drops!
```

Systematic narrowing (all measured, in order):

| Probe | Result | Meaning |
|---|---|---|
| `info from state …policer 1` | `peak-rate-kbps 0` | the datapath zeroes policer *state* — it never programmed it |
| ACL entry `action drop` (icmp) | ping 100 % loss | the XDP datapath **does** enforce ACL match+drop |
| ACL `action accept rate-limit policer` | UDP untouched | …but not rate-limiting |
| `tc` ingress police on e1-1 (in srl1's netns) | UDP untouched | XDP grabs RX *before* tc-ingress |
| **`tc tbf` egress on e1-2 (in srl1's netns)** | **UDP → 48.5 Mbps** | TX goes through the qdisc — enforcement! |

Conclusion: containerized SR Linux is a **control-plane simulator** here — it can deny,
but it cannot rate-limit. The real ASIC's half of the policer doesn't exist in the
container.

### 6.3 The adaptation (ADR-006): mirror the committed config into `tc`

The gNMI-written policer config **stays the single source of truth** — the controller
and netctl never learn about any of this (rule 6 intact). A small piece of *lab
infrastructure*, [`netlab/mirror-policer-to-tc.sh`](../netlab/mirror-policer-to-tc.sh),
plays the missing ASIC: it reads the router's *running config* (not state — see above)
and applies/removes an equivalent `tc tbf` shaper **inside srl1's own netns**, so the
limiting still physically happens at the router. Ingress policer on `e1-1.0` maps to
egress tbf on `e1-2` (equivalent for hostA→hostB through a two-port router; tc-ingress
is XDP-shadowed).

```sh
./netlab/mirror-policer-to-tc.sh        # run after every policer config change (M2.2);
                                        # M3.2's lab fixture loops it
```

### 6.4 The evidence (real runs, MTU already fixed at 1500 — see Appendix)

```
BEFORE (no policer):
  TCP:            75.6 Mbits/sec receiver        (CPU-bound datapath ceiling; varies 55–75)
  UDP offered 100M: 99.5 Mbits/sec receiver, 0 % loss

AFTER (policer committed + shim tick):
  TCP:            47.7 Mbits/sec receiver        ← the plateau
  UDP offered 100M: 48.5 Mbits/sec receiver, 51 % dropped at srl1

DETACH (delete attachment + shim tick):
  TCP back to the unshaped ceiling (56.0 this run)
```

**Explain-back seed** (docs/01 M2.2): the policer acts at the *ingress edge* —
`ethernet-1/1.0 input` — because that's where the customer's traffic enters the
provider's domain; policing in the core would waste the core's capacity carrying
packets you intend to drop. (In the shim it's *materialized* on the egress port — a
lab-only displacement with identical effect for this topology.)

## 7. Telemetry, by hand (M2.3): gNMI's third verb, seen raw

Chapter 6's product was a *limit*; chapter 7's product is a *stream* — the same router,
asked to narrate its own counters. gNMI has three verbs: **Get** (read once), **Set**
(change config — M3.x's whole job), and **Subscribe** (push me updates). This section
drives the first and third by hand; Set waits for M3.1 so each new tool lands alone.

### 7.1 Install gnmic (no sudo: user-local binary)

```sh
mkdir -p ~/.local/bin      # on PATH
VER=$(curl -s https://api.github.com/repos/openconfig/gnmic/releases/latest | jq -r .tag_name)
curl -sL "https://github.com/openconfig/gnmic/releases/download/${VER}/gnmic_${VER#v}_Linux_x86_64.tar.gz" \
  | tar -xz -C ~/.local/bin gnmic
gnmic version          # 0.46.0 at time of writing
```

### 7.2 Talk to srl1 (and the two gotchas)

Containerlab enables SR Linux's gNMI server on `:57400` with a **self-signed TLS cert**;
`--skip-verify` accepts it. That's fine for a lab and a one-line honesty note: in any
real deployment you'd pin the CA (containerlab even generates one per lab). Credentials
are the SR Linux defaults `admin` / `NokiaSrl1!`.

```sh
gnmic -a clab-a2a-srl1:57400 -u admin -p 'NokiaSrl1!' --skip-verify capabilities | head -2
# gNMI version: 0.10.0
```

Gotcha #2: **SR Linux rejects gnmic's default encoding** (`rpc error: … received
encoding: 0`) — always pass `-e json_ietf`. (M3.1's pygnmi needs the same.)

```sh
gnmic -a clab-a2a-srl1:57400 -u admin -p 'NokiaSrl1!' --skip-verify -e json_ietf \
  get --path "/interface[name=ethernet-1/1]/oper-state"
# "srl_nokia-interfaces:interface/oper-state": "up"
```

### 7.3 The subscription (the M2.3 acceptance test — real output)

With iperf3 running hostA→hostB, subscribe to the ingress interface's statistics,
sampled every 10 s:

```sh
gnmic -a clab-a2a-srl1:57400 -u admin -p 'NokiaSrl1!' --skip-verify -e json_ietf \
  subscribe --path "/interface[name=ethernet-1/1]/statistics" \
  --mode stream --stream-mode sample --sample-interval 10s
```
```
"time": "2026-07-07T04:37:03"   in-octets: 761761034
"time": "2026-07-07T04:37:13"   in-octets: 832824572     ← +71,063,538 bytes
"time": "2026-07-07T04:37:23"   in-octets: 904751684     ← +71,927,112
"time": "2026-07-07T04:37:33"   in-octets: 975849124     ← +71,097,440
```

Do the arithmetic the collector (M3.3) will do forever: `(832824572 − 761761034) × 8
/ 10 s = 56.9 Mbit/s` — the samples *are* the iperf stream, reconstructed from two
counter reads. That derivative-of-a-counter is the entire telemetry product Ada buys
in chapter 7.

Note what "sampling" means here — the router pushes on ITS schedule
(`sample-interval`), not per request; and the connection is **dial-in** (the collector
connects to the router), which is exactly the delivery-model question ADR-007 must
answer for `apply_telemetry` (M3.3).


---

## Appendix: gotchas met so far (each cost real minutes)

- **SR Linux boots slow and silent** — ~40 s before `sr_cli` answers; the `exec` config
  replay only works because containerlab waits for the node's health check first.
- **`startup-config:` + sudoless containerlab = unconfigured router** (§4). Symptom:
  every port `admin-state disable`, pings time out, no error anywhere on the console.
- **A freshly committed config needs a beat** — the first ping after `commit now` can
  lose its lead packets to ARP; measure after a warm-up, not across it.
- **pygnmi + self-signed TLS = silent timeout** (M3.1): the router's cert is a
  self-signed leaf (`CN=srl1` — the lab CA never reaches the node, same sudoless-overlay
  breakage as §4), and pygnmi's `skipverify` still verifies underneath →
  `CERTIFICATE_VERIFY_FAILED` surfacing as a bare `FutureTimeoutError`. Recipe: fetch
  the leaf (`ssl.get_server_certificate`), pass it as `path_root` (self-signed = its own
  CA), and `override="srl1"` — the cert's OWN SAN, not the container hostname
  (`netctl/src/netctl/gnmi_smoke.py` implements it).
- **The lab's /etc/hosts entries are IPv6-only** and python-grpc won't dial them; ask
  docker for the node's IPv4 (`docker inspect … .Networks.clab.IPAddress`). gnmic (Go)
  happily used IPv6, which is why M2.3 never noticed.
- **This machine had a zombie lab** (`clab-bandwidth-poc-*`, its source repo deleted,
  SRL nodes dead for 2 months) holding RAM; `docker rm -f` of the leftovers freed it.
  `containerlab inspect --all` shows what's really running before you deploy.
