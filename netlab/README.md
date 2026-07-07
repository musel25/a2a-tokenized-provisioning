# netlab — the miniature internet

Containerlab topology: one Nokia SR Linux router (`srl1`) between two Linux hosts,
hostA→hostB traffic transiting the router — the choke point where bandwidth is policed
(M2.2) and counted (M2.3). All recipes live in [`docs/07-netlab.md`](../docs/07-netlab.md).

```sh
containerlab deploy -t netlab/topology.clab.yml    # no sudo here: SUID clab + clab_admins
docker exec clab-a2a-hostA ping -c 4 10.10.2.10    # 0% loss, via 10.10.1.1
containerlab destroy -t netlab/topology.clab.yml --cleanup
```

- Shipped: **M2.1** (topology + base config + docs/07); M2.2/M2.3 recipes follow
- Depends on: nothing
