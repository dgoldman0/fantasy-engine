# Unified SoC Design: Megapad-64 × LM-1

## 1. Design Goal

Merge the Megapad-64 (MP64) register-machine SoC and the LM-1 many-tile
Lisp processor into a single unified chip.  The result is a heterogeneous
SoC where:

* MP64 cores handle scalar computation, I/O, Forth-based tooling, crypto
  offload, and the SIMD tile engine.
* LM-1 tile clusters handle symbolic AI, knowledge-graph traversal,
  garbage-collected Lisp workloads, and actor-model concurrency.
* Both processor subsystems share a single address space, a single external
  DRAM bus, and a unified QoS messaging fabric.

---

## 2. High-Level Block Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Unified SoC — "Chimera-1"                        │
│                                                                          │
│  ┌─────────────────────────────┐   ┌──────────────────────────────────┐  │
│  │     MP64 Subsystem          │   │       LM-1 Subsystem             │  │
│  │                             │   │                                  │  │
│  │  ┌──────────┐ ┌──────────┐ │   │  ┌─────────────────────────┐     │  │
│  │  │ Core 0   │ │ Core 1   │ │   │  │  Cluster 0  (8 tiles)   │     │  │
│  │  │ + Tile 0 │ │ + Tile 1 │ │   │  ├─────────────────────────┤     │  │
│  │  └──────────┘ └──────────┘ │   │  │  Cluster 1  (8 tiles)   │     │  │
│  │  ┌──────────┐ ┌──────────┐ │   │  ├─────────────────────────┤     │  │
│  │  │ Core 2   │ │ Core 3   │ │   │  │  ...                    │     │  │
│  │  │ + Tile 2 │ │ + Tile 3 │ │   │  ├─────────────────────────┤     │  │
│  │  └──────────┘ └──────────┘ │   │  │  Cluster N  (8 tiles)   │     │  │
│  │  ┌────────────────┐        │   │  └─────────────────────────┘     │  │
│  │  │ µ-cluster 0-2  │        │   │                                  │  │
│  │  │ (12 µ-cores)   │        │   │  ┌──────────────┐               │  │
│  │  │ (no tile eng)  │        │   │  │  GC Movement │               │  │
│  │  └────────────────┘        │   │  │  Engines     │               │  │
│  │                             │   │  └──────────────┘               │  │
│  │  ┌──────────────────┐      │   │  ┌──────────────┐               │  │
│  │  │ Crypto Accels    │      │   │  │  VDI Display │               │  │
│  │  │ AES SHA3 NTT KEM │      │   │  │  Engine      │               │  │
│  │  │ TRNG CRC Field   │      │   │  └──────────────┘               │  │
│  │  └──────────────────┘      │   │                                  │  │
│  │  ┌──────────┐              │   │                                  │  │
│  │  │ SRAM     │              │   │  ┌──────────────┐               │  │
│  │  │ 4 banks  │              │   │  │ Tile SRAM    │               │  │
│  │  │ 1 MiB    │              │   │  │ 256 KiB/tile │               │  │
│  │  └──────────┘              │   │  │ 2 MiB/clust  │               │  │
│  │                             │   │  └──────────────┘               │  │
│  └──────────┬──────────────────┘   └──────────┬───────────────────────┘  │
│             │                                  │                         │
│  ┌──────────▼──────────────────────────────────▼───────────────────────┐ │
│  │                  Unified Interconnect Fabric                        │ │
│  │        (Extended from mp64_bus.v + LM-1 NoC mesh concepts)         │ │
│  │   Weighted Round-Robin  ·  QoS Virtual Channels  ·  Mailbox/IPI   │ │
│  └──────────┬──────────────────────────────────┬───────────────────────┘ │
│             │                                  │                         │
│  ┌──────────▼──────────┐            ┌──────────▼───────────────────────┐ │
│  │  Shared Peripherals │            │     External Memory Controller   │ │
│  │  UART  Timer  NIC   │            │  DDR5/DDR6 PHY  ·  Multi-channel │ │
│  │  Disk  SysInfo      │            │  ≥32 GiB  ·  ≥51.2 GB/s         │ │
│  │  Mailbox  Spinlocks │            │  (replaces both mp64_extmem +    │ │
│  └─────────────────────┘            │   LM-1 HBM controller)          │ │
│                                      └─────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  External I/O                                                     │   │
│  │  PCIe Gen5 x16  ·  100GbE  ·  NVMe  ·  USB/SPI bootstrap        │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Dual-ISA Mode: The Mode Bit

### 3.1 Problem Statement

The two ISAs differ fundamentally:

| Property | MP64 | LM-1 |
|----------|------|------|
| Instruction width | Variable, 1–11 bytes | Fixed, 32-bit |
| First-byte format | `[Family:4][N:4]` | `[Opcode:6][payload:26]` |
| GPRs | 16 (R0–R15) | 32 (r0–r31) |
| Condition model | 8-bit flags: S I G P V N C Z | No flags; compare → register |
| Data width | 64-bit, untagged | 64-bit, tagged words |
| Branch model | Flag-conditional: BR.Z, BR.C, LBR.* | Value-type-conditional: BR.NIL, BR.FIX.LT |
| Memory model | Flat SRAM banks, linear addressing | Nursery/heap/GC, card table, barriers |
| Pipeline depth | 2-stage (full), 2-stage (micro) | 6-stage, 4-thread FGMT |

### 3.2 Approach: Mode CSR

A CSR register `ISA_MODE` (we propose CSR address `0x70`) selects the
active decode mode for each hardware thread / core:

| ISA_MODE | Meaning |
|----------|---------|
| `0` | MP64 decode: variable-length, 16-GPR, flags-based |
| `1` | LM-1 decode: fixed-width, 32-GPR, tagged-word |

**Who sets it:**

* MP64 cores boot in mode 0 (default).
* LM-1 tiles boot in mode 1 — their BIOS/firmware sets it during tile init.
* A privileged `CSR` write can switch modes.  This enables an MP64 core to
  briefly enter LM-1 mode to inspect Lisp objects, or an LM-1 tile to run
  a short MP64 sequence for crypto offload.

### 3.3 Dual-Decode Front-End

Each execution pipeline contains *two* decoders wired to a mux:

```
                  ┌──────────────┐
  I-cache line →  │  MP64 Decode │──┐
                  │  (var-len)   │  │    ┌───┐
                  └──────────────┘  ├───►│MUX│──► Unified µ-ops
                  ┌──────────────┐  │    └─┬─┘
  I-cache line →  │  LM-1 Decode │──┘      │
                  │  (fixed 32b) │     ISA_MODE
                  └──────────────┘
```

Both decoders emit a common internal µ-op representation that feeds into
a shared execute stage.  This is feasible because both ISAs ultimately
operate on 64-bit registers, ALU operations, loads/stores, and branches.

### 3.4 Register File Unification

The physical register file is **32 × 64-bit** (the LM-1 requirement).
In MP64 mode, only R0–R15 are architecturally visible; the upper 16 are
reserved/zero/trap-scratch.  In LM-1 mode, all 32 are accessible.

A separate 8-bit flags register exists physically but is only written/read
in MP64 mode.  LM-1 instructions that need comparison results write them
to a destination register (the LM-1 way).

### 3.5 What Stays Separate

* **MP64 SIMD tile engines (4×, one per full core)** — each full core has
  its own `mp64_tile` instance driven via the MEX CSR family through
  dedicated per-core CSR/dispatch ports.  Micro-cores lack tile engines
  entirely (FAM_MEX traps as ILLEGAL_OP).  LM-1 cores can issue MEX
  instructions by briefly switching to mode 0, or via a thin MMIO shim.
* **LM-1 nursery/heap pointers** (np, nl, tp) — only meaningful in mode 1.
  In mode 0 these registers are simply GPR aliases (r28-r31) that the MP64
  side won't touch.
* **LM-1 inline cache / CALL.IC** — mode-1-only hardware.  MP64 uses
  CALL.L / RET.L which are different call-convention instructions.
* **GC barriers** — LM-1 store-with-barrier instructions (LDF/STF family)
  only fire barrier logic in mode 1.  In mode 0 they decode as normal
  loads/stores.

---

## 4. Unified Interconnect Fabric

### 4.1 Design Lineage

MP64 has a multi-master weighted round-robin bus arbiter (`mp64_bus.v`):

```verilog
parameter N_PORTS = 8;
// per-port QoS: CSR_QOS_WEIGHT, CSR_QOS_BWLIMIT
// valid/ready handshake, MMIO vs memory decode
```

LM-1 specifies a 2D mesh NoC with 3 virtual channels for QoS.

### 4.2 Combined Fabric: Hierarchical Mesh + Arbiter

```
 MP64 cores (4)  ──►┐  (each core incl. its   ┌───────────┐
 MP64 µ-clusters ──►┤   own tile engine)       │           │
 Crypto accels   ──►┤  Local Bus Ring          │  Bridge   │
                    └  (extended mp64_bus.v)  ──┤  Unit     │
                       weighted RR, N=7+       │           │
                                                │  Unit     │
 LM-1 clusters  ──►┐  Cluster-local mesh       │  (QoS     │
 LM-1 clusters  ──►┤  (per-cluster NoC)      ──┤  mapping, │
 LM-1 clusters  ──►┘  3 virtual channels       │  addr     │
                                                │  xlation) │
 Shared DRAM ctrl ◄─────────────────────────────┤           │
 Shared periph   ◄──────────────────────────────┤           │
                                                └───────────┘
```

**Bridge Unit** responsibilities:

* Translate MP64 bus transactions (valid/ready, address, data, burst) to
  NoC packets and vice versa.
* Map MP64 QoS weights onto NoC virtual channel priorities and LM-1
  cluster-level QoS onto bus weights.
* Provide a unified address map: both subsystems see the same physical
  address space.

### 4.3 Unified Address Map

| Range | Owner | Description |
|-------|-------|-------------|
| `0x0000_0000 – 0x000F_FFFF` | MP64 | Internal SRAM (4 banks, 1 MiB) |
| `0x0010_0000 – 0x001F_FFFF` | MP64 | MMIO peripherals (crypto, UART, timer, etc.) |
| `0x0100_0000 – 0x01FF_FFFF` | Shared | Mailbox / IPI region (both sides) |
| `0x1000_0000 – 0x1FFF_FFFF` | LM-1 | Tile SRAM window (per-tile 256 KiB) |
| `0x2000_0000 – 0x3FFF_FFFF` | LM-1 | Cluster shared SRAM window |
| `0x4000_0000 – 0xFFFF_FFFF` | Shared | External DRAM (DDR5/DDR6, ≥ 32 GiB) |

Both MP64 and LM-1 masters can issue transactions to the shared DRAM
range.  The external memory controller arbitrates using the same
weighted-QoS discipline.

### 4.4 QoS Policy

Unified QoS CSRs (extending `CSR_QOS_WEIGHT` and `CSR_QOS_BWLIMIT`):

| CSR | Function |
|-----|----------|
| `QOS_WEIGHT[port]` | Per-master weight (higher = more bandwidth) |
| `QOS_BWLIMIT[port]` | Bandwidth cap per time window |
| `QOS_VC_MAP[port]` | Virtual channel assignment for NoC traffic |
| `QOS_PRIORITY[port]` | Latency-sensitive priority level (0-3) |

The MP64 subsystem and each LM-1 cluster each appear as a "port" to the
top-level arbiter.

---

## 5. LM-1 as External-RAM Master

### 5.1 DDR5 PHY Requirements

LM-1's spec calls for HBM3E (4 stacks, 32 GiB, 1.6 TB/s).  For a unified
chip targeting a broader market, we consolidate to DDR5 (or DDR6 when
available):

| Parameter | Target |
|-----------|--------|
| Channels | 4 (quad-channel) |
| Capacity | 32–128 GiB |
| Bandwidth | ≥ 51.2 GB/s per channel (DDR5-6400) |
| Burst length | 16 (DDR5 native) |
| ECC | On-die ECC + host-side SECDED |

### 5.2 Memory Controller Architecture

Replace both `mp64_extmem.v` (generic PHY) and LM-1's HBM controller
with a single unified DRAM controller:

```
┌─────────────────────────────────────────────┐
│           Unified DRAM Controller            │
│                                              │
│  ┌──────────┐   ┌──────────┐                │
│  │ MP64 Port│   │ LM-1 Port│  (+ more ports)│
│  │ (req/ack)│   │ (req/ack)│                │
│  └─────┬────┘   └─────┬────┘                │
│        │               │                     │
│  ┌─────▼───────────────▼────┐               │
│  │   Arbiter (WRR + aging)  │               │
│  └───────────┬──────────────┘               │
│              │                               │
│  ┌───────────▼──────────────┐               │
│  │  Command Scheduler       │               │
│  │  (open-page, bank-group  │               │
│  │   interleaving, refresh) │               │
│  └───────────┬──────────────┘               │
│              │                               │
│  ┌───────────▼──────────────┐               │
│  │  PHY Interface            │               │
│  │  DDR5/DDR6 · 4 channels   │               │
│  └──────────────────────────┘               │
└─────────────────────────────────────────────┘
```

MP64's existing `mp64_extmem.v` interface (`phy_req`, `phy_addr`,
`phy_wen`, `phy_wdata`, `phy_burst_len`) can be retained as the
port-level protocol.  The LM-1 cluster NoC egress ports speak the same
protocol after address translation.

### 5.3 LM-1 Allocation in DRAM

In the original LM-1 design, HBM holds:

* Old-generation heap (post-nursery GC survivors)
* System image (compiled Lisp world)
* Large vectors and bulk data

This remains the same, except the backing store is DDR5/6 instead of HBM.
Bandwidth is lower but still adequate for the Detective Box workload profile
(graph traversal, not streaming ML inference).

The hardware GC movement engines (scanner/copier/fixup — specified in
`spec/05-memory-gc.md`) connect to the DRAM controller as DMA masters
with their own arbiter port and a high QoS weight.

---

## 6. Shared Messaging and Mailbox

### 6.1 MP64 Mailbox (Existing)

`mp64_mailbox.v` provides:

* 4-slot inter-core mailbox with IPI delivery
* 8 hardware spinlocks for mutual exclusion
* MMIO-mapped at standard addresses

### 6.2 Extension for LM-1

LM-1 tiles have hardware message queues (4 per tile, with SEND/RECV
instructions from ISA family F6).

To unify:

1. **Shared Mailbox Region** (`0x0100_0000`): Both MP64 and LM-1 can
   write/read mailbox slots via MMIO loads/stores.
2. **Cross-Domain IPI**: An MP64 core can post a message to an LM-1 tile's
   hardware queue by writing to the tile's queue MMIO address.  The bridge
   unit translates this into a NoC message packet.
3. **LM-1 → MP64**: An LM-1 tile issues `SEND` targeting a virtual tile ID
   that maps to an MP64 mailbox slot.  The bridge intercepts and writes
   the MP64 mailbox + fires IPI.

### 6.3 Message Format

A unified 64-byte message envelope:

```
Offset  Size   Field
  0      8     source_id       (MP64 core ID or LM-1 tile.thread ID)
  8      8     dest_id         (target core/tile.thread ID)
 16      8     msg_type        (IPI, DATA, GC_REQ, CRYPTO_REQ, ...)
 24      8     payload_len     (0–32 bytes)
 32     32     payload         (inline data or pointer to shared DRAM)
```

---

## 7. Crypto Accelerator Sharing

### 7.1 MP64 Crypto Block

From `rtl/periph/`: AES-256-GCM, SHA-3/SHAKE, CRC-32/64, TRNG,
multi-prime FieldALU, NTT engine, KEM engine.

### 7.2 Access from LM-1

The crypto accelerators are MMIO peripherals on the MP64 bus ring.  LM-1
accesses them through the bridge:

1. LM-1 tile issues a store to the crypto MMIO address range.
2. Bridge translates to an MP64 bus transaction.
3. Crypto block processes and posts result to a return MMIO address.
4. Bridge forwards the result back as a NoC response to the requesting tile.

For latency-critical crypto (evidence hashing during ingestion), a
dedicated DMA path from the DRAM controller to the SHA-3 engine avoids
the bridge entirely — the DRAM controller can stream data to SHA-3 at
line rate.

### 7.3 Crypto Instruction Aliases

In LM-1 mode, we reserve 4 opcode slots from the supplementary scalar
group as crypto instruction aliases:

| Opcode | Mnemonic | Effect |
|--------|----------|--------|
| `0x38` | `SHA3.INIT` | Write SHA3 mode CSR via bridge |
| `0x39` | `SHA3.UPDATE` | DMA buffer to SHA3 engine |
| `0x3A` | `AES.BLOCK` | Encrypt/decrypt one AES-GCM block |
| `0x3B` | `RANDOM` | Read TRNG into destination register |

These compile to short MMIO sequences internally, giving LM-1 Lisp code
ergonomic access to the crypto pipeline.

---

## 8. Peripheral Integration Summary

| Peripheral | Location | MP64 Access | LM-1 Access |
|------------|----------|-------------|-------------|
| UART | MP64 bus | Direct MMIO | Via bridge |
| Timer | MP64 bus | Direct MMIO | Via bridge (or per-tile timer) |
| NIC (100GbE) | Shared | Direct MMIO | Via bridge |
| NVMe/Disk | PCIe | DMA | DMA via bridge |
| VDI Display | LM-1 fabric | Via bridge | Direct |
| TRNG | MP64 bus | Direct | Via bridge / alias |
| Crypto (all) | MP64 bus | Direct | Via bridge / alias |
| Mailbox | Shared region | Direct | Direct (translated) |
| DRAM | Shared ctrl | Port 0 | Port 1+ |

---

## 9. Scaling Parameters

The SoC is parameterized for different product tiers:

| Parameter | Embedded | Standard | Full |
|-----------|----------|----------|------|
| MP64 full cores | 2 | 4 | 4 |
| MP64 µ-clusters | 1 | 3 | 3 |
| LM-1 clusters | 4 | 16 | 32 |
| LM-1 tiles total | 32 | 128 | 256 |
| DRAM channels | 1 | 2 | 4 |
| DRAM capacity | 4 GiB | 32 GiB | 128 GiB |
| Crypto accels | AES+SHA3 | Full suite | Full suite |
| Network | 1GbE | 10GbE | 100GbE |
| Process node | 28nm | 7nm | 5nm |
| Die area (est.) | ~50 mm² | ~200 mm² | ~500 mm² |

---

## 10. RTL Integration Plan

### 10.1 What Exists

* **MP64**: ~25K lines Verilog, 30 modules, 28 testbenches, ~414
  assertions.  Complete and tested.
* **LM-1**: Specification only (8 spec docs + design docs).  Python
  emulator (~3K lines).  No RTL yet.

### 10.2 Phase 1 — LM-1 Single-Tile RTL (New)

Write LM-1 RTL for one tile:

* 6-stage pipeline with dual-decode front-end (mode 0 / mode 1)
* 32 × 64-bit register file
* Tag-check hardware (bit masking, comparators for tag dispatch)
* Nursery bump allocator with trap-on-overflow
* Inline cache (2-entry direct-mapped per call site)
* 4 hardware message queues (64-entry each)
* 256 KiB tile SRAM (single-port for simplicity first)

Testbench: run the existing Python emulator test suite as golden reference.

### 10.3 Phase 2 — Bridge Unit

* MP64 bus ↔ NoC protocol translator
* Address map decoder
* QoS weight → virtual channel mapper
* Mailbox cross-domain translation

### 10.4 Phase 3 — Unified DRAM Controller

* Replace `mp64_extmem.v` generic PHY with a DDR5 controller IP
  (license or build from open-source DDR5 PHY)
* Multi-port arbiter with per-port QoS
* DMA interfaces for GC movement engines and crypto streaming

### 10.5 Phase 4 — Cluster + Multi-Tile

* Instantiate 8 tiles per cluster
* Cluster shared SRAM (2 MiB)
* Intra-cluster mesh (simple crossbar for 8 ports)
* GC movement engine per cluster

### 10.6 Phase 5 — Full SoC Integration

* Parameterized top-level: `chimera1_top.v`
* Wrap MP64 subsystem + LM-1 subsystem + bridge + DRAM + peripherals
* Full-chip testbench with dual-ISA boot sequence test

---

## 11. Boot Sequence

```
Power-on
  │
  ├── MP64 Core 0 starts (mode 0, MP64 ISA)
  │     ├── BIOS Forth initializes MP64 subsystem
  │     ├── Configures DRAM controller
  │     ├── Sets up mailbox and peripheral map
  │     └── Writes LM-1 bootstrap image to DRAM from NVMe/flash
  │
  ├── MP64 Core 0 signals LM-1 tile 0 via mailbox
  │
  └── LM-1 Tile 0 starts (mode 1, LM-1 ISA)
        ├── LM-1 BIOS initializes tile 0 (stack, nursery, trap table)
        ├── Loads Lisp system image from DRAM
        ├── Brings up remaining tiles
        ├── Starts actor scheduler
        └── Signals MP64 that LM-1 subsystem is ready
            │
            ▼
        Both subsystems operational
        Cross-domain messaging active
```

---

## 12. Open Questions

1. **Thread count per LM-1 tile**: The spec says 4-thread FGMT.  With the
   dual-decode front-end adding area, should we drop to 2 threads per tile
   to stay within area budget?

2. **Coherency**: Do we need cache coherence between MP64 SRAM and LM-1
   tile SRAMs?  Probably not — use explicit message-passing and DMA for
   cross-domain data movement (no snooping).

3. **DDR5 vs HBM**: DDR5 is chosen for cost/board simplicity.  If the
   Detective Box workload proves bandwidth-starved, HBM3E remains an
   option for the "Full" tier.  The controller interface is designed to
   be PHY-agnostic (same port protocol, different physical layer).

4. **Area budget for dual decode**: Two decoders per pipeline adds ~20%
   front-end area.  Acceptable if we keep LM-1 tile count flexible.

5. **Crypto DMA**: Should the SHA-3 engine have its own DRAM port, or
   share the MP64 subsystem port with high priority?  Depends on
   evidence-ingestion throughput targets.
