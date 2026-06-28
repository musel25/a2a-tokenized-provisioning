"""Walking skeleton v0 — the whole play with cardboard props (M0.3).

Cardboard props (fakes) that satisfy the M0.2 ports, a stub controller that holds
the naive authorization predicate, and scripted agents. The lifecycle tests in
e2e/tests/ drive these end to end; CI runs them forever after.

Nothing here is real: no signatures, no keccak, no web3, no gNMI. The fakes are
deliberately dumb — they prove the architecture's joints, not any component's muscle
(docs/00-the-story.md "the walking skeleton"). Real organs replace them one phase at
a time: FakeChain → chainmcp (M1.5), FakeNet → netctl (M3.4), StubController →
controller (M4.x), scripted_agents → LLM agents (M5.6).
"""
