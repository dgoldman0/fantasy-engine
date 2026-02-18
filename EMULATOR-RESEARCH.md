# Emulator Research: MP64 (megapad) & LM-1 (lisp-machine-LM1)

Comprehensive architecture reference extracted from source code for writing a unified emulator.

---

## Part 1: MP64 (dgoldman0/megapad)

### 1.1 Architecture Overview

- **Word Size**: 64-bit registers, 8-bit byte-addressable memory
- **Encoding**: Variable-length bytecode, **1 to 11 bytes** per instruction
- **Register File**: 16 × 64-bit general-purpose registers (R0–R15)
- **Special Registers**: D (8-bit accumulator, 1802 legacy), T (8-bit), Q (1-bit output)
- **Flags**: 8-bit flag register — `[S I G P V N C Z]`
  - Z=zero, C=carry, N=negative, V=overflow, P=parity, G=greater-than, I=interrupt-enable, S=saturation
- **Program Counter**: Via register indirection — `pc = R[psel]`
- **Data Pointer**: Via register indirection — `rx = R[xsel]`
- **Stack Pointer**: Via register indirection — `sp = R[spsel]`
- **Privilege Levels**: 0 = supervisor, 1 = user (MPU enforces memory window in user mode)
- **Cores**: Up to 4 full cores + 12 micro-cores (3 clusters × 4)
- **Memory**: Flat byte array, configurable size (default 1 MiB), little-endian

### 1.2 Instruction Encoding

First byte: `[F:4][N:4]` — F = instruction family (0x0–0xF), N = sub-opcode/register/condition.

Two-register instructions pack both into byte 1: `[Rd:4][Rs:4]`.

#### Instruction Size Summary

| Family | Name | Typical Size | Notes |
|--------|------|:---:|-------|
| `0x0` | SYS | 1 | CALL.L = 2 bytes |
| `0x1` | INC | 1 | Register in low nibble |
| `0x2` | DEC | 1 | Register in low nibble |
| `0x3` | BR | 2 | + 1 signed offset byte |
| `0x4` | LBR | 3 | + 2 signed offset bytes (big-endian) |
| `0x5` | MEM | 2 | LD.D = 3 bytes (has offset) |
| `0x6` | IMM | 2–4 | LDI w/ EXT.IMM64 = 11 bytes |
| `0x7` | ALU | 2 | `[Rd:4][Rs:4]` |
| `0x8` | MEMALU | 1 | 1802-compatible D-register ops |
| `0x9` | I/O | 1 | Port input/output |
| `0xA` | SEP | 1 | Set program counter register |
| `0xB` | SEX | 1 | Set data pointer register |
| `0xC` | MULDIV | 2 | Multiply/divide |
| `0xD` | CSR | 2 | Control/status register access |
| `0xE` | MEX | 2–3 | Matrix/element extension (tile engine) |
| `0xF` | EXT | 1 | Prefix modifier (changes next instruction) |

#### EXT Prefix Modifiers

| Value | Name | Effect |
|-------|------|--------|
| 0 | EXT.IMM64 | Next LDI loads 64-bit immediate (8 LE bytes follow) |
| 6 | EXT.SKIP | Next BR becomes conditional skip (skip next instruction) |
| 8 | EXT.8 | Extended MEX ops (LOAD2D, STORE2D, VSHR, etc.) |

### 1.3 Complete Instruction Set

#### Family 0x0 — SYS (System)

| Opcode | Mnemonic | Description |
|--------|----------|-------------|
| `00` | IDL | Idle (wait for interrupt) |
| `01` | NOP | No operation |
| `02` | HALT | Halt CPU |
| `03` | RESET | Software reset |
| `04` | RTI | Return from interrupt (pop PC + flags) |
| `05` | RET | Return (pop PC, legacy 1802) |
| `06` | DIS | Disable interrupts + return |
| `07` | MARK | Push T, then T ← (X<<4)\|P |
| `08` | SAV | Store T at M(R(X)) |
| `09` | SEQ | Set Q output = 1 |
| `0A` | REQ | Reset Q output = 0 |
| `0B` | EI | Enable interrupts |
| `0C` | DI | Disable interrupts |
| `0D Rn` | CALL.L Rn | Push PC, jump to R[n] (2 bytes) |
| `0E` | RET.L | Pop PC (64-bit return) |
| `0F` | TRAP | Software trap (vector 6) |

#### Family 0x1/0x2 — INC/DEC

| Opcode | Mnemonic | Description |
|--------|----------|-------------|
| `1n` | INC Rn | R[n] += 1 |
| `2n` | DEC Rn | R[n] -= 1 |

#### Family 0x3 — BR (Short Branch)

`3c off8` — c = condition code (4-bit), off8 = signed 8-bit offset

#### Family 0x4 — LBR (Long Branch)

`4c hi lo` — c = condition code, hi:lo = signed 16-bit offset (big-endian)

#### Condition Codes (shared by BR/LBR/SKIP)

| Code | Name | Condition |
|:----:|------|-----------|
| 0 | AL | Always |
| 1 | EQ/Z | Z=1 |
| 2 | NE/NZ | Z=0 |
| 3 | CS/C | C=1 |
| 4 | CC/NC | C=0 |
| 5 | MI | N=1 |
| 6 | PL | N=0 |
| 7 | VS | V=1 |
| 8 | VC | V=0 |
| 9 | GT | G=1 |
| A | LE | G=0 |
| B | BQ | Q=1 |
| C | BNQ | Q=0 |
| D | SAT | S=1 |
| E | EF | External flags |
| F | NV | Never |

#### Family 0x5 — MEM (Scalar Load/Store)

| Sub | Mnemonic | Description |
|:---:|----------|-------------|
| 0 | LDN Rd,Rs | Rd = mem64[R[Rs]] |
| 1 | LDA Rd,Rs | Rd = mem64[R[Rs]], Rs += 8 |
| 2 | LDX Rd | Rd = mem64[R(X)] |
| 3 | LDXA Rd | Rd = mem64[R(X)], X += 8 |
| 4 | STR Rd,Rs | mem64[Rd] = R[Rs] |
| 5 | STXD Rd,Rs | mem64[Rd] = Rs, Rd -= 8 |
| 6 | LD.B Rd,Rs | Rd = mem8[R[Rs]] (zero-ext) |
| 7 | ST.B Rd,Rs | mem8[Rd] = R[Rs] & 0xFF |
| 8 | LD.H Rd,Rs | Rd = mem16[R[Rs]] (zero-ext) |
| 9 | ST.H Rd,Rs | mem16[Rd] = R[Rs] & 0xFFFF |
| A | LD.W Rd,Rs | Rd = mem32[R[Rs]] (zero-ext) |
| B | ST.W Rd,Rs | mem32[Rd] = R[Rs] & 0xFFFFFFFF |
| C | LD.SB Rd,Rs | Rd = sign_ext8(mem8[R[Rs]]) |
| D | LD.SH Rd,Rs | Rd = sign_ext16(mem16[R[Rs]]) |
| E | LD.SW Rd,Rs | Rd = sign_ext32(mem32[R[Rs]]) |
| F | LD.D Rd,Rs,off8 | Rd = mem64[R[Rs] + sext(off8)*8] (3 bytes) |

#### Family 0x6 — IMM (Immediate Operations)

| Sub | Mnemonic | Size | Description |
|:---:|----------|:----:|-------------|
| 0 | LDI Rn, imm8 | 3 | Rn = zext(imm8) |
| 1 | LHI Rn, imm16 | 4 | Rn[63:48] = imm16 |
| 2 | ADDI Rn, simm8 | 3 | Rn += sext(simm8), flags |
| 3 | ANDI Rn, imm8 | 3 | Rn &= imm8, flags |
| 4 | ORI Rn, imm8 | 3 | Rn \|= imm8, flags |
| 5 | XORI Rn, imm8 | 3 | Rn ^= imm8, flags |
| 6 | CMPI Rn, simm8 | 3 | flags ← Rn - sext(simm8) |
| 7 | SUBI Rn, simm8 | 3 | Rn -= sext(simm8), flags |
| 8 | LSLI Rn, imm4 | 2 | Rn <<= imm4 |
| 9 | LSRI Rn, imm4 | 2 | Rn >>>= imm4 (logical) |
| A | ASRI Rn, imm4 | 2 | Rn >>= imm4 (arithmetic) |
| B | ROLI Rn, imm4 | 2 | Rn = rotate_left(Rn, imm4) |
| C | GLO Rn | 2 | D = R[n][7:0] (supervisor) |
| D | GHI Rn | 2 | D = R[n][15:8] (supervisor) |
| E | PLO Rn | 2 | R[n][7:0] = D (supervisor) |
| F | PHI Rn | 2 | R[n][15:8] = D (supervisor) |

With `EXT.IMM64` prefix: `F0 60 Rx 8bytes` = LDI64 Rn, imm64 (11 bytes total)

#### Family 0x7 — ALU (Register-Register)

`7s DR` — s = sub-op, D = Rd, R = Rs. Result in Rd. 2 bytes.

| Sub | Mnemonic | Flags | Description |
|:---:|----------|-------|-------------|
| 0 | ADD Rd,Rs | ZCNVP | Rd += Rs |
| 1 | ADC Rd,Rs | ZCNVP | Rd += Rs + C |
| 2 | SUB Rd,Rs | ZCNVP | Rd -= Rs |
| 3 | SBB Rd,Rs | ZCNVP | Rd -= Rs - !C |
| 4 | AND Rd,Rs | ZP | Rd &= Rs |
| 5 | OR Rd,Rs | ZP | Rd \|= Rs |
| 6 | XOR Rd,Rs | ZP | Rd ^= Rs |
| 7 | CMP Rd,Rs | ZCNVPG | flags ← Rd - Rs (result discarded) |
| 8 | MOV Rd,Rs | — | Rd = Rs |
| 9 | NOT Rd,Rs | ZP | Rd = ~Rs |
| A | NEG Rd,Rs | ZCNVP | Rd = -Rs |
| B | SHL Rd,Rs | ZCN P | Rd <<= Rs (C = last bit out) |
| C | SHR Rd,Rs | ZCN P | Rd >>>= Rs (logical, C = last bit out) |
| D | SAR Rd,Rs | ZCN P | Rd >>= Rs (arithmetic, C = last bit out) |
| E | ROL Rd,Rs | ZNP | Rd = rotate_left(Rd, Rs) |
| F | ROR Rd,Rs | ZNP | Rd = rotate_right(Rd, Rs) |

#### Family 0x8 — MEMALU (1802-Compatible D-Register Ops)

Single-byte. All operate on the 8-bit D register and memory at R(X).

| Sub | Mnemonic | Description |
|:---:|----------|-------------|
| 0 | LDX | D = M(R(X)) |
| 1 | OR.X | D \|= M(R(X)) |
| 2 | AND.X | D &= M(R(X)) |
| 3 | XOR.X | D ^= M(R(X)) |
| 4 | ADD.X | D += M(R(X)), carry |
| 5 | SD.X | D = M(R(X)) - D |
| 6 | SHR.D | D >>= 1, C = old bit 0 |
| 7 | SM.X | D -= M(R(X)) |
| 8 | ADC.X | D += M(R(X)) + C |
| 9 | SDB.X | D = M(R(X)) - D - borrow |
| A | SHRC.D | D = (C<<7) \| (D>>1), C = old bit 0 |
| B | SMB.X | D -= M(R(X)) - borrow |
| C | SHL.D | C = D bit 7, D <<= 1 |
| D | SHLC.D | D = (D<<1) \| C, C = old bit 7 |
| E | IRX | R(X) += 1 |
| F | LDXA | D = M(R(X)), R(X) += 1 |

#### Family 0x9 — I/O

| Encoding | Description |
|----------|-------------|
| `91`–`97` | OUT1–OUT7: write M(R(X)) to port, R(X)++ |
| `99`–`9F` | INP1–INP7: read port to M(R(X)) and D |

#### Family 0xA/0xB — SEP/SEX

| Opcode | Description |
|--------|-------------|
| `An` | SEP Rn — set program counter register (psel = n) |
| `Bn` | SEX Rn — set data pointer register (xsel = n) |

#### Family 0xC — MULDIV

`Cs DR` — s = sub-op, 2 bytes.

| Sub | Mnemonic | Description |
|:---:|----------|-------------|
| 0 | MUL Rd,Rs | Rd = (int128)(Rd) * (int128)(Rs), low 64 bits |
| 1 | MULH Rd,Rs | Signed high 64 bits |
| 2 | UMUL Rd,Rs | Unsigned mul, low |
| 3 | UMULH Rd,Rs | Unsigned mul, high |
| 4 | DIV Rd,Rs | Signed divide |
| 5 | UDIV Rd,Rs | Unsigned divide |
| 6 | MOD Rd,Rs | Signed modulo |
| 7 | UMOD Rd,Rs | Unsigned modulo |

#### Family 0xD — CSR (Control/Status Register)

`Dn addr8` — n[3] = direction: 0=read (CSRR), 1=write (CSRW). n[2:0] = register index.

#### Family 0xE — MEX (Matrix/Element Extension)

Tile engine operations — SIMD on 64-byte tiles. Encoding: `En funct` where n encodes `[ss:2][op:2]`.

**TALU** (op=0): Element-wise ops — ADD, SUB, MUL, MIN, MAX, CMP, ABS, CLAMP
**TMUL** (op=1): Multiply variants — MUL, DOT, WMUL, MAC, FMA, DOTACC
**TRED** (op=2): Reductions — SUM, RMIN, RMAX, POPCNT, L1, SUMSQ, MINIDX, MAXIDX
**TSYS** (op=3): System — TRANS (transpose), SHUFFLE, MOVBANK, LOADC, ZERO, PACK, UNPACK

Extended (EXT.8 prefix): VSHR, VSHL, VSEL, VCLZ, LOAD2D, STORE2D

#### Family 0xF — EXT (Prefix)

`Fn` — sets modifier for the next instruction. n=0 is IMM64, n=6 is SKIP, n=8 is extended MEX.

### 1.4 CSR Register Map (Complete)

| Address | Name | Bits | R/W | Description |
|:-------:|------|:----:|:---:|-------------|
| `0x00` | FLAGS | 8 | RW | [S I G P V N C Z] |
| `0x01` | PSEL | 4 | RW | Program counter register selector |
| `0x02` | XSEL | 4 | RW | Data pointer register selector |
| `0x03` | SPSEL | 4 | RW | Stack pointer register selector |
| `0x04` | IVT_BASE | 64 | RW | Interrupt vector table base |
| `0x05` | D | 8 | RW | Legacy 1802 D register |
| `0x06` | DF | 1 | RW | Legacy 1802 DF (carry alias) |
| `0x07` | Q | 1 | RW | Legacy 1802 Q output |
| `0x08` | T | 8 | RW | Legacy 1802 T register |
| `0x09` | IE | 1 | RW | Interrupt enable alias |
| `0x0A` | PRIV | 1 | RW | Privilege level (0=S, 1=U) |
| `0x0B` | MPU_BASE | 64 | RW | MPU lower bound (supervisor-only) |
| `0x0C` | MPU_LIMIT | 64 | RW | MPU upper bound (supervisor-only) |
| `0x10` | SB | 64 | RW | Tile base for source B |
| `0x11` | SR | 64 | RW | Tile result address |
| `0x12` | SC | 64 | RW | Tile control |
| `0x13` | SW | 64 | RW | Tile width |
| `0x14` | TMODE | 64 | RW | Tile element width mode |
| `0x15` | TCTRL | 64 | RW | Tile control flags |
| `0x16` | TSRC0 | 64 | RW | Tile source 0 address |
| `0x17` | TSRC1 | 64 | RW | Tile source 1 address |
| `0x18` | TDST | 64 | RW | Tile destination address |
| `0x19` | ACC0 | 64 | RW | Accumulator word 0 |
| `0x1A` | ACC1 | 64 | RW | Accumulator word 1 |
| `0x1B` | ACC2 | 64 | RW | Accumulator word 2 |
| `0x1C` | ACC3 | 64 | RW | Accumulator word 3 |
| `0x20` | COREID | 64 | R | Core ID (0..N-1) |
| `0x21` | NCORES | 64 | R | Total number of cores |
| `0x22` | MBOX | 64 | RW | R: pending IPI mask, W: send IPI |
| `0x23` | IPIACK | 64 | W | Acknowledge IPI from core N |
| `0x24` | IVEC_ID | 8 | RW | Current interrupt/trap vector ID |
| `0x25` | TRAP_ADDR | 64 | R | Faulting address |
| `0x30` | MEGAPAD_SZ | 64 | R | Memory size in bytes |
| `0x31` | CPUID | 64 | R | CPU identification ("MP64") |
| `0x40` | TSTRIDE_R | 64 | RW | Row stride in bytes |
| `0x41` | TSTRIDE_C | 64 | RW | Column stride (reserved) |
| `0x42` | TTILE_H | 64 | RW | Tile height (1–8) |
| `0x43` | TTILE_W | 64 | RW | Tile width (1–64) |
| `0x50` | DMA_RING_BASE | 64 | RW | DMA descriptor ring base |
| `0x51` | DMA_RING_SIZE | 64 | RW | DMA ring size (power of 2) |
| `0x52` | DMA_HEAD | 64 | RW | DMA head pointer |
| `0x53` | DMA_TAIL | 64 | RW | DMA tail pointer |
| `0x54` | DMA_STATUS | 64 | R | DMA idle/busy/error |
| `0x55` | DMA_CTRL | 64 | RW | DMA enable/disable |
| `0x58` | QOS_WEIGHT | 64 | RW | Bus priority weight |
| `0x59` | QOS_BWLIMIT | 64 | RW | Bandwidth limit |
| `0x60` | BIST_CMD | 64 | W | Memory BIST: 0=idle, 1=full, 2=quick |
| `0x61` | BIST_STATUS | 64 | R | BIST result |
| `0x62` | BIST_FAIL_ADDR | 64 | R | First failing address |
| `0x63` | BIST_FAIL_DATA | 64 | R | Expected vs actual |
| `0x64` | TILE_SELFTEST | 64 | RW | Tile datapath self-test |
| `0x65` | TILE_ST_DETAIL | 64 | R | Failed sub-test bitmask |
| `0x68` | PERF_CYCLES | 64 | R | Total cycles since reset |
| `0x69` | PERF_STALLS | 64 | R | Stall cycles |
| `0x6A` | PERF_TILEOPS | 64 | R | MEX instructions completed |
| `0x6B` | PERF_EXTMEM | 64 | R | External memory beats |
| `0x6C` | PERF_CTRL | 64 | RW | Bit 0: enable, Bit 1: reset all |
| `0x6D` | CL_PRIV | 64 | RW | Cluster privilege level |
| `0x6E` | CL_MPU_BASE | 64 | RW | Cluster MPU base |
| `0x6F` | CL_MPU_LIMIT | 64 | RW | Cluster MPU limit |
| `0x70` | ICACHE_CTRL | 64 | RW | I-cache enable/invalidate |
| `0x71` | ICACHE_HITS | 64 | R | I-cache hit counter |
| `0x72` | ICACHE_MISSES | 64 | R | I-cache miss counter |
| `0x73` | CL_IVTBASE | 64 | RW | Cluster shared IVT base |
| `0x74` | BARRIER_ARRIVE | 64 | RW | Per-core barrier arrive mask |
| `0x75` | BARRIER_STATUS | 64 | R | Barrier done flag |

### 1.5 MMIO Memory Map

Base: `0xFFFF_FF00_0000_0000`

| Device | Base Address | Key Registers |
|--------|-------------|---------------|
| UART | +0x0000 | TX=+0, RX=+1, STATUS=+2 |
| Timer | +0x0100 | COUNT=+0..+3, CTRL=+8 |
| Storage | +0x0200 | SECTOR=+0, CMD=+8 |
| SysInfo | +0x0300 | NCORES=+0, MEM_SIZE=+8 |
| NIC | +0x0400 | CMD=+0, STATUS=+1 |
| Mailbox | +0x0500 | DATA=+0..7, SEND=+8, STATUS=+9, ACK=+A |
| Spinlock | +0x0600 | ACQUIRE=+N*4, RELEASE=+N*4+1 |
| CRC | +0x07C0 | POLY=+0, INIT=+8, DIN=+10, RESULT=+18 |
| AES | +0x0800 | KEY=+0..1F, IV=+20..2B |
| SHA3 | +0x0880 | ... |
| TRNG | +0x08C0 | ... |
| X25519 | +0x0840 | ... |
| NTT | +0x0900 | ... |
| KEM | +0x0940 | ... |
| Framebuffer | +0x0A00 | ... |

### 1.6 Interrupt Vectors (IVT)

| Vector | Name | Trigger |
|:------:|------|---------|
| 0 | RESET | Reset |
| 1 | NMI | Non-maskable interrupt |
| 2 | ILLEGAL_OP | Invalid opcode |
| 3 | ALIGN_FAULT | Alignment error |
| 4 | DIV_ZERO | Division by zero |
| 5 | BUS_FAULT | Bus error |
| 6 | SW_TRAP | TRAP instruction |
| 7 | TIMER | Timer interrupt |
| 8 | IPI | Inter-processor interrupt |
| 15 | PRIV_FAULT | Privilege violation |

Trap delivery: push (flags | priv<<8), push PC, clear IE, set priv=0, jump to `mem64[ivt_base + ivec_id * 8]`.

### 1.7 Python Emulator Structure (megapad64.py)

```python
class Megapad64:
    # State
    regs: list[int]           # 16 × 64-bit registers
    mem: bytearray            # flat byte-addressable memory
    mem_size: int
    d_reg: int                # 8-bit D accumulator
    t_reg: int                # 8-bit T register
    q_out: int                # 1-bit Q output
    psel: int                 # PC register selector (4-bit)
    xsel: int                 # X register selector (4-bit)
    spsel: int                # SP register selector (4-bit)
    flag_z, flag_c, flag_n, flag_v, flag_p, flag_g, flag_i, flag_s: int
    ivt_base: int             # IVT base address
    priv_level: int           # 0=supervisor, 1=user
    halted: bool
    idle: bool
    cycle_count: int
    _ext_modifier: int        # EXT prefix state (-1 = none)

    # Tile engine state
    tsrc0, tsrc1, tdst: int   # tile source/dest addresses
    tmode, tctrl: int         # tile mode/control
    acc: list[int]            # 4 × 64-bit accumulators

    # Performance counters
    perf_enable: int
    perf_cycles, perf_stalls, perf_tileops, perf_extmem: int

    def step(self) -> int:
        """Execute one instruction, returns cycle count."""
        byte0 = self.fetch8()
        f = (byte0 >> 4) & 0xF  # family
        n = byte0 & 0xF         # operand nibble

        # Handle EXT prefix
        if f == 0xF:
            self._ext_modifier = n
            byte0 = self.fetch8()
            f, n = (byte0 >> 4) & 0xF, byte0 & 0xF

        # Privilege check
        if self.priv_level and f in _PRIV_FAMILIES:
            raise TrapError(IVEC_PRIV_FAULT)

        # Dispatch by family
        match f:
            case 0x0: self._exec_sys(n)
            case 0x1: self._exec_inc(n)
            case 0x2: self._exec_dec(n)
            # ... through 0xE

        self._ext_modifier = -1
        self.cycle_count += cycles
```

### 1.8 C++ Accelerator (mp64_accel.cpp)

**Build**: pybind11 extension module, compiled with `-std=c++17 -O3 -march=native`.

**Architecture**: Mirrors the Python emulator exactly but in C++. Exposes two Python-callable functions:

1. `step_one(state, mmio_read8, mmio_write8, on_output, csr_override, mmio_start, mmio_end) → cycles`
2. `run_steps(state, ..., max_steps) → RunResult{total_cycles, steps_executed, stop_reason}`

**CPUState struct** (flat, no virtual methods):

```cpp
struct CPUState {
    uint64_t regs[16];        // General registers
    uint8_t  psel, xsel, spsel;
    uint8_t  d_reg, t_reg, q_out;
    uint8_t  flag_z, flag_c, flag_n, flag_v, flag_p, flag_g, flag_i, flag_s;
    uint64_t ivt_base;
    int      ext_modifier;    // -1 = none
    uint8_t  ivec_id;
    uint64_t trap_addr;
    uint64_t cycle_count;
    uint8_t* mem;             // Direct pointer to memory
    size_t   mem_size;
    // ... tile, perf, BIST, I-cache, MPU, HBW fields ...
    bool halted, idle;
    uint8_t priv_level;
    uint64_t mpu_base, mpu_limit;
    // I/O ports
    uint8_t port_out[8], port_in[8];
};
```

**Key acceleration patterns**:
- Memory access via direct pointer arithmetic: `s.mem[addr % s.mem_size]`
- MMIO accesses call back to Python via `StepCallbacks` function pointers
- Complex MEX floating-point ops throw `"MEX_FALLBACK"` — caught by Python wrapper which falls back to pure-Python step
- Traps thrown as `std::runtime_error("TRAP:...")`, caught in `run_steps` loop which delivers via `do_trap()`

**Fallback mechanism** (accel_wrapper.py):

```python
class Megapad64:
    def step(self):
        try:
            return _accel.step_one(self._cs, ...)
        except RuntimeError as e:
            if "MEX_FALLBACK" in str(e):
                return self._step_python_fallback()
            raise

    def run_steps(self, max_steps):
        result = _accel.run_steps(self._cs, ..., max_steps=max_steps)
        # Handle MEX_FALLBACK by rewind + Python step + resume
```

### 1.9 Test Infrastructure

File: `test_megapad64.py` — pytest-based, tests every family:

```python
def test_sys(): ...     # NOP, HALT, SEQ/REQ, EI/DI, MARK/SAV/RET, CALL.L/RET.L, TRAP
def test_inc_dec(): ... # INC/DEC
def test_branch(): ...  # BR (short branch)
def test_lbr(): ...     # LBR (long branch)
def test_mem(): ...     # MEM (scalar load/store)
def test_imm(): ...     # IMM family
def test_alu(): ...     # ALU (register-register)
def test_memalu(): ...  # MEMALU (1802 compatibility)
def test_io(): ...      # I/O
def test_sep_sex(): ... # SEP/SEX
```

Plus `bench_accel.py` for Python-vs-C++ performance comparison.

Also has comprehensive Verilog testbenches: `tb_opcodes.v`, `tb_multicore_smoke.v`, `tb_cluster.v`, `tb_qos.v`.

---

## Part 2: LM-1 (dgoldman0/lisp-machine-LM1)

### 2.1 Architecture Overview

- **Word Size**: 64-bit tagged words everywhere
- **Encoding**: Fixed 32-bit instructions
- **Register File**: 32 × 64-bit registers (r0–r31)
- **Special Registers**: PC (64-bit), SP (64-bit), FP (64-bit), LR (64-bit)
- **No flags register** — conditional branches test register values directly
- **Tagged value system**: Every word is self-describing via low 3 bits
- **Multi-tile**: Each tile has its own memory, registers, threads
- **Multi-threaded**: Round-robin scheduling within a tile
- **GC support**: Hardware nursery allocation, write barriers, card table

### 2.2 Tagged Word Format

Every 64-bit word's type is determined by its low bits:

| Tag (bits 2:0) | Class | Test |
|:-:|:-:|:--|
| `xx0` | **Fixnum** | `(w & 1) == 0` — bit 0 is 0 |
| `001` | **General Ref** | `(w & 3) == 1` |
| `011` | **Cons Ref** | `(w & 7) == 3` |
| `101` | **Special** | `(w & 7) == 5` |
| `111` | **Header** | `(w & 7) == 7` (memory only) |

**Fixnum encoding**: `value << 1` (63-bit signed range). Add/sub work directly on tagged values.

**Ref encoding**:
```
 63      51 50                            3  2  1  0
┌──────────┬──────────────────────────────┬──┬─────┐
│ metadata │     address bits 50:3        │  │ 0 1 │
└──────────┴──────────────────────────────┴──┴─────┘
                                           │
                                      cons bit (bit 2)
```
Address extraction: `w & 0x0007_FFFF_FFFF_FFF8`

**Special immediates**:

| Value | Constant |
|:-----:|----------|
| `0x05` | NIL |
| `0x0D` | T |
| `0x15` | UNBOUND |
| `0x1D` | EOF |
| `0x25` | VOID |
| `0x2D` | UNDEFINED |
| `0x35` (& 0xFF) | Character (codepoint in bits 63:8) |
| `0x3D` (& 0xFF) | Single-float (IEEE 754 binary32 in bits 63:8) |

**Object Header** (memory only):
```
 63      56 55                   24 23    8  7     3  2  1  0
┌──────────┬───────────────────────┬────────┬────────┬────────┐
│  GC bits │      shape ID        │  size  │ hdr-sub│ 1  1  1│
└──────────┴───────────────────────┴────────┴────────┴────────┘
```

Header subtypes:

| Code | Type |
|:----:|------|
| 0 | Instance |
| 1 | Cons |
| 2 | Vector |
| 3 | Bytevector/String |
| 4 | Closure |
| 5 | Symbol |
| 6 | Bignum |
| 7 | Ratio |
| 8 | Double-float |
| 9 | Complex |
| 10 | Weak ref |
| 11 | Continuation |
| 12 | Port |
| 13 | Hash table |
| 14 | Foreign pointer |
| 15 | Shape descriptor |
| 31 | Extended |

### 2.3 Instruction Encoding

All instructions are **fixed 32-bit wide**. 6-bit opcode in bits 31:26.

#### Format R (Register-Register)
```
 31    26 25  21 20  16 15  11 10   6  5      0
┌────────┬──────┬──────┬──────┬──────┬─────────┐
│ opcode │  Rd  │  Rs1 │  Rs2 │ func │ (rsvd)  │
│  (6)   │  (5) │  (5) │  (5) │  (5) │  (6)    │
└────────┴──────┴──────┴──────┴──────┴─────────┘
```

#### Format I (Register-Immediate)
```
 31    26 25  21 20  16 15                    0
┌────────┬──────┬──────┬────────────────────────┐
│ opcode │  Rd  │  Rs1 │      imm16 (signed)    │
│  (6)   │  (5) │  (5) │         (16)           │
└────────┴──────┴──────┴────────────────────────┘
```

#### Format S (Store)
```
 31    26 25  21 20  16 15  11 10            0
┌────────┬──────┬──────┬──────┬───────────────┐
│ opcode │  Rs  │  Rt  │field │   imm11       │
│  (6)   │  (5) │  (5) │  (5) │    (11)       │
└────────┴──────┴──────┴──────┴───────────────┘
```

#### Format B (Branch)
```
 31    26 25  21 20  16 15                    0
┌────────┬──────┬──────┬────────────────────────┐
│ opcode │  Rs1 │  Rs2 │   offset16 (signed)    │
│  (6)   │  (5) │  (5) │      (16)              │
└────────┴──────┴──────┴────────────────────────┘
```
Offset is in **words** (multiply by 4 for byte offset).

#### Format X (Extended/Special)
```
 31    26 25                                  0
┌────────┬────────────────────────────────────┐
│ opcode │       26-bit raw payload           │
└────────┴────────────────────────────────────┘
```

#### Encoding helpers (from decode.py)

```python
def encode_r(opcode, rd, rs1, rs2, func=0):
    return (opcode<<26) | (rd<<21) | (rs1<<16) | (rs2<<11) | (func<<6)

def encode_i(opcode, rd, rs1, imm16):
    return (opcode<<26) | (rd<<21) | (rs1<<16) | (imm16 & 0xFFFF)

def encode_s(opcode, rs, rt, field, imm11=0):
    return (opcode<<26) | (rs<<21) | (rt<<16) | (field<<11) | (imm11 & 0x7FF)

def encode_b(opcode, rs1, rs2, offset16):
    return (opcode<<26) | (rs1<<21) | (rs2<<16) | (offset16 & 0xFFFF)

def encode_x(opcode, payload26):
    return (opcode<<26) | (payload26 & 0x03FFFFFF)
```

### 2.4 Complete Instruction Set

#### Family 1 — Tagged Arithmetic & Type Tests

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 0 | 000000 | I | TST Rd, Rs, #tag | Type test (tag in imm16[2:0]) → T or NIL |
| 1 | 000001 | I | TST.SHAPE Rd, Rs, #shape | Shape test → T or NIL |
| 2 | 000010 | R | ARITH_FIX | Tagged fixnum arithmetic (func selects op) |
| | | | func=0: ADD.FIX | Rd = Rs1 + Rs2 (tagged, overflow traps) |
| | | | func=1: SUB.FIX | Rd = Rs1 - Rs2 |
| | | | func=2: MUL.FIX | Rd = (Rs1>>1) * Rs2 |
| | | | func=3: DIV.FIX | Rd = tag((untag(Rs1) / untag(Rs2))) |
| 3 | 000011 | I | ADD.FIX.IMM | Rd = Rs1 + imm16 (pre-tagged imm) |
| 4 | 000100 | R | CMP_TAGGED | Tagged comparison |
| | | | func=0: CMP | Rd = fixnum(-1/0/1) |
| | | | func=1: EQ | Rd = T if Rs1==Rs2, else NIL |

TST tag constants: 0=FIXNUM, 1=REF, 2=CONS, 3=SPECIAL, 4=NIL, 5=CHAR, 6=SFLOAT, 7=HEADER

#### Family 2 — Allocation

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 8 | 001000 | X | ALLOC | Alloc fixed-size object (Rd, #words, #template) |
| 9 | 001001 | X | ALLOC.CONS | Alloc cons cell (Rd) |
| 10 | 001010 | X | ALLOCV | Alloc variable-size (Rd, Rs_length, #template) |
| 11 | 001011 | X | ALLOC.CLOSURE | Alloc closure (Rd, Rs_code, #env_size) |

#### Family 3 — Field Access with Barriers

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 16 | 010000 | I | LD | Rd = obj[field] (tagged load) |
| 17 | 010001 | I | LD.CAR/CDR | imm=0→car, imm=1→cdr |
| 18 | 010010 | S | ST | obj[field] = Rt (no barrier) |
| 19 | 010011 | S | ST.WB | obj[field] = Rt (write barrier) |
| 20 | 010100 | S | ST.CAR/CDR | cons car/cdr store |

#### Family 4 — Dynamic Dispatch

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 24 | 011000 | X | CALL.IC | Inline-cache call (argc, Rs_rcv, callsite) |
| 25 | 011001 | X | IC.INSTALL | Install IC entry (Rs_entry, callsite, shape) |
| 26 | 011010 | X | CALL.DIRECT | Direct call (Rs_entry) |
| 27 | 011011 | X | CALL.CLOSURE | Call closure (argc, Rs_closure) |
| 28 | 011100 | X | RET | Return from call |
| 29 | 011101 | X | TAILCALL.IC | Tail inline-cache call |
| 30 | 011110 | X | TAILCALL.DIRECT | Direct tail call |

#### Family 5 — Prefetch (no-ops in emulator)

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 32 | 100000 | I | PREFETCH.REF | Prefetch ref |
| 33 | 100001 | I | PREFETCH.FLD | Prefetch field |
| 34 | 100010 | I | PREFETCH.CDR | Prefetch cdr |
| 35 | 100011 | R | GATHER.PRE | Gather prefetch |

#### Family 6 — Concurrency & Messaging

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 36 | 100100 | S | SEND | Enqueue value to hardware queue |
| 37 | 100101 | I | RECV | Blocking dequeue from queue |
| 37 | 100101 | R | TRY.RECV | Non-blocking dequeue |
| 38 | 100110 | X | CAS.TAGGED | Compare-and-swap (Rd, Rs_addr, Rs_exp, Rt_new) |
| 39 | 100111 | R | FAA/FENCE | Fetch-and-add (func=0→FAA, func=31→FENCE.GC) |

#### Family 7 — Region/Bulk Ops

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 40 | 101000 | I | ENQ.SCAN | Enqueue scan |
| 41 | 101001 | I | ENQ.COPY | Enqueue copy |
| 42 | 101010 | R | ENQ.FIXUP | Enqueue fixup |
| 43 | 101011 | I | ENQ.COMPACT | Enqueue compact |

#### Supplementary Scalar & Control

| Opcode | Binary | Format | Mnemonic | Description |
|:------:|:------:|:------:|----------|-------------|
| 48 | 110000 | R | ARITH_RAW | Raw 64-bit arithmetic (func: 0=ADD,1=SUB,2=MUL,3=DIV,4=MOD) |
| 49 | 110001 | R | BITWISE | Bitwise ops (func: 0=AND,1=OR,2=XOR,3=SHL,4=SHR,5=ASR,6=NOT) |
| 50 | 110010 | I | LDR | Raw load (64-bit) |
| 51 | 110011 | S | STR | Raw store (64-bit) |
| 52 | 110100 | B | BR | Unconditional branch |
| 53 | 110101 | B | BR_COND | Conditional branch (Rs2 = condition type) |
| 54 | 110110 | — | PUSH_POP | func=0→PUSH, func=1→POP |
| 55 | 110111 | I | LI | Load immediate (sign-extended 16-bit) |
| 56 | 111000 | I | LUI | Load upper immediate (imm16 → bits 31:16) |
| 57 | 111001 | I | PUSH_MULTI | Push multiple (bitmask in imm16) |
| 58 | 111010 | I | POP_MULTI | Pop multiple (bitmask in imm16) |
| 59 | 111011 | I | LI32 | Load 32-bit immediate (next word = immediate) |
| 60 | 111100 | X | TRAP | Synchronous trap (code in payload) |
| 61 | 111101 | X | ERET | Return from trap |
| 62 | 111110 | X | SYS_INFO | sub: 0=TILE.ID, 1=THREAD.ID, 2=CYCLE, 3=TRAP_CAUSE, 4=TRAP_PC |
| 63 | 111111 | X | HALT_NOP | sub=0→HALT, sub=1→NOP |

#### Branch Conditions (BR_COND, encoded in Rs2/cond field)

| Code | Name | Condition |
|:----:|------|-----------|
| 0 | BR.T | Truthy (not nil and not 0) |
| 1 | BR.NIL | Value == NIL |
| 2 | BR.FIX.LT | Fixnum < 0 |
| 3 | BR.FIX.EQ | Value == 0 |
| 4 | BR.FIX.GT | Fixnum > 0 |
| 5 | BR.EQ | Word-equal to 0 |

### 2.5 Trap Codes

```python
TRAP_NOT_FIXNUM       = 0x01
TRAP_FIXNUM_OVERFLOW  = 0x02
TRAP_DIVIDE_BY_ZERO   = 0x03
TRAP_TYPE_MISMATCH    = 0x04
TRAP_NOT_REF          = 0x05
TRAP_NOT_CONS         = 0x06
TRAP_NOT_CLOSURE      = 0x07
TRAP_NURSERY_OVERFLOW = 0x10
TRAP_IC_MISS          = 0x20
TRAP_QUEUE_FULL       = 0x30
TRAP_QUEUE_EMPTY      = 0x31
TRAP_ENGINE_BUSY      = 0x40
TRAP_BARRIER_OVERFLOW = 0x50
TRAP_STACK_UNDERFLOW  = ...
TRAP_UNIMPLEMENTED    = ...

# Emulator-level I/O traps (not hardware)
EMU_TRAP_PUTCHAR = 0x80   # r1 = char to print
EMU_TRAP_GETCHAR = 0x81   # returned in r0
EMU_TRAP_BLOCK_IO = 0x82  # block device read/write
EMU_TRAP_BYTE_MEM = 0x83  # byte-level memory access
EMU_TRAP_INSTALL_TEMPLATES = 0x91
```

### 2.6 Memory Model

```python
class Memory:
    """Flat byte-addressable, backed by array of uint64."""
    _data: array.array('Q')  # array of 64-bit words
    _size: int               # total bytes (must be multiple of 8)

    def load_word(self, addr):   # 8-byte aligned, returns uint64
    def store_word(self, addr, val):
    def load_u32(self, addr):    # 4-byte aligned, for instruction fetch
    def store_u32(self, addr, val):
    def load_byte(self, addr):   # byte access via bit manipulation
    def store_byte(self, addr, val):
    def load_instructions(self, base, instructions: list[int]):
```

Memory layout (emulator defaults):
- Code/data: `0x0000` – variable
- Nursery: `0x30000` (192 KiB), size `0x10000` (64 KiB)
- Old-gen: `0x80000` (512 KiB), size `0x40000` (256 KiB)
- Stack: grows down from top of memory

### 2.7 Emulator Structure (execute.py)

```python
class ThreadContext:
    pc: int              # program counter
    sp: int              # stack pointer
    fp: int              # frame pointer
    lr: int              # link register
    regs: list[int]      # 32 × uint64
    halted: bool
    stalled: bool
    stall_queue: int
    tile_id: int
    thread_id: int
    cycle_count: int
    trap_table_base: int
    trap_cause: int
    trap_pc: int
    in_trap: bool
    header_templates: list[int]  # indexed by template ID
    np: int              # nursery pointer (bump allocator)
    nl: int              # nursery limit

class Emulator:
    mem: Memory
    threads: list[ThreadContext]
    thread: ThreadContext        # current thread
    tile_id: int
    ic_table: dict               # (callsite_pc, shape_id) → target_addr
    card_table: bytearray
    nursery_base, nursery_size: int
    oldgen_base, oldgen_size: int
    oldgen_ptr: int              # bump pointer into old-gen
    queues: list[deque]          # 4 hardware message queues
    trace: bool

    def run(self, max_instructions=0):
        while not t.halted:
            raw = mem.load_u32(t.pc)
            inst = decode(raw)
            next_pc = t.pc + 4
            try:
                next_pc = self._execute(inst, next_pc)
            except LM1Trap as trap:
                if trap.code == TRAP_NURSERY_OVERFLOW:
                    self._gc_collect()
                    next_pc = t.pc  # retry
                elif t.trap_table_base != 0:
                    # dispatch through trap table
                    ...
            t.pc = next_pc
            t.cycle_count += 1

    def _execute(self, inst, next_pc):
        op = inst.opcode
        # Giant match/if-elif on opcode
        if op == Op.ARITH_RAW: ...
        elif op == Op.BITWISE: ...
        # ... ~50 opcode handlers
        return next_pc

    def run_round_robin(self, max_instructions, quanta=1):
        """Multi-thread round-robin scheduler."""
        for each thread, execute up to quanta instructions

class Cluster:
    """Multi-tile cluster. Each tile is an Emulator instance."""
    tiles: list[Emulator]
```

### 2.8 C Acceleration (_accel_ext.c)

A CPython C extension (not pybind11) for the hot loop of scalar operations:

```c
static PyObject *
accel_step_n(PyObject *self, PyObject *args) {
    // Takes: regs buffer, memory buffer, pc, n_instructions
    // Returns: (new_pc, instructions_executed, halt_flag, trap_code)

    for (int i = 0; i < n; i++) {
        // Fetch 32-bit instruction from word-aligned memory
        uint32_t raw = ...;

        // Decode
        int opcode = (raw >> 26) & 0x3F;
        int rd     = (raw >> 21) & 0x1F;
        int rs1    = (raw >> 16) & 0x1F;
        int rs2    = (raw >> 11) & 0x1F;
        int func   = (raw >> 6)  & 0x1F;
        int16_t imm16 = (int16_t)(raw & 0xFFFF);

        switch (opcode) {
        case OP_ARITH_RAW: {
            uint64_t a = regs[rs1], b = regs[rs2];
            switch (func) {
                case 0: regs[rd] = a + b; break;
                case 1: regs[rd] = a - b; break;
                // ...
            }
            break;
        }
        case OP_BITWISE: ...
        case OP_LDR: ...
        case OP_STR: ...
        case OP_BR: ...
        case OP_BR_COND: ...
        case OP_LI: ...
        case OP_LUI: ...
        case OP_HALT_NOP: ...
        // Only handles scalar ops — tagged/alloc/dispatch fall back to Python
        default: trap_code = opcode; goto done;
        }
    }
}
```

Only accelerates a subset (scalar ALU, loads/stores, branches, LI/LUI, HALT). All tagged operations, allocation, dispatch, messaging fall through to Python.

### 2.9 GC Implementation

**Nursery**: Bump-pointer allocator. On overflow → `_gc_collect()`:
1. **Phase A**: Scan roots (registers, stack) — forward all nursery refs to old-gen via Cheney copying
2. **Card table scan**: Dirty cards in old-gen are scanned for inter-generational pointers
3. **Phase B**: Cheney scan — process copied objects in old-gen, forward their internal refs
4. **Reset**: Reset nursery pointer to base

**Write barrier** (`ST.WB`): If storing a nursery ref into an old-gen object, mark the card table.

### 2.10 Test Infrastructure

Tests organized by phase (matching the build plan):

| File | Phase | Tests |
|------|-------|-------|
| `test_phase1.py` | Scalar ops | ~20 tests: LI, LUI, LI32, arithmetic, bitwise, memory, branches, push/pop, sys_info |
| `test_phase2.py` | Tagged + alloc | ~20 tests: ALLOC, ALLOC.CONS, ALLOCV, ALLOC.CLOSURE, LD/ST, TST, TST.SHAPE, cons-list integration |
| `test_phase3.py` | Traps + GC | Trap dispatch, ERET, PUSH/POP.MULTI, write barrier, nursery GC survival |
| `test_phase4.py` | Dispatch | CALL.DIRECT, CALL.CLOSURE, RET, IC.INSTALL, CALL.IC, polymorphic IC |
| `test_phase5.py` | Concurrency | SEND/RECV/TRY.RECV, CAS.TAGGED, FAA, multi-thread, multi-tile |
| `test_phase6.py` | Assembler | Assembly → emulation integration tests |
| `test_phase7.py` | BIOS/I/O | Block device I/O, BIOS boot |

Test pattern (from test_phase1.py):
```python
@test("tagged_add_fix", batch="phase1_tagged")
def test_add_fix():
    emu = _emu()
    program = [
        encode_i(Op.LI, 1, 0, tag_fixnum(30) & 0xFFFF),   # r1 = fixnum(30)
        encode_i(Op.LI, 2, 0, tag_fixnum(12) & 0xFFFF),   # r2 = fixnum(12)
        encode_r(Op.ARITH_FIX, 3, 1, 2, 0),                # r3 = r1 + r2
        encode_x(Op.HALT_NOP, 0),                           # HALT
    ]
    _load_and_run(emu, program)
    assert untag_fixnum(emu.thread.regs[3]) == 42
```

Custom test harness (`lm1/testing/harness.py`) with `@test(name, batch=...)` decorator.

### 2.11 Assembler (asm.py)

Two-pass assembler:
- Pass 1: Collect labels, compute instruction sizes
- Pass 2: Emit 32-bit instruction words

```python
class Assembler:
    labels: dict[str, int]
    equ: dict[str, int]
    templates: list[tuple]

    def assemble(self, source: str, base: int = 0) -> bytes:
    def assemble_to_words(self, source: str) -> list[int]:
```

Supports: labels, `.equ`, `.org`, `.space`, `.word`, `.template`, all instruction mnemonics.

Special: `LI` auto-expands to `LI32` when immediate doesn't fit in 16 bits.

---

## Part 3: Comparison Summary

| Feature | MP64 | LM-1 |
|---------|------|------|
| Word size | 64-bit | 64-bit (tagged) |
| Instruction width | Variable (1–11 bytes) | Fixed 32-bit |
| Registers | 16 × 64-bit | 32 × 64-bit |
| Opcode encoding | 4-bit family + 4-bit sub | 6-bit opcode |
| Flags | 8-bit flag register (SIGPVNCZ) | No flags (test-and-branch) |
| PC model | Indirect via R[psel] | Direct PC register |
| Memory | Flat byte array | Flat 64-bit word array |
| Privilege | 2-level (supervisor/user + MPU) | Trap-based |
| Acceleration | C++ pybind11 (full ISA) | CPython C ext (scalar subset) |
| Special | Tile engine (SIMD), 1802 legacy | Tagged values, GC, IC dispatch |
| Multi-core | 4 full + 12 micro, IPI/mailbox | Multi-tile + multi-thread |
| Assembler | Python (asm.py) | Python (emu/lm1/asm.py) |
| Test framework | pytest | Custom @test harness |
