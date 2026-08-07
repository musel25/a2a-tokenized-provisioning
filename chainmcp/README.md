# chainmcp — Ada's & Bell's banking app

Chain adapter + signing. **The only package that ever holds a private key**
(hard rule #2). One `ChainClient` per identity: it satisfies the `EntitlementReader`
port (docs/03 §4), signs EIP-712 offers and EIP-191 activation proofs, and submits
`approve`+`fulfill` — callers see addresses and signatures, never the key.

- Shipped: **M1.5** — client, signing, the cross-stack signature tests, and
  `chainmcp.testing` (throwaway Anvil + deploy for tests/notebooks).
- Still to come: the MCP server wrapper (M5.4).
- May depend on: `interfaces`, `contracts` ABI (loaded from `contracts/out/`, never
  copy-pasted).

```sh
uv run pytest chainmcp/               # incl. Python-signs / Solidity-verifies, on live Anvil
```

**Hands-on tour:** course chapters [`03`](../e2e/notebooks/course/03_the_atomic_swap.ipynb)
and [`04`](../e2e/notebooks/course/04_signatures_that_contracts_believe.ipynb) — build the
atomic swap and the EIP-712 signatures from zero, then drive this client against them.
