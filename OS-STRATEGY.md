# OS Strategy: KDOS Adaptation vs Custom OS

## 1. The Question

We have two existing OS-level designs:

* **KDOS v1.1** — a Forth-based "Kernel Dashboard OS" for MP64.  ~8,300
  lines of Forth, 653 colon definitions, 405 variables/constants.
  Cooperative + preemptive multitasking, pipeline engine, buffer
  subsystem, filesystem, network stack, TLS 1.3, interactive TUI,
  multicore dispatch.  Mature and tested.

* **Lispos** — a Lisp-native OS design for LM-1.  Actor-model scheduling,
  trap-based syscalls, hardware GC integration, hierarchical work-stealing
  scheduler, image-based boot.  Design docs only — no implementation yet.

The merged SoC ("Chimera-1") needs an OS that:

1. Manages both MP64 and LM-1 subsystems.
2. Orchestrates the Cryptographic Detective Box pipeline.
3. Handles cross-domain messaging, shared DRAM, and peripheral dispatch.
4. Exposes a coherent programming model to both Forth and Lisp code.

---

## 2. Option A: Adapt KDOS

### 2.1 What KDOS Already Has

| Capability | Status | Relevance to Detective Box |
|------------|--------|---------------------------|
| Forth REPL + compiler | ✅ Complete | Interactive debugging, pipeline scripting |
| Buffer subsystem (typed, tile-aligned) | ✅ Complete | Evidence blocks, index structures |
| Kernel registry + pipelines | ✅ Complete | Ingestion/normalization/hashing stages |
| Cooperative + preemptive scheduler | ✅ Complete | Task dispatch for MP64 cores |
| MP64FS filesystem | ✅ Complete | Case file storage, evidence persistence |
| Network stack + data ports | ✅ Complete | Evidence ingestion from external sources |
| TLS 1.3 + post-quantum crypto | ✅ Complete | Secure evidence transport |
| Crypto word bindings (AES, SHA3, KEM, NTT, TRNG, CRC) | ✅ Complete | Core Detective Box operations |
| Multicore dispatch (CORE-RUN, CORE-WAIT, BARRIER) | ✅ Complete | MP64 parallelism |
| Bundle format (versioned pipeline bundles) | ✅ Complete | Deployable investigation bundles |
| Dashboard TUI (9 screens) | ✅ Complete | Operator interface |

### 2.2 What KDOS Would Need

| Addition | Effort | Description |
|----------|--------|-------------|
| LM-1 subsystem driver | Medium | Cross-domain mailbox protocol: send work to LM-1 tiles, receive results.  New Forth words: `LM1-SEND`, `LM1-RECV`, `LM1-STATUS`, `LM1-BOOT`. |
| DRAM manager | Medium | Allocate/free regions in shared DDR5.  KDOS currently uses fixed SRAM banks.  New: `DRAM-ALLOT`, `DRAM-FREE`, `DRAM-MAP`. |
| Evidence store engine | Medium | Append-only evidence blocks with hash chains.  Built on existing buffers + SHA3 + disk.  ~200 lines Forth. |
| Knowledge graph primitives | High | Graph operations (add-node, add-edge, query, traverse) mapped to LM-1 offload.  Forth stubs that dispatch to Lisp actors. |
| GC coordination | Low | KDOS doesn't GC (Forth doesn't need it).  But it needs to not interfere with LM-1 GC pauses — honor "GC in progress" mailbox signals. |
| ISA-mode awareness | Low | KDOS runs in MP64 mode.  No changes needed to core KDOS Forth — it never sees LM-1 instructions. |

### 2.3 Strengths of This Approach

* **Huge head start**: 8,300 lines of tested, working code.
* **Pipeline model is a natural fit**: Detective Box stages (acquire →
  normalize → fingerprint → index → seal) map directly to KDOS kernel
  pipelines.
* **Crypto already wired**: Every crypto accelerator has a Forth binding.
* **Incremental**: The LM-1 subsystem appears as just another peripheral.
  KDOS dispatches graph/AI workloads to it the same way it dispatches
  SIMD work to the tile engine.
* **Operational tooling**: Dashboard, benchmarking, bundle system, docs
  browser — all production-ready.
* **Boot story**: MP64 BIOS (291 words, 11K lines assembly) boots KDOS.
  KDOS then boots LM-1 via mailbox.  Clean layering.

### 2.4 Weaknesses

* **Forth is not ideal for graph algorithms**: Complex graph traversal,
  pattern matching, and rule compilation are awkward in Forth.  Mitigated
  by offloading to LM-1 Lisp.
* **No actor model**: KDOS has tasks, not actors.  Cross-domain messaging
  with LM-1 actors requires a translation layer.
* **No tagged-word runtime**: KDOS operates on raw 64-bit words.  It
  cannot natively inspect or manipulate LM-1 tagged objects.  Needs
  explicit tag/untag helpers.
* **Single-paradigm**: Forth-only programming model.  Operators must learn
  Forth *and* Lisp (for graph work).
* **Scaling**: KDOS scheduler is simple round-robin with 8 task slots.
  Adequate for MP64 but not for coordinating 256 LM-1 tiles.  (LM-1
  tiles schedule themselves — KDOS just launches and monitors.)

---

## 3. Option B: Custom Unified OS

### 3.1 Architecture: "ChimeraOS"

A purpose-built OS that natively spans both subsystems:

```
┌──────────────────────────────────────────────────────────────┐
│                        ChimeraOS                              │
│                                                                │
│  ┌───────────────────┐   ┌────────────────────────────────┐   │
│  │  MP64 Kernel       │   │  LM-1 Runtime                  │   │
│  │  (Forth + C-like)  │   │  (Lisp, actor-model)           │   │
│  │                    │   │                                 │   │
│  │  • Device drivers  │   │  • GC management               │   │
│  │  • Crypto dispatch │   │  • Actor scheduler             │   │
│  │  • Evidence store  │   │  • Knowledge graph engine      │   │
│  │  • DRAM allocator  │   │  • Rule compiler + matcher     │   │
│  │  • NVMe/network    │   │  • Similarity engine           │   │
│  │  • Console REPL    │   │  • Object store                │   │
│  └────────┬───────────┘   └────────────┬──────────────────┘   │
│           │                             │                      │
│  ┌────────▼─────────────────────────────▼──────────────────┐  │
│  │              Cross-Domain Services Layer                 │  │
│  │                                                          │  │
│  │  • Unified mailbox protocol                              │  │
│  │  • Shared DRAM region manager                            │  │
│  │  • Object serialization (Lisp ↔ raw bytes)               │  │
│  │  • Work dispatch API (either side can submit jobs)       │  │
│  │  • Unified logging + evidence provenance                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Key Design Choices

**Dual-kernel, shared services.**  Not a microkernel — two full runtime
systems (Forth on MP64, Lisp on LM-1) with a message-passing bridge.

**Evidence as first-class OS primitive.**  Evidence blocks are not just
"files" — they are a kernel object type with:

* Automatic hash-chain linking on creation
* Hardware-assisted integrity sealing (SHA-3 DMA)
* Immutability enforcement (write-once semantics in the DRAM allocator)
* Cross-referenced by both the Forth buffer system and the Lisp graph

**Actor-native scheduling.**  Instead of KDOS's task-table model (8 slots,
cooperative), ChimeraOS uses:

* For MP64: An extended task model with 32 task slots, priority queues,
  and mailbox-driven wakeup (not just timer preemption).
* For LM-1: The Lispos actor scheduler (hierarchical: global → cluster →
  tile → thread), with work stealing.
* Cross-domain: An MP64 task can `SEND` to an LM-1 actor and block until
  a reply arrives.  An LM-1 actor can request crypto/SIMD work from MP64.

**Unified namespace.**  Both Forth words and Lisp symbols live in a shared
"registry" that maps names to capabilities.  An operator can invoke a Lisp
function from the Forth REPL:

```forth
S" (build-timeline user-42 T1 T2)" LM1-EVAL  \ sends to LM-1, blocks for result
```

And a Lisp program can call MP64 crypto:

```lisp
(sha3-hash evidence-buffer)  ;; dispatches to MP64 crypto via SEND
```

### 3.3 What Must Be Built

| Component | Lines (est.) | Description |
|-----------|-------------|-------------|
| MP64 kernel (Forth) | ~4,000 | Simplified from KDOS: drivers, DRAM, task scheduler, evidence store.  Reuse KDOS crypto/network bindings. |
| LM-1 runtime (Lisp) | ~6,000 | Actor scheduler, GC policy, trap handlers, object system.  Based on Lispos design docs. |
| Cross-domain bridge | ~2,000 | Mailbox protocol, serialization, dispatch API. |
| Evidence engine | ~1,500 | Hash-chain blocks, integrity ledger, snapshot management. |
| Knowledge graph | ~3,000 | Lisp-side graph store with persistence to DRAM, query engine. |
| Rule compiler | ~2,000 | Declarative pattern language → graph query plans. Runs in Lisp. |
| Similarity engine | ~1,500 | LSH, shingle sets, clustering.  Uses MP64 SIMD tile engine via dispatch. |
| Console / TUI | ~1,500 | Reuse KDOS screen system, extended for LM-1 status. |
| **Total** | **~21,500** | |

### 3.4 Strengths

* **Purpose-built for the Detective Box**: Every abstraction (evidence
  blocks, graph primitives, rule engine) is a first-class OS concept,
  not bolted onto a general-purpose Forth system.
* **Clean cross-domain model**: Designed from day one for dual-ISA
  operation.  No impedance mismatch.
* **Actor model throughout**: Both MP64 tasks and LM-1 tasks use the same
  message-passing paradigm.  Uniform programming model.
* **Evidence as kernel primitive**: Hardware-enforced immutability, inline
  hashing, provenance tracking at the OS level.
* **Optimal scheduling**: LM-1 work-stealing scheduler is designed for
  256 tiles.  No need to shoehorn KDOS's 8-task scheduler.

### 3.5 Weaknesses

* **~21K lines of new code**: Even reusing KDOS subsystems, this is a
  significant engineering effort.
* **Two codebases**: MP64 kernel in Forth, LM-1 runtime in Lisp.  Two
  languages, two debugging stories, two sets of docs.
* **KDOS features lost**: The complete, tested KDOS (8,300 lines) is
  partially rewritten, not fully reused.  Risk of regressions.
* **Boot complexity**: Two firmware images, two initialization sequences,
  cross-domain handshake.
* **No existing tests**: KDOS has 1,258+ tests.  ChimeraOS starts at zero.

---

## 4. Comparative Analysis

| Criterion | KDOS Adaptation | Custom ChimeraOS |
|-----------|----------------|-------------------|
| Time to first boot | **Weeks** (KDOS boots today) | **Months** (new kernel) |
| Crypto integration | **Already done** | Reuse KDOS bindings |
| Pipeline model | **Built-in** (kernels + pipelines) | Must rebuild |
| Graph workloads | Offload to LM-1 (thin bridge) | **Native Lisp graph engine** |
| Evidence model | Bolted on (buffer + SHA3) | **First-class primitive** |
| Cross-domain UX | Forth → LM-1 shim words | **Unified namespace** |
| Scheduling quality | Adequate for MP64 (LM-1 self-schedules) | **Optimal** |
| Code reuse | **~90% of KDOS** | ~30% of KDOS + new Lispos |
| Testing base | **1,258+ tests** | 0 (must write new) |
| Operational tooling | **Complete** (dashboard, docs, bundles) | Must rebuild |
| Maintainability | Single Forth codebase + LM-1 shims | Dual codebase |
| Extensibility | Add Forth words for new features | Full Lisp metaprogramming |
| Detective Box fit | Good (with shims) | **Excellent** (purpose-built) |

---

## 5. Recommendation: Hybrid — KDOS Core + Lisp Services

The pragmatic path is **neither pure option**, but a blend:

### 5.1 Layer 0: KDOS as System Kernel

Keep KDOS as the boot kernel on MP64.  It manages:

* Hardware init, DRAM controller config, peripheral bring-up
* Evidence store (append-only buffers + SHA-3 hash chains)
* Crypto pipeline (all existing bindings)
* Network ingestion (data ports, frame routing)
* NVMe/disk persistence (MP64FS)
* Console + dashboard (TUI)
* MP64 task scheduling (KDOS scheduler)

**Changes to KDOS** (~800 lines of new Forth):

```forth
\ --- LM-1 subsystem driver ---
: LM1-BOOT     ( -- )          \ Load LM-1 firmware from disk to DRAM, signal tile 0
: LM1-SEND     ( msg-addr tile -- )   \ Post message to LM-1 tile queue
: LM1-RECV     ( buf -- n )    \ Read reply from LM-1 mailbox into buffer
: LM1-STATUS   ( -- flags )    \ Query LM-1 subsystem health
: LM1-EVAL     ( str len -- )  \ Send Lisp form to LM-1, print result

\ --- Shared DRAM manager ---
: DRAM-ALLOT   ( bytes -- addr )   \ Bump-allocate from shared DRAM region
: DRAM-FREE    ( addr bytes -- )   \ Return region (simple freelist)
: DRAM-MAP     ( addr bytes -- )   \ Map DRAM region into buffer descriptor

\ --- Evidence store ---
: EVIDENCE-SEAL  ( buf -- )    \ Hash buffer, append to evidence chain
: EVIDENCE-CHAIN ( -- addr n ) \ Return evidence block chain head + length
: EVIDENCE-VERIFY ( idx -- f ) \ Verify integrity of evidence block idx
```

### 5.2 Layer 1: Lispos as Application Runtime on LM-1

The LM-1 tiles run the Lispos runtime (actor scheduler, GC, trap
handlers, object system).  Lispos manages:

* Actor scheduling across all LM-1 tiles
* Garbage collection (nursery → old-gen → DRAM)
* Knowledge graph engine (nodes, edges, queries in Lisp)
* Rule compiler and pattern matcher (Lisp DSL)
* Similarity/clustering computations (dispatching SIMD work to MP64 via
  cross-domain messages)

Lispos is a **service layer**, not the system kernel.  It receives work
requests from KDOS and returns structured results.

### 5.3 Layer 2: Cross-Domain Protocol

A thin message protocol connects KDOS and Lispos:

| Message Type | Direction | Payload |
|-------------|-----------|---------|
| `WORK_REQ` | KDOS → Lispos | Job type + DRAM pointer to input data |
| `WORK_RESP` | Lispos → KDOS | Status + DRAM pointer to result |
| `GC_PAUSE` | Lispos → KDOS | "Don't touch DRAM region X for N µs" |
| `GC_RESUME` | Lispos → KDOS | "Region X is safe again" |
| `CRYPTO_REQ` | Lispos → KDOS | Crypto op + data pointer |
| `CRYPTO_RESP` | KDOS → Lispos | Result + hash/ciphertext pointer |
| `STATUS_REQ` | Either | Health/metrics query |
| `STATUS_RESP` | Either | Metrics bundle |

### 5.4 Why This Works

1. **KDOS boots today** — the MP64 side is operational immediately.
2. **Lispos development is independent** — LM-1 tiles can be brought up
   incrementally while KDOS handles all I/O and persistence.
3. **Clean separation of concerns** — Forth for hardware/crypto/storage,
   Lisp for AI/graph/reasoning.  Each language does what it's best at.
4. **Evidence store lives in KDOS** — the chain-of-custody, hashing, and
   provenance are handled by the system kernel, not the GC'd runtime.
   This is important for integrity: evidence blocks must never be moved
   or collected by a GC.
5. **~800 lines of KDOS additions** vs ~21K lines for a full custom OS.
6. **Existing test suite** (1,258+ tests) remains valid.  New tests
   needed only for the ~800 lines of additions + the cross-domain
   protocol.

### 5.5 What We Give Up

* No unified namespace (Forth and Lisp remain separate worlds, connected
  by messages).  Acceptable — the detective box is an appliance, not a
  general-purpose dev environment.
* Evidence store is not a kernel primitive — it's a Forth library.  But
  on MP64, "Forth library" and "kernel" are the same thing (KDOS *is*
  Forth all the way down).
* LM-1 scheduling is Lispos's problem.  KDOS can't inspect or preempt
  individual LM-1 actors.  But it can kill the whole LM-1 subsystem and
  reboot it if something goes wrong (`LM1-BOOT`).

---

## 6. Implementation Roadmap

| Phase | Milestone | Depends On |
|-------|-----------|-----------|
| OS-1 | KDOS boots on Chimera-1 SoC (MP64 side) | SoC Phase 1 |
| OS-2 | `DRAM-ALLOT` / `DRAM-FREE` / `DRAM-MAP` working | SoC DRAM ctrl |
| OS-3 | `LM1-BOOT`: KDOS loads LM-1 firmware to DRAM, signals tile 0 | SoC bridge |
| OS-4 | `LM1-SEND` / `LM1-RECV`: cross-domain message round-trip | SoC mailbox |
| OS-5 | Evidence store: `EVIDENCE-SEAL` / `EVIDENCE-VERIFY` | SHA3 bindings (done) |
| OS-6 | Lispos single-tile boot on LM-1 (actor scheduler, minimal GC) | LM-1 tile RTL |
| OS-7 | Cross-domain crypto: Lispos calls SHA3 via KDOS | OS-4 |
| OS-8 | Lispos multi-tile: work-stealing across N tiles | LM-1 cluster RTL |
| OS-9 | Knowledge graph engine in Lispos | OS-8 |
| OS-10 | End-to-end detective box pipeline: KDOS ingests → Lispos analyzes → KDOS reports | OS-5 + OS-9 |
