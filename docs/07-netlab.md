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

## 6. Bandwidth, by hand (M2.2) — *lands with M2.2*

## 7. Telemetry, by hand (M2.3) — *lands with M2.3*

---

## Appendix: gotchas met so far (each cost real minutes)

- **SR Linux boots slow and silent** — ~40 s before `sr_cli` answers; the `exec` config
  replay only works because containerlab waits for the node's health check first.
- **`startup-config:` + sudoless containerlab = unconfigured router** (§4). Symptom:
  every port `admin-state disable`, pings time out, no error anywhere on the console.
- **A freshly committed config needs a beat** — the first ping after `commit now` can
  lose its lead packets to ARP; measure after a warm-up, not across it.
- **This machine had a zombie lab** (`clab-bandwidth-poc-*`, its source repo deleted,
  SRL nodes dead for 2 months) holding RAM; `docker rm -f` of the leftovers freed it.
  `containerlab inspect --all` shows what's really running before you deploy.
