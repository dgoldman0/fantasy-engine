# Chimera-1 SoC Emulator — Roadmap

> Fantasy compute engine for the Cryptographic Detective Box.
> 13,200+ lines of Python, 411 tests, 15 commits on `master`.

---

## Phase 1 — Silicon Emulation ✅

Everything needed to execute code on the Chimera-1 SoC in software.

### Stage 1 — MP64 Core ✅
- [x] Full 64-bit ISA: 15 instruction families (ALU, MEM, IMM, BR, LBR, MUL/DIV, CSR, IO, SEP/SEX, INC/DEC, MEX)
- [x] Condition codes (AL/EQ/NE/CS/CC/MI/PL/VS/VC/GT/LE/BQ/BNQ)
- [x] Flag arithmetic (Z, C, N, V, P, G, I, S)
- [x] 16 general-purpose 64-bit registers with selectable PC (psel), SP (spsel), X (xsel)
- [x] CSR file (flags, psel, xsel, spsel, IVT, D, DF/Q, perf counters)
- [x] Interrupt delivery (IVT-based, maskable, with context save/restore)
- [x] Optional C-accelerated hot loop via ctypes

### Stage 2 — MEX Tile Engine + MMIO Devices ✅
- [x] MEX extended instruction family (field ALU, crypto, tile, packed ops)
- [x] UART (TX/RX FIFOs, status register, interrupt support)
- [x] Timer (compare-match, one-shot/periodic, IRQ)
- [x] Mailbox (inter-core message passing)

### Stage 3 — LM-1 Lisp Machine Core ✅
- [x] Tagged-pointer runtime (61-bit payload + 3-bit tag)
- [x] 7 tag types: fixnum, symbol, cons, closure, string, vector, float
- [x] Complete opcode set: stack, arithmetic, list ops, environment, control, I/O
- [x] Tail-call optimisation
- [x] Mark-compact GC with root scanning
- [x] Optional C-accelerated interpreter loop

### Stage 4 — Multi-Core + χ-Bridge ✅
- [x] MP64Cluster: N-core MP64 with shared memory
- [x] LM1Cluster: N-tile LM-1 with per-tile local memory
- [x] χ-Bridge: cross-cluster communication bus (doorbell + shared-memory regions)

### Stage 5 — Full System Integration ✅
- [x] Cross-cluster integration tests (MP64 ↔ LM-1 via bridge)
- [x] End-to-end workload tests

### Stage 6 — Crypto Accelerator Peripherals ✅
- [x] CRC-32 (IEEE 802.3)
- [x] AES-128/192/256 (ECB encrypt/decrypt, key expansion)
- [x] SHA-3 (224/256/384/512, SHAKE128/256, absorb/squeeze)
- [x] TRNG (entropy pool, CSPRNG, configurable output)
- [x] X25519 (scalar multiply on Curve25519, merged into FieldALU as mode 0)
- [x] NTT (number-theoretic transform for lattice crypto)
- [x] KEM (Kyber-style key encapsulation)
- [x] FieldALU (multi-mode: Curve25519 / configurable prime / binary extension)

### Stage 7 — OS-Facing Peripherals ✅
- [x] NIC with pluggable backends (loopback, tap)
- [x] Storage device (host-file-backed block I/O, DMA-ready)
- [x] SysInfo (CPU ID, core count, RAM size, feature bits)
- [x] MP64FS (simple on-disk filesystem)

### Stage 8 — GPU & GC Hardware ✅
- [x] DMA engine (memory-to-memory, device-to-memory, scatter/gather)
- [x] Framebuffer device (pixel modes, palette, vblank IRQ)
- [x] GC movement opcodes for LM-1 (hardware-assisted heap compaction)
- [x] Inline cache support for LM-1 (polymorphic dispatch acceleration)
- [x] Missing LM-1 ops (VECTOR-REF, VECTOR-SET!, STRING-REF, STRING-SET!, etc.)
- [x] New MP64 CSRs (performance counters, extended control)

---

## Phase 2 — SoC Wiring ✅

Connecting all the pieces into a single addressable system.

### Stage A — DeviceBus + MMIO Map ✅
- [x] Unified DeviceBus routing 15 MMIO devices to the MP64 address space
- [x] UART, Timer, Mailbox, Storage, SysInfo, NIC, DMA, Framebuffer
- [x] CRC, AES, SHA3, TRNG, FieldALU, NTT, KEM
- [x] ChimeraSoC top-level class wiring everything together

### Stage B — Timer IRQ Delivery ✅
- [x] Timer compare-match triggers IRQ on MP64 cores
- [x] IVT-based interrupt dispatch with context save/restore verified

### Stage C — Boot Protocol ✅
- [x] Reset vector at address 0
- [x] Boot ROM loading into memory
- [x] Storage-based program loading

### Stage D — Assembly BIOS ✅
- [x] Minimal hand-assembled BIOS with banner print
- [x] Timer ISR wired and tested
- [x] Full boot sequence verified end-to-end

---

## Phase 3 — Forth Operating Environment ✅

A self-hosted programming environment running on the emulated hardware.

### Stage E — Forth BIOS + Assembler ✅
- [x] Label-aware two-pass assembler (`MP64Asm`) wrapping `asm.py`
  - Labels, forward references, LDI64/LBR/BR fixup resolution
  - Data directives: `db`, `dw`, `dd`, `dq`, `ascii`, `asciiz`, `align`, `pad_to`
- [x] Subroutine-threaded Forth BIOS ROM builder (~2,300 lines)
  - `SEP 4` boot trick to free R0 as scratch (PC moved to R4)
  - `SPSEL=15` for `call.l`/`ret.l` return stack on R15
  - 60+ Forth words across 9 categories:
    - **Stack**: DUP DROP SWAP OVER ROT TUCK NIP PICK DEPTH
    - **Arithmetic**: + - * / MOD NEGATE ABS MIN MAX 1+ 1- 2* 2/
    - **Comparison**: = < > 0= 0< <>
    - **Logic**: AND OR XOR INVERT LSHIFT RSHIFT
    - **Memory**: @ ! C@ C! CELLS CELL+ FILL
    - **I/O**: EMIT KEY SPACE CR . .S
    - **Compiler**: : ; VARIABLE CONSTANT IMMEDIATE LITERAL [ ] EXIT
    - **Control**: IF ELSE THEN BEGIN UNTIL AGAIN WHILE REPEAT DO LOOP
    - **System**: HEX DECIMAL BASE STATE HERE LATEST BYE WORDS
  - Full outer interpreter (QUIT loop): prompt → read line → parse → find/compile/execute
- [x] 57 tests: assembler (14), build (5), boot (2), arithmetic (7), stack (5), colon defs (3), control flow (4), memory (2), I/O (5), system (4), logic (6)

---

## Phase 4 — OS Kernel (next)

Building ChimeraOS on top of the Forth environment and SoC hardware.

### Stage F — Multitasking Forth
- [ ] Cooperative multitasking (round-robin task switcher)
- [ ] Per-task data/return stacks and user variables
- [ ] `PAUSE`, `ACTIVATE`, `TASK`, `STOP` words
- [ ] Background task for timer tick / watchdog

### Stage G — Storage & Filesystem
- [ ] Block-based Forth screens (BLOCK / BUFFER / UPDATE / FLUSH)
- [ ] Integration with Storage MMIO device
- [ ] Simple file-like abstraction over MP64FS
- [ ] LOAD / THRU for executing Forth source from blocks

### Stage H — Crypto Primitives in Forth
- [ ] Forth words wrapping crypto MMIO devices (AES, SHA3, X25519, KEM)
- [ ] `SHA3-256` `AES-ENCRYPT` `X25519-SCALARMULT` `KEM-KEYGEN` `KEM-ENCAPS`
- [ ] TRNG-backed `RANDOM` word
- [ ] CRC32 word for integrity checks

### Stage I — Networking
- [ ] Forth words wrapping NIC MMIO (SEND-PACKET, RECV-PACKET)
- [ ] Minimal packet framing (Ethernet-like)
- [ ] Simple request/response protocol for AI agent communication
- [ ] Evidence ingestion channel

---

## Phase 5 — Detective Box Application (future)

The "facts with receipts" engine described in IDEA.md.

### Stage J — Evidence Store
- [ ] Append-only evidence block storage with integrity manifests
- [ ] Content-addressable hashing (SHA-3) for all ingested items
- [ ] Hash-chain tamper-evident ledger
- [ ] Snapshot / checkpoint support

### Stage K — Normalization & Identity Resolution
- [ ] Canonical event schema (entities, events, relations, attributes)
- [ ] Identity resolver (aliases → stable IDs)
- [ ] Timestamp normalisation and ordering
- [ ] Content fingerprinting (LSH / shingle sets)

### Stage L — Knowledge Graph
- [ ] Graph storage (nodes, edges, timestamps, weights, evidence refs)
- [ ] Path queries, neighborhood extraction, temporal slicing
- [ ] Anomaly scoring over graph motifs
- [ ] Deterministic subgraph extraction for any scope window

### Stage M — Rule Engine & Similarity
- [ ] Declarative rule language compiling to query plans
- [ ] Pattern matching over normalised events and graph edges
- [ ] Approximate similarity search and clustering
- [ ] Outlier detection on event rates and sequences

### Stage N — AI Agent Interface
- [ ] Structured API for AI agent queries
- [ ] Timeline / graph / finding / cluster bundle output formats
- [ ] Replay instructions and provenance metadata in every response
- [ ] Case file export with integrity seals

---

## Architecture Reference

```
┌──────────────────────────────────────────────┐
│                 ChimeraSoC                   │
│                                              │
│  ┌──────────┐   χ-Bridge   ┌──────────────┐ │
│  │ MP64     │◄────────────►│ LM-1 Cluster │ │
│  │ Cluster  │              │ (Lisp tiles) │ │
│  │ (N cores)│              │              │ │
│  └────┬─────┘              └──────────────┘ │
│       │                                      │
│  ┌────▼──────────────────────────────────┐   │
│  │           DeviceBus (MMIO)            │   │
│  ├───────┬───────┬───────┬───────┬──────┤   │
│  │ UART  │ Timer │ NIC   │ Store │ DMA  │   │
│  │ Mbox  │ FB    │ SysInf│ CRC   │ AES  │   │
│  │ SHA3  │ TRNG  │ Field │ NTT   │ KEM  │   │
│  └───────┴───────┴───────┴───────┴──────┘   │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │     Forth BIOS (subroutine-threaded) │    │
│  │     60+ words · outer interpreter    │    │
│  │     SEP 4 · SPSEL=15 · call.l/ret.l │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

### Register Conventions (Forth BIOS)
| Register | Role |
|----------|------|
| R0       | Scratch (freed by SEP 4) |
| R1       | Scratch / argument passing |
| R4       | Program counter (psel=4) |
| R7       | Scratch |
| R8       | UART TX base address |
| R9–R13   | Scratch / word addr / loop counters |
| R14      | Data stack pointer (DSP, grows down) |
| R15      | Return stack pointer (RSP, grows down, spsel=15) |

### Key Files
| Path | Lines | Purpose |
|------|-------|---------|
| `chimera/mp64/core.py` | 1,381 | MP64 CPU emulator |
| `chimera/lm1/core.py` | ~900 | LM-1 Lisp Machine emulator |
| `chimera/bios.py` | 2,311 | Forth BIOS ROM builder |
| `chimera/soc.py` | 209 | Top-level SoC wiring |
| `chimera/mp64/assembler.py` | 155 | Label-aware assembler |
| `chimera/mp64/asm.py` | 275 | Instruction encoding helpers |
| `chimera/devices/*.py` | ~2,500 | 15 MMIO peripherals |
| `tests/*.py` | 5,466 | 411 tests across 10 test files |
