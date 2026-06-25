# 00 — The story: the whole project, explained from zero

> **Who this is for.** Someone who can program a little but knows nothing about blockchains
> and nothing about network automation. Every concept is introduced *by the problem it
> solves*, in order, with real numbers. If you can retell any chapter out loud, you own
> that concept.
>
> **How this fits the docs.** This is the narrative twin of the formal documents. Each
> chapter ends with a pointer to its formal version. The design plan lives in `DESIGN.md`;
> the precise schemas live in `docs/03-interfaces.md`.

---

## Prologue — a Tuesday, 13:30

Meet **Ada**. Ada is an AI agent — a program with an LLM for a brain and a crypto wallet
for a hand. At 13:30 her owner's application hands her a job: move a **45 GB dataset**
from `host-A` to `host-B`, finished **before 16:00**.

Ada does the arithmetic. 45 GB in two hours requires a steady **50 megabits per second**
(50 Mbps × 7,200 s = 360 billion bits = 45 GB — exactly). The regular best-effort network
might give her that, or might not, and "might" is not a plan. She needs a *guarantee*:
50 Mbps, on the path A→B, from 14:00 to 16:00.

Meet **Bell**. Bell is also an AI agent. Bell works for a network operator and sells
exactly this: guaranteed bandwidth, by the hour.

In today's world, what happens next involves humans: a sales call, a contract, an account,
an API key arriving by email on Thursday. Ada's deadline is in two and a half hours.

What we want instead: **Ada buys the guarantee from Bell, by herself, in seconds — even
though they have never met and have no reason to trust each other.** And then the network
actually obeys.

That sentence hides two hard problems:

1. **The fair-exchange problem.** How do two strangers trade money for a promise without
   one robbing the other?
2. **The obedient-network problem.** A purchase is just data. How does it become physics —
   actual configured routers?

This whole project is a careful answer to those two questions, twice over (you'll meet the
second service in chapter 7).

---

## Chapter 1 — why strangers can't just pay each other

Try the obvious things first.

**Ada pays first.** She sends Bell 10 TOK (the project's toy currency). Bell now has the
money and... nothing forces him to do anything. He can vanish. Ada has no contract, no
court, no recourse — she's a piece of software.

**Bell delivers first.** He configures the network for Ada's window. Ada gets her transfer
and... nothing forces *her* to pay. Bell burned real capacity for free.

Humans solve this with escrow agents, reputation, and lawyers. All three fail our test:
they're slow, they're human, and they presume a relationship. Strangers' *software* needs a
referee that is fast, automatic, and impossible to sweet-talk.

So make the referee a program — but a program running where? If it runs on Bell's server,
Bell can edit it. On Ada's, Ada can. It must run somewhere **neither of them controls and
both can inspect**.

That place is a **blockchain**: a computer operated by many machines in agreement, where
programs and their data are public, and where deployed code cannot be quietly changed.
A program living there is called a **smart contract**. (For development we run a private,
single-node pretend version on the laptop, called **Anvil** — identical rules, zero cost,
resets on demand.)

The one property we exploit above all others: a blockchain **transaction is atomic** — it
either fully happens or fully doesn't. There is no "the money left but the goods didn't
arrive" state, ever.

Picture a **vending machine**. Coin in, can out, one mechanical motion. You cannot lose
your coin and get nothing; the machine cannot take the coin and refuse the can; and you
cannot argue with it. Our smart contract is a vending machine that sells... what, exactly?

(One honest caveat, planted now and paid off in chapter 8: the machine guarantees the
**swap**, not the **service**. Hold that thought.)

*Formal twin: `DESIGN.md` §1.3, §2.1.*

---

## Chapter 2 — what is Ada actually buying? (the ticket)

First instinct: tokenize *the bandwidth*. Put "50 Mbps" in the machine.

It collapses immediately. Bell's pipe is 1 Gbps of continuous, flowing, divisible stuff.
Bandwidth isn't an object; you can't put it in a box, and there's no meaningful "this
particular 50 Mbps" to hand over.

Second instinct — and the right one: don't sell the stuff, **sell the right**. What Ada
needs isn't ownership of electrons; it's an enforceable claim:

> *up to 50 Mbps · path A→B · 14:00–16:00 today · service class 1 ("the gold lane")*

Think of a **concert ticket**. The ticket is not the concert. Music is as un-ownable as
bandwidth. But *seat 14B, on June 12th, at this venue* is a unique, discrete, ownable
**bundle of terms** — even though "music" is not.

Each such bundle is one of a kind (different capacity, path, window every time), and
one-of-a-kind ownable things have an exact technical match: an **NFT** (the ERC-721
standard). Forget the monkey-JPEG hype. An NFT is a row in a public registry:

> token **#7** exists · its properties are *these* · it belongs to *this address*

— a land registry, not art. In this project the row is called an **entitlement**, and
here is what's printed on Ada's, the moment she buys it:

```
Ticket (entitlement) #7
  issued by : Bell        (0x7099…79C8)
  owner     : Ada         (0xf39F…2266)
  type      : bandwidth   (serviceType 0)
  terms     : up to 50 Mbps · path resource 0xabc… · class 1
  valid     : 14:00 → 16:00   (stored as unix seconds: 1757944800 → 1757952000)
  revoked   : no
  terms doc : committed as hash 0x9f3e…   (chapter 8 explains)
```

One detail that matters more than it looks: those terms live **on the chain itself, in the
contract's storage** — not behind a URL on Bell's web server. A ticket whose fine print
can 404 or be edited overnight is worthless to the gatekeeper who must enforce it. Terms
and ownership must live in the **same tamper-proof place**.

*Formal twin: `DESIGN.md` §2.2, §7.2 · `docs/03-interfaces.md` §4.*

---

## Chapter 3 — a ticket that does work (capability, not receipt)

Suppose chapter 2 is done: Ada paid, ticket #7 is hers. So what? Who tells the routers?

Path one: the ticket is a **receipt** — proof of purchase, nothing more — and Bell
separately emails Ada an API key that *actually* opens the door. Look closely: every
trust problem we just solved comes back, wearing the API key's face. Who guarantees the
key arrives? Arrives only to Ada? Can't be copied, revoked, faked? You'd need to build a
second trust machine to guard the first one's receipt. Infinite regress; autonomy dies.

Path two: **the ticket itself is the key.** The network's gatekeeper authorizes by
checking *on-chain ownership of the token* — nothing else. No account, no email, no prior
relationship. The right travels with the token.

Nightclub version: a screenshot saying "I paid online" is a *receipt* — the bouncer
shrugs. The wristband he physically checks is a *capability*. This project's tickets are
wristbands, and that single design choice is what makes two strangers' agents able to
transact with nothing but cryptography between them. We say the entitlement is
**load-bearing**.

*Formal twin: `DESIGN.md` §2.3.*

---

## Chapter 4 — inside the vending machine

Now build the machine. Four sub-problems, in the order they'd bite you.

**(a) The catalog — Bell can't sit at the counter.** Agents sleep, crash, redeploy. Bell
must be able to put items in the machine *without being online when they sell*. The tool:
a **digital signature**. Bell writes out an offer and signs it with his private key; anyone
can verify, using his public address, that exactly these words came from exactly him —
change one comma and the signature shatters. We sign a *structured form* rather than a
sentence (the **EIP-712** standard: labeled boxes, so signer and machine can never misread
a field). Bell's offer:

```
Offer (signed by Bell, 0x7099…79C8)
  serviceType : 0 (bandwidth)
  resourceId  : 0xabc…           (Bell's opaque name for the A→B path)
  params      : 50 Mbps · class 1
  window      : 14:00 → 16:00
  price       : 10 TOK  (paymentToken 0xTok…)
  validUntil  : 13:50             (a quote, not a standing promise)
  salt        : 0x42…             (this paper's unique serial number)
  termsHash   : 0x9f3e…
```

**(b) The swap — one motion.** Ada decides to buy (her LLM's *only* job here: read the
offer, answer `{"accept": true, "reason": "meets need; within budget"}` — chapter 5 says
why so little). She calls the contract's `fulfill(offer, signature)` with her 10 TOK
approved. In **one transaction** the contract: verifies Bell's signature → checks serial
0x42… unused → marks it used → pulls 10 TOK from Ada → **mints ticket #7 to Ada** →
pushes 10 TOK to Bell. Six effects, one atom. If *any* step fails — wrong signature,
insufficient funds, reused serial — **all six unwind** and the world is exactly as before.
That is the vending machine's clunk.

**(c) The photocopier attack.** Why the serial number? A signature can be copied
perfectly. Without the "mark it used" step, anyone holding Bell's signed offer could feed
it to the machine a hundred times — and Bell, who signed capacity for *one* customer,
would owe a hundred. So the contract keeps a ledger of punched offers — keyed by the hash
of the *whole* offer, with the serial there only to make each offer's hash unique: **every
signed offer is single-use**.

**(d) Two small honesty notes about money and printing.** Money: TOK uses 18 decimals —
"10 TOK" is stored as `10000000000000000000`, because blockchains do exact integer math
only (no floats, no rounding surprises; it's counting in trillionths so fractions never
exist). Printing: tickets are **not pre-printed** and parked in the machine. Minting
happens *at the moment of sale* — Bell's signature is his standing permission to print
those exact terms at that exact price. Which means Bell's *signing policy* is his
inventory control: he signs only what he can honor (chapter 8 returns to this).

*Formal twin: `DESIGN.md` §7 · `docs/03-interfaces.md` §1.4, §2.*

---

## Chapter 5 — the bouncer

14:02. Ada walks up to Bell's **controller** — a deterministic program standing between
the chain-world and the network-world — and says: "Activate ticket #7."

Says who? Over a network, anyone can *claim* to be Ada. Two wrong answers first:

- *Ada sends her private key as proof.* Never. The key **is** her identity; sending it is
  handing over her hand. Keys never travel — in this whole system, Ada's key lives inside
  one component (`chainmcp`) and nothing else ever sees it.
- *Ada sends a pre-signed note: "I, owner of #7, request activation."* Better — but that
  note crosses the network, and bytes get copied. Anyone who saw it can **replay** it
  tomorrow and puppeteer Ada's ticket.

The right answer is a fresh **challenge–response**. The controller throws Ada a random,
never-before-used number (a **nonce**) with a short fuse. Ada signs a message binding
everything together:

```
a2a-activate|bw-ctrl-1|0x5f9c…|7|1757945100
              ^controller  ^nonce  ^ticket  ^proof expiry
```

The controller checks two things: the signature mathematically recovers to whatever
address `ownerOf(7)` returns **on-chain right now**, and the nonce is fresh (then burns
it). A stolen proof is useless — wrong nonce, wrong controller, expired fuse.

Identity settled, the controller runs its entire decision — a five-line checklist called
the **authorization predicate** — against ticket #7 at 14:02:

```
owner is the requester        ✓  (proof recovered Ada, ownerOf(7) = Ada)
not expired                   ✓  (chain time 14:02 ∈ [14:00, 16:00])
not revoked                   ✓  (flag is false)
request within the terms      ✓  (asked: bandwidth; granted: bandwidth)
no conflicting active session ✓  (controller's own ledger)
```

Notice how *boring* that is. Deliberately. **The bouncer is never an LLM.** Brains (LLMs)
decide *whether to buy* — fuzzy, judgment-shaped questions. Rules (plain code) decide
*whether you're allowed in* — arithmetic-shaped questions. A creative bouncer is a
security hole: "I'm totally the owner, trust me 🥺" must bounce off math, not vibes.

All checks green, the controller's **translator** turns paper into physics: it looks up
`0xabc…` in its private map (→ device `srl1`, interfaces `ethernet-1/1` → `ethernet-1/2`)
and instructs the router: *rate-limit to 50,000 kbps, class 1, on that path.* Ticket #7
is now a law of nature on this network.

One clock rules the teardown: at 16:00 the service dies. But whose 16:00? The router's
clock, the controller's, the chain's? They *will* disagree by seconds, and seconds make
heisenbugs. The rule (ADR-004): **chain time is the only clock that decides validity.**
The controller's alarm clock may wake it up; the chain's timestamp decides whether to act.

*Formal twin: `DESIGN.md` §3.1, §7.4, §8 · `docs/03-interfaces.md` §3 · ADR-004, ADR-005.*

---

## Chapter 6 — the hands, and proof it's real

What is "the network" on a student's laptop? **Containerlab** boots **Nokia SR Linux** —
the genuine router operating system that runs on real telecom hardware — inside containers,
with virtual cables between them. A flight simulator loaded with the real cockpit
firmware: fake plane, true instruments.

And how does software talk to a router? The old way is screen-scraping a human CLI —
sending keystrokes, parsing English with regexes, praying. The modern way, and ours, is
**gNMI**: a typed remote control where the router's entire configuration is one big
structured tree, with three verbs — **Get** a value, **Set** a value, **Subscribe** to a
stream of values. (File that third verb away; it becomes a whole product in chapter 7.)
The component that speaks gNMI is `netctl` — pure hands, no brain: it receives "device
`srl1`, rate 50,000 kbps, these interfaces" and never knows tickets or chains exist.

How do you *know* it worked? You measure. `iperf3` blasts traffic from host-A to host-B:

- **before activation:** whatever the unshaped lab gives — hundreds of Mbps or more;
- **after activation:** a flat plateau at **≈ 50 Mbps**.

The moment that graph flattens at 50, ticket #7 stopped being data and became physics.
That number is the project's favorite piece of evidence, and it goes on the dashboard.

*Formal twin: `DESIGN.md` §6.3 · `docs/07-netlab.md` (to come) · `docs/03-interfaces.md` §5.*

---

## Chapter 7 — Tess, and why a second service proves the thesis

Different day, different customer, deliberately unrelated to Ada's transfer (the two demos
are independent on purpose — same pattern, separate stories). A consumer agent runs an
anomaly-detection model and needs **raw measurements**: interface counters from router
`leafA`, sampled every 10 seconds, streamed to its collector at `10.0.0.50:57000`, for two
hours.

The seller is **Tess**, the telemetry provider. And here is the punchline of the entire
project — watch how much of the story you already know:

| Step | Bandwidth (ch. 1–6) | Telemetry (now) |
|---|---|---|
| Discover & quote | signed offer | **same** machinery, different params |
| Decide | LLM yes/no | **same** |
| Pay ↔ ticket, atomically | `fulfill`, mint | **same contract, same function** |
| Prove ownership | challenge–response | **same** |
| Run the checklist | the predicate | **same five lines** |
| Translate to config | rate-limiter via gNMI **Set** | telemetry subscription via gNMI — *different translator* |
| Tear down at `t1` | remove limiter | remove subscription |

The ticket's `serviceType` field is a one-byte switch: `0` routes to the bandwidth
translator, `1` to the telemetry translator. Everything north of that switch — settlement,
ownership, authorization — **never noticed the product changed**. One shapes the data
plane; the other configures the management plane; the machine doesn't care.

That is the thesis, demonstrated rather than claimed: *the settlement layer is
service-agnostic; only the entitlement's terms and the last-mile translation specialize.*

*Formal twin: `DESIGN.md` §4 · `docs/03-interfaces.md` §1.3, §4.2.*

---

## Chapter 8 — what we honestly do not solve

A thesis earns trust by drawing its borders in ink. Here are ours.

**The machine guarantees the exchange, not the service.** Brutal example: Bell can take
Ada's 10 TOK, mint her a perfectly valid ticket #7... and configure nothing. The system
would not notice. Money–for–ticket is **trustless** (the chain enforces it); ticket–for–
actual-Mbps is **assumed** (we trust the provider to honor what it sold). Verifying
delivery would need an agreed-upon referee measuring real throughput — called an
**oracle** — and that is deliberately out of scope. The honest table:

| Guarantee | Status |
|---|---|
| Can't pay twice; ticket can't have two owners | trustless |
| Payment ↔ ticket swapped atomically | trustless |
| A signed offer can't be fulfilled twice | trustless |
| Requester really owns a valid, live ticket | trustless |
| Provider actually delivers the service | **assumed** |
| The promised quality (latency, loss…) is met | **assumed** |

The design's quiet elegance: the **capability model is exactly the cut line**. Everything
about *ownership and authorization* sits on the trustless side; everything about
*fulfillment* sits on the assumed side — which is precisely where a future oracle would
bolt on.

Three more borders, briefly:

- **No negotiation.** Prices are fixed; the LLM answers yes or no. Haggling agents are a
  different thesis.
- **No overselling — by policy, not magic.** Bell has 1 Gbps. If he's already signed away
  950 Mbps for the 14:00–16:00 window, he *declines* the next quote request. His signing
  policy **is** his admission control; remember, minting happens at sale, so signing is
  committing.
- **Revocation and expiry are different animals.** Expiry is *passive*: nobody "turns off"
  ticket #7 at 16:00 — the bouncer simply stops honoring it, like an expired coupon.
  Revocation is *active*: Bell, the issuer, can flip a `revoked` flag (a kill-switch; the
  controller hears the event and tears down mid-session). Which means — say it plainly —
  the ticket is a **revocable credential**, like a season pass the club can cancel under
  its conditions, *not* sovereign property like a gold coin. For a service entitlement,
  that's the appropriate honesty. And about that `termsHash` from chapter 2: the full SLA
  document (latency targets and such) is committed as a fingerprint on-chain — tamper-
  evident for audits — precisely *because* we don't enforce it; the enforceable fields
  live in storage, the aspirational ones live behind a hash.

*Formal twin: `DESIGN.md` §1.4, §2.4, §7.3, §14.*

---

## Chapter 9 — the map of the code, and how it gets built

Eight packages, one job each — you've already met them all as characters:

| Package | Story role | One-line job |
|---|---|---|
| `contracts` | the vending machine | money moves; tickets exist; nowhere else |
| `chainmcp` | Ada's & Bell's banking app | the only holder of keys; signs, pays, reads |
| `netlab` | the miniature internet | real router OS, fake cables |
| `netctl` | the hands | speaks gNMI; knows no tickets |
| `controller` | the bouncer + translator | the checklist; terms → config |
| `agents` | the brains | LLM judgment at exactly two decision points |
| `interfaces` | the treaty | the schemas every border agrees on |
| `e2e` | the stage | brings it all up; tests the play; the dashboard |

Two construction ideas keep a solo project alive:

**Ports & adapters.** The bouncer's rulebook never mentions Ethereum or Nokia. It says
"ask the registry who owns #7" and "apply this config" — abstract **ports**. Real
**adapters** answer in production; cardboard ones (mocks) answer in tests. That's why the
checklist can be unit-tested in milliseconds, years of blockchain and routers nowhere in
sight.

**The walking skeleton.** The fatal pattern is building every prop perfectly in isolation
and discovering on opening night that none of them fit the stage. Instead: perform the
*entire play on day one with cardboard props* — discover→offer→decide→settle→authorize→
activate→teardown, all mocked, ~100 lines, running in CI — then swap props for real ones,
one at a time, keeping the play green after every swap. An integration bug found today
costs minutes; found in September, it costs the defense.

And one house rule binding it all: **evidence or it didn't happen.** A milestone is done
when there's something to *show* — a green test run, a flattened iperf graph, a revocation
visibly killing a live session.

*Formal twin: `DESIGN.md` §6, §10, §11 · ADR-001…005.*

---

## Epilogue — the whole story in twelve lines

```
13:30  Ada gets the job: 45 GB, A→B, before 16:00 → needs 50 Mbps × 2 h
13:31  Ada reads the registry, fetches Bell's agent card, asks for a quote   (A2A)
13:31  Bell checks capacity, signs offer: 50 Mbps · 14:00–16:00 · 10 TOK     (EIP-712)
13:32  Ada's LLM: {"accept": true, "reason": "meets need; within budget"}
13:32  fulfill() — one transaction: serial punched, 10 TOK → Bell,
       ticket #7 → Ada. All or nothing.                                      (atomic)
14:02  Ada → controller: challenge → fresh nonce → signed proof              (replay-safe)
14:02  Checklist: owner ✓ window ✓ not revoked ✓ in-scope ✓ no conflict ✓
14:02  Translator: 0xabc… → srl1, e1-1→e1-2 → gNMI Set: police 50,000 kbps
14:03  iperf3 plateaus at ≈50 Mbps. The ticket became physics.
15:58  Transfer complete (45 GB ÷ 50 Mbps ≈ 2 h, with minutes to spare)
16:00  Chain time ≥ endTime → controller tears down. Coupon expired.
       ─ another day ─  Tess sells telemetry through the SAME machine;
       only the translator differs. That's the thesis.
```

The formal thesis statement says: *a service-agnostic, trust-minimized settlement pattern
for autonomous agent-to-agent network-service provisioning, in which payment is atomically
exchanged for a tokenized entitlement via a standardizing smart contract, and the
entitlement is honored by the provider's enforcement plane.*

In this book's words: **strangers' agents can buy network services from each other,
because a neutral vending machine makes payment-and-ticket one indivisible motion, and
because the network's bouncer trusts nothing but the ticket — and the same machine sells
very different services by swapping one translator.**

### Decoder ring (story word → formal word)

| In this story | In the formal docs |
|---|---|
| vending machine | settlement contract / atomic settlement |
| ticket | entitlement (ERC-721 NFT) |
| wristband the bouncer checks | load-bearing **capability** |
| "I paid" screenshot | receipt (the rejected model) |
| bouncer | controller / anti-corruption layer (ACL) |
| the checklist | authorization predicate |
| serial number + punched-serial ledger | salt + consumed-offer set (single-use offers) |
| printing at the moment of sale | mint-at-swap |
| signed catalog page | EIP-712 signed offer |
| fresh random phrase, burned after use | challenge–response nonce |
| the one clock that counts | chain time (`block.timestamp`), ADR-004 |
| the hands | `netctl` / gNMI |
| the miniature internet | `netlab` / Containerlab + SR Linux |
| the treaty | `interfaces` / published language |
| cardboard props | mocks (adapters behind ports) |
| the full play on day one | walking skeleton |

### Where to go next

- The precise schemas behind every chapter: `docs/03-interfaces.md`
- Why each big choice was made (one page each): `docs/adr/`
- The full plan, scope, and timeline: `DESIGN.md`
- The demo you'll show the jury: `docs/08-demo-dashboard.md` (to come)
