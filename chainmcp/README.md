# chainmcp — Ada's & Bell's banking app

Chain adapter + signing + MCP server. **The only package that ever holds a private key**
(hard rule #2). Implements the `EntitlementReader` port; signs EIP-712 offers and
activation proofs; submits `fulfill`.

- Arrives: M1.5 (client), M5.4 (MCP server)
- May depend on: `interfaces`, `contracts` ABI
