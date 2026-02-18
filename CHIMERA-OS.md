# ChimeraOS — Unified Operating System for Chimera-1

## 1. Design Mandate

ChimeraOS is the purpose-built operating system for the Chimera-1
heterogeneous SoC.  It spans both the MP64 register-machine subsystem
(4 full cores + 3 micro-clusters of 4 µ-cores each) and the LM-1
many-tile Lisp subsystem (up to 256 tiles across 32 clusters).

ChimeraOS is **not** a general-purpose OS.  It is an appliance kernel
optimised for one workload class: the Cryptographic Detective Box — a
local, high-throughput evidence-ingestion, knowledge-graph, and
reasoning engine with hardware-enforced tamper-evidence.

### 1.1 Why Not Adapt KDOS?

KDOS v1.1 (8,300 lines Forth, 653 colon defs, 1,258+ tests) is
production-quality for MP64 alone.  But bolting on the LM-1 subsystem
as "just another peripheral" creates impedance mismatches:

* **Scheduling**: KDOS has 8 task slots, round-robin.  LM-1 needs a
  256-tile hierarchical work-stealing actor scheduler.  No shim
  reconciles these.
* **Evidence model**: In KDOS, evidence blocks are "buffers + SHA-3" —
  a library.  ChimeraOS makes evidence a kernel primitive with
  hardware-enforced write-once semantics, inline hash chaining, and
  cross-domain provenance tracking.
* **Graph workloads**: Forth is painful for graph algorithms, pattern
  matching, and rule compilation.  Offloading everything to LM-1 via
  messages introduces serialisation overhead and splits the abstraction.
  ChimeraOS gives LM-1 a first-class graph/rule subsystem at OS level.
* **Actor model**: KDOS tasks ≠ actors.  Cross-domain messaging requires
  a proper actor abstraction on both sides, not a translation layer.
* **Unified namespace**: An operator should be able to invoke Lisp graph
  queries from the Forth REPL and dispatch MP64 crypto from Lisp code
  without knowing which bus transaction carries the call.

ChimeraOS accepts the ~21K-line cost for a cleaner architecture that
treats the Detective Box as the primary design constraint, not an
afterthought.

### 1.2 What We Salvage from KDOS

We are not starting from zero.  Large subsystems port directly:

| KDOS Subsystem | Lines | Reuse Strategy |
|----------------|------:|----------------|
| Crypto bindings (AES, SHA3, CRC, TRNG, KEM, NTT, Field) | ~600 | Copy verbatim — same CSR interface |
| Buffer subsystem (typed, tile-aligned, descriptors) | ~400 | Copy, extend with evidence metadata |
| Pipeline engine (kernel registry, P.ADD/P.RUN) | ~300 | Copy, add P.RUN-CROSS for cross-domain steps |
| Network stack (Ethernet, ARP, IPv4, UDP, TCP, TLS 1.3) | ~1,400 | Copy verbatim — pure MP64 |
| Storage (disk persistence, MP64FS) | ~500 | Copy, extend for evidence checkpoints |
| ANSI terminal / screen system | ~500 | Copy, add LM-1 and evidence screens |
| Multicore dispatch (CORE-RUN, BARRIER, work-stealing) | ~400 | Copy, extend for µ-cluster awareness |
| Dashboard / help / startup | ~300 | Copy, extend |
| **Total reused** | **~4,400** | **~53% of KDOS** |

The remaining ~3,900 lines of KDOS (REPL, basic scheduler, demos,
doc browser, dict search) are either superseded by ChimeraOS
equivalents or kept as-is for compatibility.

---

## 2. Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                            ChimeraOS                                  │
│                                                                       │
│  ┌───────────────────────────┐    ┌────────────────────────────────┐  │
│  │      Σ-Kernel             │    │       λ-Runtime                │  │
│  │      (MP64 · Forth)       │    │       (LM-1 · Lisp)           │  │
│  │                           │    │                                │  │
│  │  ┌─────────────────────┐  │    │  ┌──────────────────────────┐ │  │
│  │  │ HAL                 │  │    │  │ Tile Runtime             │ │  │
│  │  │ UART Timer NIC NVMe │  │    │  │ Trap table  GC  Threads │ │  │
│  │  │ Crypto  Mailbox     │  │    │  │ Nursery  Old-gen  Cards │ │  │
│  │  └─────────────────────┘  │    │  └──────────────────────────┘ │  │
│  │  ┌─────────────────────┐  │    │  ┌──────────────────────────┐ │  │
│  │  │ Task Scheduler      │  │    │  │ Actor Scheduler          │ │  │
│  │  │ 32 slots · priority │  │    │  │ Hierarchical · stealing  │ │  │
│  │  │ per-core queues     │  │    │  │ Global→Cluster→Tile→Thd  │ │  │
│  │  │ affinity · preempt  │  │    │  │ 5 priority levels        │ │  │
│  │  └─────────────────────┘  │    │  └──────────────────────────┘ │  │
│  │  ┌─────────────────────┐  │    │  ┌──────────────────────────┐ │  │
│  │  │ DRAM Manager        │  │    │  │ GC Coordinator           │ │  │
│  │  │ Regions · write-once│  │    │  │ Nursery · Old-gen · Full │ │  │
│  │  │ Allocator · freelist│  │    │  │ Movement engines · fence │ │  │
│  │  └─────────────────────┘  │    │  └──────────────────────────┘ │  │
│  │  ┌─────────────────────┐  │    │  ┌──────────────────────────┐ │  │
│  │  │ Evidence Engine     │  │    │  │ Knowledge Graph          │ │  │
│  │  │ Hash-chain · seal   │  │    │  │ Partitioned · parallel   │ │  │
│  │  │ Write-once DRAM     │  │    │  │ BFS · motif · temporal   │ │  │
│  │  │ NVMe checkpoints    │  │    │  └──────────────────────────┘ │  │
│  │  └─────────────────────┘  │    │  ┌──────────────────────────┐ │  │
│  │  ┌─────────────────────┐  │    │  │ Rule Engine              │ │  │
│  │  │ Ingestion Pipeline  │  │    │  │ DSL · compiler · matcher │ │  │
│  │  │ Parse · Normalise   │  │    │  │ Graph traversal actors   │ │  │
│  │  │ Fingerprint · Seal  │  │    │  └──────────────────────────┘ │  │
│  │  └─────────────────────┘  │    │  ┌──────────────────────────┐ │  │
│  │  ┌─────────────────────┐  │    │  │ Similarity Engine        │ │  │
│  │  │ Crypto Subsystem    │  │    │  │ LSH · cluster · outlier  │ │  │
│  │  │ AES SHA3 KEM NTT    │  │    │  │ SIMD dispatch via Σ     │ │  │
│  │  │ CRC TRNG Field      │  │    │  └──────────────────────────┘ │  │
│  │  └─────────────────────┘  │    │  ┌──────────────────────────┐ │  │
│  │  ┌─────────────────────┐  │    │  │ Object Store             │ │  │
│  │  │ Console / TUI       │  │    │  │ Persistent graph         │ │  │
│  │  │ 11 screens · REPL   │  │    │  │ Block-device backed      │ │  │
│  │  └─────────────────────┘  │    │  └──────────────────────────┘ │  │
│  └────────────┬──────────────┘    └──────────────┬─────────────────┘  │
│               │                                   │                    │
│  ┌────────────▼───────────────────────────────────▼─────────────────┐ │
│  │                    χ-Bridge  (Cross-Domain Layer)                │ │
│  │                                                                  │ │
│  │  ┌──────────┐ ┌───────────┐ ┌────────────┐ ┌─────────────────┐  │ │
│  │  │ Mailbox  │ │ Serialise │ │ Capability │ │ Unified         │  │ │
│  │  │ Protocol │ │ Lisp ↔    │ │ Tokens     │ │ Registry        │  │ │
│  │  │ 64B envl │ │ Raw bytes │ │ (ACLs)     │ │ (name→service)  │  │ │
│  │  └──────────┘ └───────────┘ └────────────┘ └─────────────────┘  │ │
│  │  ┌──────────────────────────────────────────────────────────┐    │ │
│  │  │ Work Dispatch: either side submits jobs to either side   │    │ │
│  │  │ GC Coordination: pause/resume/fence signals              │    │ │
│  │  │ Evidence Provenance: cross-domain hash-chain witnesses   │    │ │
│  │  └──────────────────────────────────────────────────────────┘    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

The three named layers:

| Layer | Name | Runs On | Language | Role |
|:-----:|------|---------|----------|------|
| **Σ** | Sigma-Kernel | MP64 (4 full + 12 µ-cores) | Forth | Hardware, I/O, crypto, evidence, ingestion, console |
| **λ** | Lambda-Runtime | LM-1 (up to 256 tiles, 1024 threads) | Lisp | GC, actors, graph, rules, similarity, object store |
| **χ** | Chi-Bridge | Both (shared MMIO + DRAM) | Protocol | Cross-domain messaging, serialisation, dispatch |

---

## 3. Σ-Kernel — The MP64 Forth Kernel

### 3.1 Hardware Abstraction Layer (HAL)

Thin wrappers around MMIO registers and CSRs.  Ported directly from
KDOS/BIOS with zero modification where the hardware interface is
unchanged.

```forth
\ === Core identity ===
: COREID       ( -- n )     CSR_COREID CSR@ ;
: NCORES       ( -- n )     CSR_NCORES CSR@ ;
: MICRO?       ( core -- f ) N-FULL-CORES >= ;

\ === Timer ===
: TIMER!       ( val -- )   MMIO_TIMER_CMP ! ;
: TIMER-CTRL!  ( val -- )   MMIO_TIMER_CTL ! ;
: TIMER-ACK    ( -- )       1 MMIO_TIMER_CTL ! ;
: CYCLES       ( -- u )     CSR_PERF_CYCLES CSR@ ;

\ === Interrupt control ===
: EI!          ( mask -- )  CSR_IE CSR! ;
: DI!          ( -- )       0 CSR_IE CSR! ;
: ISR!         ( xt vec -- ) CELLS IVT-BASE + ! ;

\ === Crypto (unchanged from KDOS) ===
: SHA3-INIT    ( mode -- )          MMIO_SHA3_MODE ! ;
: SHA3-UPDATE  ( addr len -- )      MMIO_SHA3_DATA DMA-START SHA3-WAIT ;
: SHA3-FINAL   ( out-addr -- )      MMIO_SHA3_CTL 2 SWAP ! SHA3-WAIT ... ;
: AES-KEY!     ( key-addr -- )      32 0 DO  DUP I + C@  MMIO_AES_KEY I + C!  LOOP DROP ;
: AES-ENCRYPT  ( in out len -- )    ... ;
: CRC-RESET    ( -- )               0 MMIO_CRC_CTL ! ;
: CRC-FEED     ( addr len -- )      MMIO_CRC_DATA DMA-START CRC-WAIT ;
: CRC-RESULT   ( -- u )             MMIO_CRC_RESULT @ ;
: TRNG         ( -- u64 )           MMIO_TRNG_DATA @ ;
\ ... KEM, NTT, FieldALU words identical to KDOS
```

### 3.2 SIMD Tile Engine Interface

Each of the 4 full cores has its own `mp64_tile` instance.  The HAL
exposes tile ops as Forth words with automatic core routing.

```forth
\ CSR-based tile configuration (per-core, private)
: TMODE!   ( val -- )   CSR_TMODE CSR! ;
: TCTRL!   ( val -- )   CSR_TCTRL CSR! ;
: TSRC0!   ( addr -- )  CSR_TSRC0 CSR! ;
: TSRC1!   ( addr -- )  CSR_TSRC1 CSR! ;
: TDST!    ( addr -- )  CSR_TDST  CSR! ;
: ACC@     ( -- u )     CSR_ACC0  CSR@ ;

\ MEX dispatch (high-level: operates on buffers)
: B.SUM    ( buf -- u )   B.DATA TSRC0!  2 TCTRL!  MEX-TRED-SUM  ACC@ ;
: B.ADD    ( a b c -- )   >R B.DATA TSRC1!  B.DATA TSRC0!  R> B.DATA TDST!  MEX-TALU-ADD ;
: B.SCALE  ( n buf -- )   B.DATA DUP TSRC0! TDST!  TSRC1-BCAST!  MEX-TMUL-SMUL ;

\ µ-cores lack tile engines — dispatch traps as ILLEGAL_OP
\ The scheduler (§3.4) never assigns tile-requiring tasks to µ-cores
```

### 3.3 DRAM Manager

MP64's existing SRAM banks (4 × 256 KiB = 1 MiB internal) are used for
kernel data, stacks, and hot working sets.  The shared DDR5 DRAM (32–128
GiB) is managed by a region allocator.

```forth
\ === DRAM Region Allocator ===
\ Manages the shared DRAM address space (0x4000_0000 – end).
\ Three region types with different lifetime semantics.

VARIABLE DRAM-HEAP       \ bump pointer for transient allocations
VARIABLE DRAM-HEAP-END
VARIABLE DRAM-EVID       \ bump pointer for write-once evidence region
VARIABLE DRAM-EVID-END
VARIABLE DRAM-GRAPH      \ base of graph partition (LM-1 managed)
VARIABLE DRAM-GRAPH-END

: DRAM-INIT ( -- )
    \ Zone 0: Transient heap (first 25% of DRAM)
    HEX 40000000 DRAM-HEAP !
    HEX 48000000 DRAM-HEAP-END !
    \ Zone 1: Evidence store (next 25%)
    HEX 48000000 DRAM-EVID !
    HEX 50000000 DRAM-EVID-END !
    \ Zone 2: Graph / LM-1 managed (remaining 50%)
    HEX 50000000 DRAM-GRAPH !
    HEX 60000000 DRAM-GRAPH-END ! ;

: DRAM-ALLOT ( bytes -- addr )
    64 ALIGN                        \ tile-align
    DRAM-HEAP @ SWAP                ( base bytes )
    OVER + DUP DRAM-HEAP-END @ > ABORT" DRAM exhausted"
    DRAM-HEAP !                     ( base )
;

: DRAM-FREE ( addr bytes -- )
    \ Simple: no-op for bump allocator.
    \ Phase 2: freelist with coalescing.
    2DROP ;

\ === Write-Once Evidence Region ===
\ Allocations in this zone are permanently sealed.
\ The DRAM controller marks the range read-only after write.

: EVID-ALLOT ( bytes -- addr )
    64 ALIGN
    DRAM-EVID @ SWAP
    OVER + DUP DRAM-EVID-END @ > ABORT" Evidence DRAM full"
    DRAM-EVID ! ;
```

**Memory map overlay:**

| DRAM Range | Zone | Owner | Semantics |
|-----------|------|-------|-----------|
| `0x4000_0000 – 0x47FF_FFFF` | Transient | Σ-Kernel | Alloc/free, general purpose |
| `0x4800_0000 – 0x4FFF_FFFF` | Evidence | Σ-Kernel | Write-once, append-only |
| `0x5000_0000 – 0x5FFF_FFFF` | Graph | λ-Runtime | GC-managed Lisp heap |
| Remainder | Overflow | Either | Dynamically assigned as needed |

### 3.4 Task Scheduler

Upgraded from KDOS's 8-slot round-robin to a 32-slot priority-queue
scheduler with per-core run queues, work stealing, core affinity, and
µ-core awareness.

```forth
\ === Task descriptor (8 cells = 64 bytes) ===
\   +0   status        0=FREE 1=READY 2=RUNNING 3=BLOCKED 4=DONE
\   +8   priority      0=highest, 255=lowest
\   +16  xt            execution token
\   +24  dsp_save      saved data stack
\   +32  rsp_save      saved return stack
\   +40  name_addr     name string or 0
\   +48  flags         bit0=tile-required  bit1=evidence-ctx  bit2=cross-domain
\   +56  affinity      core ID or -1 (any)

32 CONSTANT MAX-TASKS
VARIABLE TASK-TABLE  MAX-TASKS CELLS ALLOT
VARIABLE TASK-COUNT  0 TASK-COUNT !

\ Per-core circular run queues (inherited from KDOS §8.2)
\ Each full core: 16-entry queue.  µ-clusters: shared 8-entry queue.
16 CONSTANT RQ-CAP
VARIABLE RQ-DATA     NCORES_MAX RQ-CAP * CELLS ALLOT
VARIABLE RQ-HEAD     NCORES_MAX CELLS ALLOT
VARIABLE RQ-TAIL     NCORES_MAX CELLS ALLOT

: TASK ( xt priority "name" -- )
    CREATE-TASK-DESC
    DUP T.FLAGS 0 SWAP !           \ clear flags
    DUP T.AFFINITY -1 SWAP !       \ any core
    REGISTER-TASK ;

: SPAWN-TILE ( xt -- )
    \ Spawn with tile-required flag — never dispatched to µ-core
    SPAWN  LAST-SPAWNED T.FLAGS @ 1 OR  LAST-SPAWNED T.FLAGS ! ;

: SPAWN-ON ( xt core -- )
    \ Dispatch to a specific core's run queue
    OVER SWAP RQ-PUSH
    TASK-COUNT @ 1+ TASK-COUNT ! ;

\ --- Scheduling loop ---
: SCHEDULE ( -- )
    1 SCHED-RUNNING !
    BEGIN
        FIND-READY-PRIO DUP        \ find highest-priority READY task
    WHILE
        DUP T.FLAGS @ 1 AND IF
            \ Tile-required: only dispatch to full cores
            DUP T.AFFINITY @ DUP -1 = IF
                DROP NEXT-FULL-CORE
            THEN
        ELSE
            DUP T.AFFINITY @ DUP -1 = IF
                DROP NEXT-ANY-CORE
            THEN
        THEN
        DISPATCH-TO                 \ enqueue on chosen core
    REPEAT
    DROP
    SCHED-ALL                       \ drain all core queues
    0 SCHED-RUNNING ! ;

\ --- Work stealing (per KDOS §8.3) ---
: WORK-STEAL ( idle-core -- flag )
    RQ-BUSIEST OVER = IF DROP 0 EXIT THEN
    DUP -1 = IF DROP 0 EXIT THEN
    OVER STEAL-FROM ;

: BALANCE ( -- )
    BEGIN
        0
        N-FULL-CORES 0 DO
            I RQ-EMPTY? IF
                I WORK-STEAL IF DROP -1 THEN
            THEN
        LOOP
        0=
    UNTIL ;
```

### 3.5 Evidence Engine

The core Detective Box primitive.  Evidence blocks are kernel objects,
not library data structures.  The Σ-Kernel owns the evidence chain;
the λ-Runtime can read evidence blocks but cannot create or modify them.

```forth
\ === Evidence Block Layout (128-byte header + variable payload) ===
\
\   Offset  Size    Field
\     0      32     sha3_hash         SHA-3-256 of payload
\    32      32     prev_hash         SHA-3-256 of previous block (chain link)
\    64       8     sequence_number   monotonic counter
\    72       8     timestamp         CYCLES at seal time
\    80       8     source_id         data port / import / cross-domain origin
\    88       8     payload_length    bytes of payload
\    96       8     schema_version    canonical schema version
\   104       8     flags             bit0=sealed  bit1=verified  bit2=exported
\                                     bit3=lm1-witness (cross-domain)
\   112      16     reserved
\   128       *     payload           normalised records / raw bytes

VARIABLE EVID-HEAD       0 EVID-HEAD !     \ address of latest block
VARIABLE EVID-COUNT      0 EVID-COUNT !    \ monotonic counter
VARIABLE EVID-PREV-HASH  32 ALLOT          \ hash of previous block (rolling)

: EVIDENCE-SEAL ( buf -- )
    \ 1. Allocate write-once DRAM for header + payload
    DUP B.BYTES 128 +  EVID-ALLOT         ( buf block-addr )

    \ 2. Fill header
    EVID-COUNT @ 1+  DUP EVID-COUNT !     ( buf block seq )
    OVER 64 + !                            ( buf block )        \ sequence_number
    CYCLES OVER 72 + !                                          \ timestamp
    DUP 80 + 0 SWAP !                                           \ source_id (set by caller)
    OVER B.BYTES OVER 88 + !                                    \ payload_length
    1 OVER 96 + !                                               \ schema v1
    1 OVER 104 + !                                              \ flags = sealed

    \ 3. Copy payload
    2DUP 128 + SWAP B.DATA SWAP B.BYTES CMOVE

    \ 4. Hash payload → sha3_hash (first 32 bytes)
    DUP 128 + OVER 88 + @ SHA3-256         ( buf block )
    SHA3-OUT OVER 32 CMOVE                 \ store hash at +0

    \ 5. Copy prev_hash from rolling state
    EVID-PREV-HASH OVER 32 + 32 CMOVE     \ store prev_hash at +32

    \ 6. Update rolling prev_hash to this block's hash
    DUP EVID-PREV-HASH 32 CMOVE

    \ 7. Register as head
    EVID-HEAD !

    DROP ;                                  ( )

: EVIDENCE-VERIFY ( idx -- flag )
    EVID-BLOCK@                            \ look up block by index
    DUP 0= IF DROP FALSE EXIT THEN
    \ Recompute payload hash
    DUP 128 + OVER 88 + @ SHA3-256
    SHA3-OUT OVER 32 COMPARE 0= IF
        \ Verify chain link (except block 0)
        DUP 64 + @ 0> IF                  \ sequence > 0?
            DUP 32 +                       \ prev_hash field
            \ look up previous block, compare its hash
            DUP 64 + @ 1- EVID-BLOCK@
            DUP 0= IF 2DROP DROP FALSE EXIT THEN
            32 COMPARE 0=
        ELSE
            DROP TRUE                      \ genesis block, no prev
        THEN
    ELSE
        DROP FALSE
    THEN ;

: EVIDENCE-CHAIN ( -- addr count )
    EVID-HEAD @  EVID-COUNT @ ;

: EVIDENCE-STATS ( -- )
    ." Evidence chain: " EVID-COUNT @ . ." blocks" CR
    ." Head block at: " EVID-HEAD @ HEX. CR
    ." DRAM used: " DRAM-EVID @ HEX 48000000 - . ." bytes" CR ;

: EVIDENCE-CHECKPOINT ( -- )
    \ Flush evidence DRAM region to NVMe
    HEX 48000000  DRAM-EVID @  OVER -     ( addr bytes )
    0 DISK-DMA-WRITE                       \ DMA to NVMe starting sector 0
    ." Checkpoint: " . ." bytes written to NVMe" CR ;
```

### 3.6 Ingestion Pipeline

The Σ-Kernel ingestion pipeline is a KDOS-style kernel pipeline with
cross-domain stages.  Evidence flows through 6 stages with hardware
acceleration at each step.

```forth
6 PIPELINE ingest-pipe

: stage-acquire ( -- )
    \ Read from bound data port (NIC or NVMe import)
    ingest-buf PORT-ID PORT@ DROP
    ingest-buf B.BYTES 0= IF EXIT THEN ;

: stage-normalise ( -- )
    \ Parse raw bytes into canonical schema
    ingest-buf schema-version@ CASE
        1 OF ingest-buf parse-syslog  ENDOF
        2 OF ingest-buf parse-json    ENDOF
        3 OF ingest-buf parse-pcap    ENDOF
    ENDCASE ;

: stage-resolve ( -- )
    \ Identity resolution: dispatch to λ-Runtime
    ingest-buf entity-fields@          ( addr len )
    X-RESOLVE-ID                       \ χ-Bridge call to LM-1 identity actor
    ingest-buf stable-id! ;            \ store resolved ID

: stage-fingerprint ( -- )
    \ Crypto fingerprinting (all on MP64 hardware)
    ingest-buf B.DATA ingest-buf B.BYTES SHA3-256
    ingest-buf B.DATA ingest-buf B.BYTES CRC-DMA
    ingest-buf simhash-tile-kernel ;   \ SIMD SimHash via per-core tile engine

: stage-index ( -- )
    \ Update search indexes (dispatch heavy work to λ-Runtime)
    ingest-buf X-INDEX-UPDATE ;        \ χ-Bridge: add to graph + similarity index

: stage-seal ( -- )
    ingest-buf EVIDENCE-SEAL ;

' stage-acquire     ingest-pipe P.ADD
' stage-normalise   ingest-pipe P.ADD
' stage-resolve     ingest-pipe P.ADD
' stage-fingerprint ingest-pipe P.ADD
' stage-index       ingest-pipe P.ADD
' stage-seal        ingest-pipe P.ADD
```

### 3.7 Console and TUI

Extended from KDOS's 9-screen TUI to 11 screens:

| Screen | Key | Content |
|--------|:---:|---------|
| S1: Home | `1` | System overview (cores, memory, tasks, DRAM usage) |
| S2: Buffers | `2` | Buffer registry (type, width, length, residency) |
| S3: Kernels | `3` | Kernel registry (inputs, outputs, tile footprint) |
| S4: Pipelines | `4` | Pipeline status and per-step timing |
| S5: Tasks | `5` | Task table (32 slots: status, priority, affinity, core) |
| S6: Help | `6` | Quick reference card |
| S7: Storage | `7` | NVMe disk, MP64FS directory, evidence checkpoints |
| S8: Network | `8` | NIC status, data ports, TLS sessions |
| S9: Evidence | `9` | Evidence chain: block count, integrity, DRAM usage |
| S10: LM-1 | `0` | λ-Runtime: tile count, actor count, GC stats, graph size |
| S11: Case | `-` | Active case: name, evidence count, findings, export status |

---

## 4. λ-Runtime — The LM-1 Lisp Runtime

The λ-Runtime is based on the Lispos design (design/os.md in
lisp-machine-LM1) but implemented as a **service layer** within
ChimeraOS rather than a standalone operating system.

### 4.1 Tile Runtime

Each LM-1 tile runs a per-tile runtime initialised at boot:

```lisp
(defstruct tile-env
  tile-id                ; fixnum
  thread-contexts        ; vector of 4 thread context structs
  nursery-base           ; raw address
  nursery-limit          ; raw address
  card-table-base        ; raw address
  trap-table             ; raw address → OS trap handlers
  header-templates       ; vector of 64-bit header template words
  ic-table               ; inline cache hash map
  local-actor-queue      ; queue of actors waiting to run
  gc-state               ; current GC phase + stats
  method-cache           ; ref to cluster-shared method cache
  symbol-table           ; ref to cluster-shared symbol table
  bridge-queue)          ; inbound χ-Bridge messages from Σ-Kernel
```

**Trap handlers** (the OS's syscall mechanism — no explicit SYSCALL
instruction exists in LM-1):

| Trap | Handler |
|------|---------|
| `TRAP_NOT_FIXNUM` (0x01) | Generic arithmetic dispatch via method table |
| `TRAP_FIXNUM_OVERFLOW` (0x02) | Promote to bignum, retry |
| `TRAP_NURSERY_OVERFLOW` (0x10) | Production nursery GC (Cheney copy) |
| `TRAP_IC_MISS` (0x20) | Method lookup, IC install, retry |
| `TRAP_QUEUE_FULL` (0x30) | Back-pressure: yield thread, retry later |
| `TRAP_QUEUE_EMPTY` (0x31) | No message: yield, schedule another actor |

### 4.2 Garbage Collector

Three-generation, mostly-concurrent collector using LM-1's hardware
GC support (card tables, write barriers, movement engines).

| Generation | Location | Algorithm | Trigger |
|:----------:|----------|-----------|---------|
| Gen 0 (nursery) | Tile SRAM (64 KiB/tile) | Stop-the-tile Cheney copy | `TRAP_NURSERY_OVERFLOW` |
| Gen 1 (old-gen) | Cluster shared SRAM (2 MiB) | Movement-engine assisted compaction | Promotion threshold |
| Gen 2 (DRAM) | Graph zone (DRAM `0x5000_0000+`) | Incremental mark-compact | Full-heap pressure |

**GC coordination with Σ-Kernel:** The Σ-Kernel must never hold raw
pointers into LM-1 managed DRAM across a GC cycle.  The χ-Bridge
protocol enforces this with `GC_PAUSE` / `GC_RESUME` messages.

```lisp
;; GC fence protocol
(defun gc-collect-cluster (cluster)
  ;; Notify Σ-Kernel: "don't touch graph DRAM"
  (bridge-send :sigma (make-gc-pause-msg
                        :region (cluster-old-gen-region cluster)
                        :estimated-us 500))
  ;; Run compaction via movement engines
  (let ((result (enq-scan (cluster-old-gen-region cluster))))
    (await-engine result)
    (let ((new-region (allocate-cluster-region cluster)))
      (enq-copy (cluster-old-gen-region cluster) new-region)
      (await-engine)
      (broadcast-gc-fence cluster)
      (enq-fixup (scan-result-pointers result)
                 (copy-result-forwarding))
      (await-engine)
      ;; Swap regions
      (release-cluster-region cluster (cluster-old-gen-region cluster))
      (setf (cluster-old-gen-region cluster) new-region)))
  ;; Resume
  (bridge-send :sigma (make-gc-resume-msg
                        :region (cluster-old-gen-region cluster))))
```

### 4.3 Actor Scheduler

Hierarchical work-stealing scheduler matching the Lispos design:

```
Global Queue (system-wide)
    │
    ├── Cluster 0 Queue
    │     ├── Tile 0 Local Queue  ← 4 HW threads consume from here
    │     ├── Tile 1 Local Queue
    │     ├── ...
    │     └── Tile 7 Local Queue
    │
    ├── Cluster 1 Queue
    │     └── ...
    └── ...
```

**Actor definition:**

```lisp
(defstruct actor
  id              ; unique fixnum ID
  mailbox         ; ref to message queue (or hardware queue ID 0–3)
  behavior        ; closure — the actor's message handler
  state           ; private mutable state (Lisp object)
  priority        ; 0=System 1=Interactive 2=Normal 3=Background 4=Idle
  affinity        ; tile or cluster ID, or nil (any)
  status)         ; :running  :waiting  :suspended  :dead
```

**Scheduling loop (per tile, each of 4 HW threads):**

```lisp
(defun tile-scheduler-loop (tile-env)
  (loop
    (let ((actor (or (dequeue (tile-env-local-actor-queue tile-env))
                     (steal-from-cluster (tile-env-cluster tile-env))
                     (steal-from-global))))
      (when (null actor)
        (idle-wait)       ; wait for IPI or queue non-empty
        (continue))
      ;; Run the actor
      (let* ((msg (recv-blocking (actor-mailbox actor)))
             (result (funcall (actor-behavior actor)
                              (actor-state actor)
                              msg)))
        (match result
          ((:continue new-state)
           (setf (actor-state actor) new-state)
           (enqueue actor (tile-env-local-actor-queue tile-env)))
          ((:stop)
           (setf (actor-status actor) :dead))
          ((:send target msg)
           (send target msg)
           (enqueue actor (tile-env-local-actor-queue tile-env)))
          ((:become new-fn)
           (setf (actor-behavior actor) new-fn)
           (enqueue actor (tile-env-local-actor-queue tile-env)))
          ((:suspend)
           (setf (actor-status actor) :suspended)))))))
```

### 4.4 Knowledge Graph Engine

The graph is partitioned across LM-1 tiles by entity-ID hash.  Each
tile owns a local adjacency structure in its 256 KiB SRAM with overflow
to cluster shared SRAM and DRAM.

```lisp
;; Core data structures
(defstruct entity
  id                 ; stable identifier (fixnum or symbol)
  type               ; :user  :host  :process  :file  :network  :cert  ...
  attributes         ; alist of (key . value) pairs
  evidence-refs)     ; list of evidence block sequence numbers

(defstruct edge
  source             ; entity-id
  target             ; entity-id
  type               ; :auth  :spawn  :access  :transfer  :escalate  ...
  weight             ; fixnum (confidence or count)
  timestamp          ; MP64 cycle counter value
  evidence-ref)      ; evidence block sequence number

(defstruct graph-partition
  tile-id            ; owning tile
  entities           ; hash-table: id → entity
  adjacency          ; hash-table: id → list of edges
  temporal-index     ; sorted vector of (timestamp . edge-ref) pairs
  stats)             ; node-count, edge-count, memory-used

;; Query API (invoked from Σ-Kernel via χ-Bridge)

(defun query-path (graph from-id to-id &key (max-depth 10))
  "Parallel BFS across tiles.  Each tile explores local partition,
   cross-partition edges generate SEND to owning tile's graph actor."
  (let ((frontier (list from-id))
        (visited (make-hash-table))
        (parent (make-hash-table)))
    (loop for depth from 0 below max-depth
          while frontier do
      (let ((next-frontier '()))
        (dolist (node frontier)
          (unless (gethash node visited)
            (setf (gethash node visited) t)
            (when (= node to-id)
              (return-from query-path
                (reconstruct-path parent from-id to-id)))
            ;; Local edges
            (dolist (edge (local-neighbors node))
              (push (edge-target edge) next-frontier)
              (setf (gethash (edge-target edge) parent) node))
            ;; Remote edges → SEND to owning tile
            (dolist (edge (remote-neighbors node))
              (send (tile-for-entity (edge-target edge))
                    (make-bfs-msg :node (edge-target edge)
                                  :depth (1+ depth)
                                  :parent node)))))
        (setq frontier next-frontier)))))

(defun query-neighborhood (graph entity-id &key (depth 2) time-range)
  "Return subgraph within N hops, optionally time-filtered.")

(defun query-timeline (graph entity-id t1 t2)
  "All edges involving entity between timestamps t1 and t2.
   Uses temporal-index for efficient range scan.")

(defun score-anomalies (graph pattern-set)
  "Score subgraph motifs matching patterns, return ranked findings.")
```

### 4.5 Rule Engine

Declarative rule DSL compiled to graph traversal actor programs.

```lisp
;; Rule definition
(defmacro defrule (name &key description pattern action)
  "Define a detection rule.  PATTERN is compiled to a graph query plan.
   ACTION creates a finding with evidence references."
  `(register-rule
     (make-rule :name ',name
                :description ,description
                :query-plan (compile-pattern ',pattern)
                :action-fn (lambda (bindings) ,action))))

;; Example rules
(defrule suspicious-lateral-movement
  :description "User authenticates to >3 hosts within 5 minutes"
  :pattern
    (match-sequence
      (auth-event ?user ?host1 ?t1)
      (auth-event ?user ?host2 ?t2 :where (< (- ?t2 ?t1) 300))
      (auth-event ?user ?host3 ?t3 :where (< (- ?t3 ?t1) 300))
      :constraint (distinct ?host1 ?host2 ?host3))
  :action
    (create-finding :type :lateral-movement
                    :entities (list ?user ?host1 ?host2 ?host3)
                    :evidence (list ?t1-event ?t2-event ?t3-event)
                    :severity :high))

(defrule privilege-escalation
  :description "Role grant followed by admin action within 1 minute"
  :pattern
    (match-sequence
      (role-grant ?user ?role ?t1 :where (admin-role? ?role))
      (admin-action ?user ?action ?t2 :where (< (- ?t2 ?t1) 60)))
  :action
    (create-finding :type :privilege-escalation
                    :entities (list ?user)
                    :evidence (list ?t1-event ?t2-event)
                    :severity :critical))

;; Rule compiler: DSL → graph traversal actors
(defun compile-pattern (pattern)
  "Transform a declarative pattern into a DAG of actor-spawning operations.
   Each match clause becomes a graph query step; constraints become filters."
  (let ((steps (parse-match-clauses pattern)))
    (make-query-plan
      :steps steps
      :parallelism (compute-parallelism steps)
      :estimated-tiles (estimate-tile-count steps))))

;; Rule execution
(defun run-ruleset (ruleset-name)
  "Load and execute all rules in a named rule set.
   Each rule spawns a set of traversal actors.
   Findings are collected and deduplicated."
  (let ((rules (lookup-ruleset ruleset-name))
        (findings '()))
    (dolist (rule rules)
      (let ((results (execute-query-plan (rule-query-plan rule))))
        (dolist (binding results)
          (push (funcall (rule-action-fn rule) binding) findings))))
    (deduplicate-findings findings)))
```

### 4.6 Similarity Engine

MinHash and clustering using MP64 SIMD tile engines via χ-Bridge
dispatch.  The λ-Runtime orchestrates the algorithm; the Σ-Kernel
executes the vector math.

```lisp
(defun minhash-fingerprint (document-tiles)
  "Compute MinHash fingerprint by dispatching SIMD work to Σ-Kernel."
  (let ((hash-buf (make-array 128 :element-type 'fixnum)))
    (dotimes (i 128)
      (bridge-send :sigma
        (make-simd-req :op :tmul-tmin
                       :src document-tiles
                       :seed (aref *hash-seeds* i)))
      (setf (aref hash-buf i)
            (bridge-recv-result :sigma)))
    hash-buf))

(defun jaccard-similarity (hash-a hash-b)
  "Estimate Jaccard similarity from MinHash signatures."
  (let ((matches 0))
    (dotimes (i 128)
      (when (= (aref hash-a i) (aref hash-b i))
        (incf matches)))
    (/ matches 128.0)))

(defun cluster-entities (entity-list &key (threshold 0.3))
  "Cluster entities by similarity.  Distance matrix via SIMD, assignment in Lisp."
  (let* ((fingerprints (mapcar #'entity-fingerprint entity-list))
         (n (length fingerprints))
         ;; Dispatch pairwise distance computation to Σ-Kernel SIMD
         (dist-matrix (bridge-send :sigma
                        (make-distance-matrix-req :fingerprints fingerprints))))
    ;; Single-linkage clustering in Lisp
    (hierarchical-cluster dist-matrix n threshold)))
```

---

## 5. χ-Bridge — Cross-Domain Protocol

### 5.1 Message Envelope

All cross-domain communication uses a 64-byte envelope that fits in one
tile and one hardware mailbox message.

```
Offset  Size   Field
  0      8     source_id       MP64 core ID  or  LM-1 tile.thread ID
  8      8     dest_id         target core/tile.thread  or  service ID
 16      4     msg_type        see table below
 20      4     flags           bit0=needs-reply  bit1=priority
 24      8     payload_len     0–32 bytes inline, or DRAM pointer
 32     32     payload         inline data  or  (8-byte DRAM addr + 24 reserved)
```

### 5.2 Message Types

| Code | Mnemonic | Direction | Purpose |
|:----:|----------|:---------:|---------|
| `0x01` | `WORK_REQ` | Σ→λ | Submit graph/rule/similarity job |
| `0x02` | `WORK_RESP` | λ→Σ | Job result + DRAM pointer |
| `0x03` | `CRYPTO_REQ` | λ→Σ | Hash/encrypt/sign request |
| `0x04` | `CRYPTO_RESP` | Σ→λ | Crypto result |
| `0x05` | `GC_PAUSE` | λ→Σ | "Don't touch DRAM region X" |
| `0x06` | `GC_RESUME` | λ→Σ | "Region X is safe" |
| `0x07` | `EVID_WITNESS` | Σ→λ | "New evidence block sealed, here's its hash" |
| `0x08` | `EVID_QUERY` | λ→Σ | Request evidence block by index |
| `0x09` | `EVID_DATA` | Σ→λ | Evidence block content (DRAM pointer) |
| `0x0A` | `STATUS_REQ` | Either | Health/metrics query |
| `0x0B` | `STATUS_RESP` | Either | Metrics bundle |
| `0x0C` | `EVAL_REQ` | Σ→λ | Lisp form as S-expression string |
| `0x0D` | `EVAL_RESP` | λ→Σ | Result as string |
| `0x0E` | `SIMD_REQ` | λ→Σ | SIMD tile engine operation request |
| `0x0F` | `SIMD_RESP` | Σ→λ | SIMD result (acc value or DRAM pointer) |
| `0x10` | `SHUTDOWN` | Σ→λ | Orderly shutdown signal |

### 5.3 Σ-Kernel Bridge Words

```forth
\ === χ-Bridge: Forth side ===

: X-SEND ( msg-addr tile -- )
    \ Write 64-byte envelope to mailbox MMIO, fire IPI
    SWAP MBOX-REGION OVER 64 CMOVE
    IPI-SEND ;

: X-RECV ( buf -- n )
    \ Poll mailbox for inbound message, copy to buf
    MBOX-REGION OVER 64 CMOVE
    64 ;

: X-CALL ( msg-addr tile -- resp-addr )
    \ Synchronous: send request, block until reply
    DUP >R  X-SEND
    BEGIN  X-POLL  UNTIL
    R> X-RECV DROP
    RESP-BUF ;

\ === High-level cross-domain calls ===

: X-RESOLVE-ID ( entity-addr len -- stable-id )
    PACK-WORK-REQ  0 X-CALL            \ tile 0 hosts identity actor
    RESP-PAYLOAD @ ;

: X-GRAPH-QUERY ( query-str len -- result-addr )
    PACK-EVAL-REQ  0 X-CALL
    RESP-PAYLOAD @ ;

: X-INDEX-UPDATE ( buf -- )
    PACK-WORK-REQ  0 X-SEND ;          \ fire-and-forget

: LM1-EVAL ( str len -- )
    PACK-EVAL-REQ  0 X-CALL
    RESP-PAYLOAD TYPE ;                 \ print result

: LM1-STATUS ( -- )
    STATUS-REQ-MSG  0 X-CALL
    DECODE-STATUS-RESP .LM1-STATUS ;
```

### 5.4 λ-Runtime Bridge Functions

```lisp
(defun bridge-send (target msg)
  "Send a χ-Bridge message to the Σ-Kernel or another LM-1 service."
  (let ((envelope (make-bridge-envelope
                    :source (current-tile-thread-id)
                    :dest target
                    :msg-type (msg-type msg)
                    :payload (serialise-payload msg))))
    (hw-queue-send 0 envelope)))   ; queue 0 = bridge channel

(defun bridge-recv ()
  "Receive next χ-Bridge message (blocking)."
  (hw-queue-recv 0))

(defun bridge-dispatch-loop ()
  "Main bridge listener actor on tile 0."
  (loop
    (let* ((envelope (bridge-recv))
           (msg-type (envelope-msg-type envelope)))
      (case msg-type
        (#x01  ; WORK_REQ
         (dispatch-work (deserialise-work-req envelope)))
        (#x0C  ; EVAL_REQ
         (let* ((form (deserialise-eval-req envelope))
                (result (eval (read-from-string form))))
           (bridge-send :sigma
             (make-eval-resp :result (prin1-to-string result)))))
        (#x0E  ; SIMD response from Σ → forward to waiting actor
         (deliver-simd-result envelope))
        (otherwise
         (warn "Unknown bridge message type: ~X" msg-type))))))
```

### 5.5 Unified Registry

Both Forth words and Lisp services are registered in a shared name
table.  The registry maps string names to capabilities.

```forth
\ Σ-side registry
32 CONSTANT MAX-SERVICES
VARIABLE SVC-TABLE  MAX-SERVICES 3 * CELLS ALLOT
VARIABLE SVC-COUNT  0 SVC-COUNT !

\ Each entry: name-addr  name-len  handler-type  handler-data
\ handler-type: 0=forth-xt  1=lm1-actor  2=lm1-eval

: REGISTER-SERVICE ( name len type data -- )
    SVC-COUNT @  MAX-SERVICES >= ABORT" Service registry full"
    SVC-COUNT @ 4 *  CELLS SVC-TABLE +
    >R  R@ 3 CELLS + !  R@ 2 CELLS + !  R@ CELL+ !  R> !
    SVC-COUNT @ 1+ SVC-COUNT ! ;

: INVOKE-SERVICE ( name len args -- result )
    LOOKUP-SERVICE                     ( type data args )
    OVER 0= IF                         \ Forth XT
        DROP SWAP EXECUTE
    ELSE OVER 1 = IF                   \ LM-1 actor
        DROP SWAP PACK-WORK-REQ X-CALL
    ELSE                               \ LM-1 eval
        DROP SWAP PACK-EVAL-REQ X-CALL
    THEN THEN ;
```

This enables the operator interaction model:

```forth
\ From Forth REPL:
S" graph-query" S" (query-path graph 'user-42 'db-server)" INVOKE-SERVICE

\ Or the short form:
S" (query-timeline graph 'U42 t1 t2)" LM1-EVAL
```

And from Lisp:

```lisp
;; From Lisp:
(invoke-sigma-service "sha3-hash" evidence-buffer)
(invoke-sigma-service "evidence-seal" processed-buf)
```

---

## 6. Boot Sequence

```
Power-on Reset
│
├─── Phase 0: Hardware Init
│      MP64 Core 0 starts (mode 0, MP64 ISA)
│      BIOS Forth (291 words, 11K lines asm) runs
│      Stack, IVT, timer, UART initialised
│
├─── Phase 1: Σ-Kernel Load
│      BIOS loads ChimeraOS Σ-Kernel from NVMe/flash
│      Σ-Kernel Forth source evaluated by BIOS interpreter
│      HAL words installed (crypto, timer, mailbox, DRAM)
│      DRAM controller configured, zones allocated
│      Evidence engine initialised (empty chain)
│      Task scheduler started (32-slot)
│      Console/TUI available
│      ."  ChimeraOS Σ-Kernel v0.1 on MP64 (4F+12µ)" CR
│
├─── Phase 2: LM-1 Firmware Load
│      Σ-Kernel reads λ-Runtime image from NVMe
│      Writes image to DRAM graph zone (0x5000_0000+)
│      Configures bridge mailbox MMIO region
│
├─── Phase 3: λ-Runtime Boot
│      Σ-Kernel signals LM-1 Tile 0 via mailbox
│      Tile 0 starts (mode 1, LM-1 ISA)
│        ├── LM-1 BIOS: stack, nursery, card table, trap table
│        ├── Loads OS image from DRAM
│        ├── Installs production trap handlers
│        ├── Initialises GC (nursery + old-gen)
│        ├── Initialises object system (shapes, classes)
│        ├── Builds symbol table
│        ├── Starts actor scheduler
│        └── Spawns bridge-dispatch-loop actor on tile 0
│
├─── Phase 4: Multi-Tile Bringup
│      Tile 0 brings up remaining tiles:
│        for each tile 1..N:
│          ├── Configure SRAM regions (nursery, stacks)
│          ├── Install trap table via message
│          ├── Start tile scheduler thread
│          └── Add tile to available-tile pool
│      Tile 0 → Σ-Kernel: STATUS_RESP "N tiles online"
│
├─── Phase 5: Services Init
│      λ-Runtime spawns system actors:
│        ├── GC monitor actor
│        ├── Tile monitor actor
│        ├── Identity resolver actor
│        ├── Graph engine actor (one per tile for partitions)
│        ├── Rule engine coordinator actor
│        └── Similarity engine actor
│      Σ-Kernel registers cross-domain services in unified registry
│
└─── Phase 6: Operational
       ."  ChimeraOS v0.1 — 4 MP64 cores + N LM-1 tiles online" CR
       ."  Evidence chain: 0 blocks | Graph: empty | Rules: 0 loaded" CR
       ."  Type HELP for commands, SCREENS for TUI" CR
       Both subsystems operational
       χ-Bridge active
       Ingestion pipeline ready
```

---

## 7. Case Management

Each investigation is a first-class OS object with isolation guarantees.

```forth
\ === Case descriptor (128 bytes) ===
\   +0    name_addr        case name string
\   +8    name_len
\   +16   evid_chain_head  address of first evidence block for this case
\   +24   evid_count       number of evidence blocks
\   +32   dram_base        allocated DRAM region for transient data
\   +40   dram_size
\   +48   graph_part_id    LM-1 graph partition ID for this case
\   +56   status           0=open 1=sealed 2=exported
\   +64   created_ts       CYCLES at creation
\   +72   sealed_ts        CYCLES at seal (or 0)
\   +80   manifest_hash    SHA-3-256 of integrity manifest (32 bytes)
\   +112  reserved

8 CONSTANT MAX-CASES
VARIABLE CASE-TABLE   MAX-CASES 128 * ALLOT
VARIABLE CURRENT-CASE 0 CURRENT-CASE !
VARIABLE CASE-COUNT   0 CASE-COUNT !

: CASE-NEW ( name len -- )
    CASE-COUNT @ MAX-CASES >= ABORT" Max cases reached"
    CASE-COUNT @ 128 * CASE-TABLE +    ( name len desc-addr )
    >R
    R@ 8 + !  R@ !                     \ store name
    0 R@ 16 + !                         \ empty evidence chain
    0 R@ 24 + !                         \ zero blocks
    \ Allocate DRAM region for this case
    HEX 1000000 DRAM-ALLOT R@ 32 + !   \ 16 MiB per case
    HEX 1000000 R@ 40 + !
    \ Request graph partition from λ-Runtime
    R@ 0 + @  R@ 8 + @  X-CREATE-GRAPH-PARTITION
    R@ 48 + !
    0 R@ 56 + !                         \ status = open
    CYCLES R@ 64 + !
    R> CURRENT-CASE !
    CASE-COUNT @ 1+ CASE-COUNT ! ;

: CASE-OPEN ( name len -- )
    CASE-LOOKUP DUP 0= ABORT" Case not found"
    CURRENT-CASE ! ;

: CASE-SEAL ( -- )
    CURRENT-CASE @ DUP 0= ABORT" No active case"
    \ Generate integrity manifest
    DUP case-generate-manifest         ( case-desc manifest-hash )
    OVER 80 + 32 CMOVE                 \ store manifest hash
    1 SWAP 56 + !                      \ status = sealed
    CYCLES OVER 72 + ! DROP ;

: CASE-EXPORT ( -- )
    CURRENT-CASE @ DUP 0= ABORT" No active case"
    DUP 56 + @ 1 <> ABORT" Case must be sealed before export"
    \ Export to NVMe: evidence blocks + graph snapshot + manifest
    DUP case-export-evidence
    DUP case-export-graph              \ χ-Bridge: request graph serialisation
    DUP case-export-manifest
    2 SWAP 56 + !                      \ status = exported
    ." Case exported to NVMe." CR ;

: CASE-VERIFY ( -- )
    CURRENT-CASE @ DUP 0= ABORT" No active case"
    ." Verifying case integrity..." CR
    DUP case-verify-evidence           ( case flag1 )
    OVER case-verify-manifest          ( case flag1 flag2 )
    AND IF
        ." PASS: all evidence blocks and manifest verified." CR
    ELSE
        ." FAIL: integrity violation detected!" CR
    THEN DROP ;
```

---

## 8. Security Model

### 8.1 Evidence Integrity

* Evidence blocks reside in the write-once DRAM zone.  After
  `EVIDENCE-SEAL`, the DRAM controller hardware locks the address range
  (reads allowed, writes trap).
* Hash chains are verified periodically by a background Σ-Kernel task.
* Each case has an independent hash chain.  Cross-case contamination is
  impossible at the hardware level (separate DRAM regions).
* Every evidence block hashed by the λ-Runtime (e.g., graph-derived
  findings) includes a cross-domain witness: the Σ-Kernel independently
  hashes the block and both hashes must agree.

### 8.2 Case Compartmentalisation

* Each case gets a dedicated DRAM transient region + evidence region.
* LM-1 graph partitions are isolated: an actor in case A cannot access
  case B's graph partition.  Enforced via capability tokens in the
  actor's state.
* MP64 MPU (memory protection unit) CSRs can be configured per-core to
  restrict access to only the active case's DRAM region.

### 8.3 Crypto Transport

* All external API communication over TLS 1.3 (Σ-Kernel network stack).
* Post-quantum key exchange via KEM accelerator (ML-KEM-512).
* Evidence exports are AES-256-GCM encrypted with case-specific keys
  derived from TRNG + HKDF.

### 8.4 Air-Gap Mode

```forth
: AIR-GAP ( -- )
    0 NET-TX-EN!  0 NET-RX-EN!
    ." Network isolated. Import/export via NVMe only." CR ;

: AIR-GAP-OFF ( -- )
    1 NET-TX-EN!  1 NET-RX-EN!
    ." Network restored." CR ;
```

---

## 9. API Layer

External systems (including AI agents) interact with ChimeraOS via a
JSON-over-TLS API served by the Σ-Kernel network stack.

### 9.1 Endpoints

| Method | Path | Handler |
|--------|------|---------|
| `POST` | `/ingest` | Σ: `stage-acquire` → ingest pipeline |
| `POST` | `/query/path` | χ→λ: `query-path` |
| `POST` | `/query/timeline` | χ→λ: `query-timeline` |
| `POST` | `/query/neighborhood` | χ→λ: `query-neighborhood` |
| `POST` | `/rules/run` | χ→λ: `run-ruleset` |
| `GET`  | `/findings` | Σ+λ: current findings list |
| `GET`  | `/evidence/:id` | Σ: evidence block by sequence number |
| `POST` | `/case/new` | Σ: `CASE-NEW` |
| `POST` | `/case/seal` | Σ: `CASE-SEAL` |
| `GET`  | `/status` | Σ+λ: system health |

### 9.2 Response Envelope

Every response includes provenance:

```json
{
  "type": "query_result",
  "snapshot_id": "sha3:abc123...",
  "query_plan_hash": "sha3:def456...",
  "result": { ... },
  "evidence_refs": ["block:1234", "block:1235"],
  "replay_instructions": {
    "snapshot": "sha3:abc123...",
    "query": "(query-path graph 'user-42 'db-server)",
    "deterministic": true
  }
}
```

---

## 10. Component Size Estimates

| Component | Layer | Language | Lines (est.) |
|-----------|:-----:|----------|-------------:|
| HAL (drivers, crypto, MMIO) | Σ | Forth | ~1,200 |
| DRAM manager | Σ | Forth | ~400 |
| Task scheduler (32-slot, queues, stealing) | Σ | Forth | ~800 |
| Evidence engine | Σ | Forth | ~600 |
| Ingestion pipeline | Σ | Forth | ~500 |
| Network stack + TLS 1.3 (from KDOS) | Σ | Forth | ~1,400 |
| Storage + MP64FS (from KDOS) | Σ | Forth | ~500 |
| Console / TUI (11 screens) | Σ | Forth | ~700 |
| Case management | Σ | Forth | ~400 |
| API layer (JSON + dispatch) | Σ | Forth | ~500 |
| χ-Bridge (Forth side) | χ | Forth | ~600 |
| **Σ-Kernel total** | | | **~7,600** |
| | | | |
| Tile runtime (traps, threads, init) | λ | Lisp | ~1,200 |
| GC (3-gen, movement engine integration) | λ | Lisp | ~1,500 |
| Actor scheduler (hierarchical, stealing) | λ | Lisp | ~1,000 |
| Object system (shapes, classes, dispatch) | λ | Lisp | ~800 |
| χ-Bridge (Lisp side + serialisation) | χ | Lisp | ~600 |
| Knowledge graph engine | λ | Lisp | ~2,500 |
| Rule engine (DSL, compiler, matcher) | λ | Lisp | ~2,000 |
| Similarity engine (LSH, clustering) | λ | Lisp | ~800 |
| Object store (persistence) | λ | Lisp | ~600 |
| **λ-Runtime total** | | | **~11,000** |
| | | | |
| **ChimeraOS total** | | | **~18,600** |

### Reuse Breakdown

| Source | Lines Reused | % of ChimeraOS |
|--------|------------:|:--------------:|
| KDOS v1.1 verbatim (crypto, network, storage, TUI core) | ~4,400 | 24% |
| KDOS adapted (scheduler, buffers, pipeline) | ~1,200 | 6% |
| Lispos design docs → new Lisp | ~11,000 | 59% |
| New Forth (evidence, DRAM, bridge, case, API) | ~2,000 | 11% |

---

## 11. Testing Strategy

### 11.1 Test Categories

| Category | Count (target) | Approach |
|----------|:---------:|----------|
| Σ-Kernel unit tests | ~600 | Port applicable KDOS tests (1,258 existing), add evidence/DRAM/case tests |
| λ-Runtime unit tests | ~400 | LM-1 emulator test harness (test_phase*.py style) |
| χ-Bridge integration | ~100 | Round-trip message tests, serialisation, GC coordination |
| End-to-end pipeline | ~50 | Full ingestion → graph → rule → report flow |
| Evidence integrity | ~100 | Hash chain verification, write-once enforcement, cross-case isolation |
| **Total** | **~1,250** | |

### 11.2 Test Infrastructure

* **Σ-Kernel tests**: Run in the MP64 Python emulator (`megapad64.py`
  / `mp64_accel.cpp`).  Load ChimeraOS Forth source, execute test words.
* **λ-Runtime tests**: Run in the LM-1 Python emulator
  (`emu/lm1/execute.py`).  Cross-compile Lisp to LM-1, boot via BIOS.
* **Integration tests**: Run both emulators linked via a Python bridge
  that simulates the hardware mailbox.

---

## 12. Implementation Roadmap

| Phase | Milestone | Deliverable | Depends On |
|:-----:|-----------|-------------|-----------|
| **C-1** | Σ-Kernel boots on Chimera-1 (MP64 side) | HAL + scheduler + REPL | SoC Phase 1 |
| **C-2** | DRAM manager operational | `DRAM-ALLOT` / `EVID-ALLOT` working | SoC DRAM controller |
| **C-3** | Evidence engine | `EVIDENCE-SEAL` / `EVIDENCE-VERIFY` / chain | C-2, SHA-3 (done) |
| **C-4** | Single-source ingestion | NIC → parse → hash → seal pipeline | C-3, network (from KDOS) |
| **C-5** | λ-Runtime single-tile boot | Tile 0: trap table, GC, actors, REPL | LM-1 tile RTL |
| **C-6** | χ-Bridge round-trip | Σ→λ message, λ→Σ reply, `LM1-EVAL` | SoC bridge unit, C-5 |
| **C-7** | Identity resolution via χ | Σ sends entity → λ resolves → Σ gets ID | C-6 |
| **C-8** | λ-Runtime multi-tile | Work-stealing across N tiles | LM-1 cluster RTL |
| **C-9** | Knowledge graph (single tile) | Entity/edge store, BFS, timeline query | C-5 |
| **C-10** | Knowledge graph (multi-tile) | Partitioned graph, parallel BFS, SEND | C-8, C-9 |
| **C-11** | Rule engine | DSL, compiler, pattern matcher, findings | C-10 |
| **C-12** | Similarity engine | MinHash via SIMD dispatch, clustering | C-10, C-6 |
| **C-13** | Case management | `CASE-NEW` / `CASE-SEAL` / `CASE-EXPORT` | C-3, C-10 |
| **C-14** | API layer | TLS 1.3 JSON API, evidence receipts | C-11, C-12, C-13 |
| **C-15** | End-to-end detective box | Full pipeline: ingest → analyse → report | C-14 |
| **C-16** | Hardening + production | 1,250 tests, stress testing, docs | C-15 |

### Critical Path

```
SoC RTL ─── C-1 ─── C-2 ─── C-3 ─── C-4
                                        │
LM-1 RTL ── C-5 ─── C-6 ─── C-7       │
                      │                  │
              C-8 ─── C-9 ─── C-10 ─── C-11 ─── C-14 ─── C-15
                               │                   │
                               C-12 ───────────────┘
                               │
                               C-13 ───────────────┘
```

---

## 13. Open Questions

1. **Forth object model**: Should the Σ-Kernel adopt any Lisp-like
   tagged-word conventions for cross-domain data, or keep everything as
   raw 64-bit cells with explicit serialisation at the χ-Bridge?
   **Leaning toward**: raw cells + explicit serialisation.  Forth's
   strength is its simplicity; adding tags would complicate every word.

2. **Evidence block size**: Fixed 128-byte header + variable payload,
   or fixed-size blocks (e.g., 4 KiB) with padding?  Fixed-size
   simplifies the write-once DRAM allocator but wastes space for small
   evidence items.  **Leaning toward**: variable with 64-byte alignment.

3. **GC impact on ingestion**: During an LM-1 old-gen GC, the graph
   zone DRAM is fenced.  If this overlaps with a high-throughput
   ingestion burst, evidence blocks queue in the Σ-Kernel.  Do we need
   a backpressure signal to the NIC?  **Leaning toward**: yes — a
   `GC_PAUSE` message triggers NIC flow control (`XOFF`) until
   `GC_RESUME`.

4. **Rule engine expressiveness**: Is the match-sequence DSL sufficient,
   or do we need full Datalog / graph pattern matching?
   **Leaning toward**: start with match-sequence, add Datalog later as
   a compile target.

5. **µ-core utilisation**: The 12 µ-cores have no tile engines.  Should
   they run dedicated I/O tasks (packet parsing, NVMe DMA management,
   UART console) to free full cores for tile-heavy work?
   **Leaning toward**: yes — micro-clusters as a dedicated I/O fabric,
   with KDOS-style cluster dispatch words (`CLUSTER-ENABLE`,
   `HW-BARRIER-WAIT`, `SPAD`).

6. **λ-Runtime self-hosting**: Should the Lisp compiler eventually
   self-host on LM-1 (eliminating the Python cross-compiler)?
   **Leaning toward**: yes, milestone C-16+.  Not blocking for the
   Detective Box MVP.
