"""MP64 core emulator — full ISA implementation.

Implements the complete MP64 instruction set (families 0x0–0xF) with
optional C acceleration via ctypes.  MEX (tile engine) is stubbed
and filled in at Stage 3.
"""

from __future__ import annotations
import ctypes, os, struct
from pathlib import Path

MASK64 = 0xFFFF_FFFF_FFFF_FFFF
MASK32 = 0xFFFF_FFFF
MASK16 = 0xFFFF
MASK8  = 0xFF

# IVT vector IDs
IVEC_RESET       = 0
IVEC_NMI         = 1
IVEC_ILLEGAL_OP  = 2
IVEC_ALIGN_FAULT = 3
IVEC_DIV_ZERO    = 4
IVEC_BUS_FAULT   = 5
IVEC_SW_TRAP     = 6
IVEC_TIMER       = 7
IVEC_IPI         = 8
IVEC_PRIV_FAULT  = 15

# Condition codes
CC_AL  = 0   # always
CC_EQ  = 1   # Z=1
CC_NE  = 2   # Z=0
CC_CS  = 3   # C=1
CC_CC  = 4   # C=0
CC_MI  = 5   # N=1
CC_PL  = 6   # N=0
CC_VS  = 7   # V=1
CC_VC  = 8   # V=0
CC_GT  = 9   # G=1
CC_LE  = 10  # G=0
CC_BQ  = 11  # Q=1
CC_BNQ = 12  # Q=0
CC_SAT = 13  # S=1
CC_EF  = 14  # external flags
CC_NV  = 15  # never


class TrapError(Exception):
    """Raised internally to deliver a hardware trap."""
    def __init__(self, vector: int, addr: int = 0):
        self.vector = vector
        self.addr = addr


class MP64Core:
    """Single MP64 core emulator."""

    __slots__ = (
        "regs", "d", "t", "q", "psel", "xsel", "spsel",
        "flag_z", "flag_c", "flag_n", "flag_v", "flag_p",
        "flag_g", "flag_i", "flag_s",
        "mem", "mem_size",
        "ivt_base", "priv", "halted", "idle", "cycle_count",
        "core_id", "n_cores",
        "mpu_base", "mpu_limit",
        "ivec_id", "trap_addr",
        "tsrc0", "tsrc1", "tdst", "tmode", "tctrl", "acc",
        "tstride_r", "tstride_c", "ttile_h", "ttile_w",
        "perf_en", "perf_cycles", "perf_stalls",
        "perf_tileops", "perf_extmem",
        "port_in", "port_out",
        "on_output", "on_input",
        "mmio_read", "mmio_write", "mmio_start", "mmio_end",
        "_accel_lib", "_accel_state", "_accel_run",
    )

    def __init__(self, mem: bytearray, *, core_id: int = 0,
                 n_cores: int = 1):
        self.mem = mem
        self.mem_size = len(mem)
        self.regs = [0] * 16
        self.d = 0
        self.t = 0
        self.q = 0
        self.psel = 0
        self.xsel = 0
        self.spsel = 2  # R2 default SP
        # Flags
        self.flag_z = 0
        self.flag_c = 0
        self.flag_n = 0
        self.flag_v = 0
        self.flag_p = 0
        self.flag_g = 0
        self.flag_i = 0
        self.flag_s = 0
        # System
        self.ivt_base = 0
        self.priv = 0  # 0=supervisor
        self.halted = False
        self.idle = False
        self.cycle_count = 0
        self.core_id = core_id
        self.n_cores = n_cores
        # MPU
        self.mpu_base = 0
        self.mpu_limit = 0
        # Trap
        self.ivec_id = 0
        self.trap_addr = 0
        # Tile engine (stub)
        self.tsrc0 = 0
        self.tsrc1 = 0
        self.tdst = 0
        self.tmode = 0
        self.tctrl = 0
        self.acc = [0, 0, 0, 0]
        # Tile 2D
        self.tstride_r = 0
        self.tstride_c = 0
        self.ttile_h = 1
        self.ttile_w = 64
        # Perf
        self.perf_en = 0
        self.perf_cycles = 0
        self.perf_stalls = 0
        self.perf_tileops = 0
        self.perf_extmem = 0
        # I/O
        self.port_in = [0] * 8
        self.port_out = [0] * 8
        self.on_output = None
        self.on_input = None
        # MMIO
        self.mmio_read = None
        self.mmio_write = None
        self.mmio_start = 0xFFFF_FF00_0000_0000
        self.mmio_end = 0xFFFF_FF00_0001_0000
        # Acceleration
        self._accel_lib = None
        self._accel_state = None
        self._accel_run = None

    # -- properties -------------------------------------------------------
    @property
    def pc(self) -> int:
        return self.regs[self.psel]

    @pc.setter
    def pc(self, v: int):
        self.regs[self.psel] = v & MASK64

    @property
    def sp(self) -> int:
        return self.regs[self.spsel]

    @sp.setter
    def sp(self, v: int):
        self.regs[self.spsel] = v & MASK64

    # -- memory access ----------------------------------------------------
    def _r8(self, a: int) -> int:
        if self.mmio_start <= a < self.mmio_end:
            return self.mmio_read(a) & MASK8 if self.mmio_read else 0
        return self.mem[a % self.mem_size]

    def _w8(self, a: int, v: int):
        if self.mmio_start <= a < self.mmio_end:
            if self.mmio_write:
                self.mmio_write(a, v & MASK8)
            return
        self.mem[a % self.mem_size] = v & MASK8

    def _r16(self, a: int) -> int:
        if self.mmio_start <= a < self.mmio_end:
            return self._r8(a) | (self._r8(a + 1) << 8)
        o = a % self.mem_size
        return self.mem[o] | (self.mem[o + 1] << 8)

    def _w16(self, a: int, v: int):
        self._w8(a, v & MASK8)
        self._w8(a + 1, (v >> 8) & MASK8)

    def _r32(self, a: int) -> int:
        if self.mmio_start <= a < self.mmio_end:
            return (self._r8(a) | (self._r8(a + 1) << 8) |
                    (self._r8(a + 2) << 16) | (self._r8(a + 3) << 24))
        o = a % self.mem_size
        return struct.unpack_from("<I", self.mem, o)[0]

    def _w32(self, a: int, v: int):
        if self.mmio_start <= a < self.mmio_end:
            for i in range(4):
                self._w8(a + i, (v >> (8 * i)) & MASK8)
            return
        o = a % self.mem_size
        struct.pack_into("<I", self.mem, o, v & MASK32)

    def _r64(self, a: int) -> int:
        if self.mmio_start <= a < self.mmio_end:
            return self._r32(a) | (self._r32(a + 4) << 32)
        o = a % self.mem_size
        return struct.unpack_from("<Q", self.mem, o)[0]

    def _w64(self, a: int, v: int):
        if self.mmio_start <= a < self.mmio_end:
            self._w32(a, v & MASK32)
            self._w32(a + 4, (v >> 32) & MASK32)
            return
        o = a % self.mem_size
        struct.pack_into("<Q", self.mem, o, v & MASK64)

    # -- flag helpers -----------------------------------------------------
    @staticmethod
    def _parity8(v: int) -> int:
        v = v & MASK8
        v ^= v >> 4
        v ^= v >> 2
        v ^= v >> 1
        return v & 1

    @staticmethod
    def _sext(v: int, bits: int) -> int:
        """Sign-extend *v* from *bits* width to Python int."""
        s = 1 << (bits - 1)
        mask = (1 << bits) - 1
        return ((v & mask) ^ s) - s

    @staticmethod
    def _sext8(v: int) -> int:
        v = v & MASK8
        return v - 256 if v >= 128 else v

    @staticmethod
    def _sext16(v: int) -> int:
        v = v & MASK16
        return v - 0x10000 if v >= 0x8000 else v

    @staticmethod
    def _sext32(v: int) -> int:
        v = v & MASK32
        return v - 0x1_0000_0000 if v >= 0x8000_0000 else v

    @staticmethod
    def _sext64(v: int) -> int:
        v = v & MASK64
        return v - (1 << 64) if v >= (1 << 63) else v

    def _pack_flags(self) -> int:
        return (self.flag_s << 7 | self.flag_i << 6 | self.flag_g << 5 |
                self.flag_p << 4 | self.flag_v << 3 | self.flag_n << 2 |
                self.flag_c << 1 | self.flag_z)

    def _unpack_flags(self, f: int):
        self.flag_z = f & 1
        self.flag_c = (f >> 1) & 1
        self.flag_n = (f >> 2) & 1
        self.flag_v = (f >> 3) & 1
        self.flag_p = (f >> 4) & 1
        self.flag_g = (f >> 5) & 1
        self.flag_i = (f >> 6) & 1
        self.flag_s = (f >> 7) & 1

    def _flags_arith_add(self, a: int, b: int, r: int):
        """Set flags for addition result.  *r* is the full (possibly >64-bit) result."""
        r64 = r & MASK64
        self.flag_z = int(r64 == 0)
        self.flag_c = int(r > MASK64)
        self.flag_n = (r64 >> 63) & 1
        sa, sb, sr = (a >> 63) & 1, (b >> 63) & 1, (r64 >> 63) & 1
        self.flag_v = int(sa == sb and sr != sa)
        self.flag_p = self._parity8(r64)

    def _flags_arith_sub(self, a: int, b: int, r: int):
        """Set flags for subtraction  a - b = r."""
        r64 = r & MASK64
        self.flag_z = int(r64 == 0)
        self.flag_c = int(a >= b)  # no borrow
        self.flag_n = (r64 >> 63) & 1
        sa, sb, sr = (a >> 63) & 1, (b >> 63) & 1, (r64 >> 63) & 1
        self.flag_v = int(sa != sb and sr != sa)
        self.flag_p = self._parity8(r64)

    def _flags_logic(self, r64: int):
        r64 &= MASK64
        self.flag_z = int(r64 == 0)
        self.flag_p = self._parity8(r64)

    def _flags_shift(self, r64: int, carry: int):
        r64 &= MASK64
        self.flag_z = int(r64 == 0)
        self.flag_c = carry & 1
        self.flag_n = (r64 >> 63) & 1
        self.flag_p = self._parity8(r64)

    # -- condition test ---------------------------------------------------
    def _cond(self, cc: int) -> bool:
        if cc == CC_AL:  return True
        if cc == CC_EQ:  return self.flag_z == 1
        if cc == CC_NE:  return self.flag_z == 0
        if cc == CC_CS:  return self.flag_c == 1
        if cc == CC_CC:  return self.flag_c == 0
        if cc == CC_MI:  return self.flag_n == 1
        if cc == CC_PL:  return self.flag_n == 0
        if cc == CC_VS:  return self.flag_v == 1
        if cc == CC_VC:  return self.flag_v == 0
        if cc == CC_GT:  return self.flag_g == 1
        if cc == CC_LE:  return self.flag_g == 0
        if cc == CC_BQ:  return self.q == 1
        if cc == CC_BNQ: return self.q == 0
        if cc == CC_SAT: return self.flag_s == 1
        if cc == CC_EF:  return False  # external flags not yet wired
        if cc == CC_NV:  return False
        return False

    # -- CSR access -------------------------------------------------------
    def _csr_read(self, addr: int) -> int:
        a = addr & MASK8
        if a == 0x00: return self._pack_flags()
        if a == 0x01: return self.psel
        if a == 0x02: return self.xsel
        if a == 0x03: return self.spsel
        if a == 0x04: return self.ivt_base
        if a == 0x05: return self.d
        if a == 0x06: return self.flag_c  # DF alias
        if a == 0x07: return self.q
        if a == 0x08: return self.t
        if a == 0x09: return self.flag_i
        if a == 0x0A: return self.priv
        if a == 0x0B: return self.mpu_base
        if a == 0x0C: return self.mpu_limit
        # Tile CSRs
        if a == 0x10: return self.tsrc1   # SB
        if a == 0x11: return self.tdst    # SR
        if a == 0x12: return self.tctrl   # SC
        if a == 0x14: return self.tmode
        if a == 0x15: return self.tctrl
        if a == 0x16: return self.tsrc0
        if a == 0x17: return self.tsrc1
        if a == 0x18: return self.tdst
        if a == 0x19: return self.acc[0]
        if a == 0x1A: return self.acc[1]
        if a == 0x1B: return self.acc[2]
        if a == 0x1C: return self.acc[3]
        # Tile 2D
        if a == 0x40: return self.tstride_r
        if a == 0x41: return self.tstride_c
        if a == 0x42: return self.ttile_h
        if a == 0x43: return self.ttile_w
        # Core identity
        if a == 0x20: return self.core_id
        if a == 0x21: return self.n_cores
        if a == 0x24: return self.ivec_id
        if a == 0x25: return self.trap_addr
        if a == 0x30: return self.mem_size
        if a == 0x31: return 0x4D503634  # "MP64"
        # Perf counters
        if a == 0x68: return self.perf_cycles
        if a == 0x69: return self.perf_stalls
        if a == 0x6A: return self.perf_tileops
        if a == 0x6B: return self.perf_extmem
        if a == 0x6C: return self.perf_en
        return 0

    def _csr_write(self, addr: int, val: int):
        a = addr & MASK8
        v = val & MASK64
        if a == 0x00: self._unpack_flags(v & MASK8)
        elif a == 0x01: self.psel = v & 0xF
        elif a == 0x02: self.xsel = v & 0xF
        elif a == 0x03: self.spsel = v & 0xF
        elif a == 0x04: self.ivt_base = v
        elif a == 0x05: self.d = v & MASK8
        elif a == 0x06: self.flag_c = v & 1
        elif a == 0x07: self.q = v & 1
        elif a == 0x08: self.t = v & MASK8
        elif a == 0x09: self.flag_i = v & 1
        elif a == 0x0A: self.priv = v & 1
        elif a == 0x0B: self.mpu_base = v
        elif a == 0x0C: self.mpu_limit = v
        elif a == 0x14: self.tmode = v
        elif a == 0x15: self.tctrl = v
        elif a == 0x16: self.tsrc0 = v
        elif a == 0x17: self.tsrc1 = v
        elif a == 0x18: self.tdst = v
        elif a == 0x19: self.acc[0] = v
        elif a == 0x1A: self.acc[1] = v
        elif a == 0x1B: self.acc[2] = v
        elif a == 0x1C: self.acc[3] = v
        elif a == 0x40: self.tstride_r = v
        elif a == 0x41: self.tstride_c = v
        elif a == 0x42: self.ttile_h = v & 0xFF
        elif a == 0x43: self.ttile_w = v & 0xFF
        elif a == 0x6C:
            self.perf_en = v & 1
            if v & 2:  # reset
                self.perf_cycles = 0
                self.perf_stalls = 0
                self.perf_tileops = 0
                self.perf_extmem = 0

    # -- trap delivery ----------------------------------------------------
    def _trap(self, vector: int, addr: int = 0):
        """Deliver a hardware trap / interrupt."""
        self.ivec_id = vector
        self.trap_addr = addr
        # Push flags|priv and PC
        sp = self.regs[self.spsel]
        sp = (sp - 8) & MASK64
        self._w64(sp, self.regs[self.psel])  # push PC
        sp = (sp - 8) & MASK64
        self._w64(sp, self._pack_flags() | (self.priv << 8))  # push flags+priv
        self.regs[self.spsel] = sp
        # Enter supervisor mode, disable interrupts
        self.priv = 0
        self.flag_i = 0
        # Jump to handler
        handler = self._r64(self.ivt_base + vector * 8)
        self.regs[self.psel] = handler

    # -- instruction fetch (from local pc variable) -----------------------
    def _fetch8(self, pc: int) -> tuple[int, int]:
        v = self.mem[pc % self.mem_size]
        return v, (pc + 1) & MASK64

    # =====================================================================
    #  MAIN STEP FUNCTION
    # =====================================================================
    def step(self) -> int:
        """Execute one instruction. Returns cycle count."""
        if self.halted or self.idle:
            return 0

        old_psel = self.psel
        pc = self.regs[self.psel]

        # Fetch first byte
        b0 = self.mem[pc % self.mem_size]
        pc = (pc + 1) & MASK64
        f = (b0 >> 4) & 0xF
        n = b0 & 0xF

        # Handle EXT prefix
        ext = -1
        if f == 0xF:
            ext = n
            b0 = self.mem[pc % self.mem_size]
            pc = (pc + 1) & MASK64
            f = (b0 >> 4) & 0xF
            n = b0 & 0xF

        cycles = 1

        try:
            if f == 0x0:
                pc, cycles = self._x_sys(n, pc, ext)
            elif f == 0x1:
                self.regs[n] = (self.regs[n] + 1) & MASK64
            elif f == 0x2:
                self.regs[n] = (self.regs[n] - 1) & MASK64
            elif f == 0x3:
                pc, cycles = self._x_br(n, pc, ext)
            elif f == 0x4:
                pc, cycles = self._x_lbr(n, pc)
            elif f == 0x5:
                pc, cycles = self._x_mem(n, pc)
            elif f == 0x6:
                pc, cycles = self._x_imm(n, pc, ext)
            elif f == 0x7:
                pc, cycles = self._x_alu(n, pc)
            elif f == 0x8:
                self._x_memalu(n)
            elif f == 0x9:
                self._x_io(n)
            elif f == 0xA:  # SEP
                self.regs[old_psel] = pc
                self.psel = n
                pc = self.regs[n]
            elif f == 0xB:  # SEX
                self.xsel = n
            elif f == 0xC:
                pc, cycles = self._x_muldiv(n, pc)
            elif f == 0xD:
                pc, cycles = self._x_csr(n, pc)
            elif f == 0xE:
                pc, cycles = self._x_mex(n, pc, ext)
            # 0xF already handled above
        except TrapError as te:
            self.regs[self.psel] = pc
            self._trap(te.vector, te.addr)
            return 4  # trap overhead

        self.regs[self.psel] = pc
        self.cycle_count += cycles
        if self.perf_en:
            self.perf_cycles += cycles
        return cycles

    def run(self, max_steps: int = 0) -> int:
        """Run up to *max_steps* instructions (0 = unlimited until halt).
        Returns total cycles executed."""
        total = 0
        n = 0
        while not self.halted:
            total += self.step()
            n += 1
            if max_steps and n >= max_steps:
                break
        return total

    # =====================================================================
    #  FAMILY HANDLERS
    # =====================================================================

    # -- 0x0  SYS ---------------------------------------------------------
    def _x_sys(self, n: int, pc: int, ext: int) -> tuple[int, int]:
        if n == 0x0:   # IDL
            self.idle = True
            return pc, 1
        if n == 0x1:   # NOP
            return pc, 1
        if n == 0x2:   # HALT
            self.halted = True
            return pc, 1
        if n == 0x3:   # RESET
            self.__init__(self.mem, core_id=self.core_id, n_cores=self.n_cores)
            return 0, 1
        if n == 0x4:   # RTI
            sp = self.regs[self.spsel]
            fw = self._r64(sp)
            sp = (sp + 8) & MASK64
            ret_pc = self._r64(sp)
            sp = (sp + 8) & MASK64
            self.regs[self.spsel] = sp
            self._unpack_flags(fw & MASK8)
            self.priv = (fw >> 8) & 1
            return ret_pc, 4
        if n == 0x5:   # RET (1802-style)
            xr = self.regs[self.xsel]
            ret_pc = self._r8(xr)
            self.regs[self.xsel] = (xr + 1) & MASK64
            return ret_pc, 2
        if n == 0x6:   # DIS
            self.flag_i = 0
            xr = self.regs[self.xsel]
            ret_pc = self._r8(xr)
            self.regs[self.xsel] = (xr + 1) & MASK64
            return ret_pc, 2
        if n == 0x7:   # MARK
            # push T, T = (X<<4)|P
            sp = self.regs[self.spsel]
            sp = (sp - 1) & MASK64
            self._w8(sp, self.t)
            self.regs[self.spsel] = sp
            self.t = ((self.xsel << 4) | self.psel) & MASK8
            return pc, 1
        if n == 0x8:   # SAV
            xr = self.regs[self.xsel]
            self._w8(xr, self.t)
            return pc, 1
        if n == 0x9:   # SEQ
            self.q = 1
            return pc, 1
        if n == 0xA:   # REQ
            self.q = 0
            return pc, 1
        if n == 0xB:   # EI
            self.flag_i = 1
            return pc, 1
        if n == 0xC:   # DI
            self.flag_i = 0
            return pc, 1
        if n == 0xD:   # CALL.L Rn (2 bytes)
            rn = self.mem[pc % self.mem_size] & 0xF
            pc = (pc + 1) & MASK64
            target = self.regs[rn]
            # push return address
            sp = self.regs[self.spsel]
            sp = (sp - 8) & MASK64
            self._w64(sp, pc)
            self.regs[self.spsel] = sp
            return target, 3
        if n == 0xE:   # RET.L
            sp = self.regs[self.spsel]
            ret_pc = self._r64(sp)
            self.regs[self.spsel] = (sp + 8) & MASK64
            return ret_pc, 3
        if n == 0xF:   # TRAP
            raise TrapError(IVEC_SW_TRAP)
        return pc, 1

    # -- 0x3  BR (short branch, 2 bytes) ----------------------------------
    def _x_br(self, cc: int, pc: int, ext: int) -> tuple[int, int]:
        off = self._sext8(self.mem[pc % self.mem_size])
        pc = (pc + 1) & MASK64
        if ext == 6:  # EXT.SKIP — skip next instruction if condition true
            if self._cond(cc):
                # skip next instruction (peek at its length)
                pc = self._skip_next(pc)
            return pc, 2
        if self._cond(cc):
            pc = (pc + off) & MASK64
        return pc, 2

    def _skip_next(self, pc: int) -> int:
        """Advance pc past the next instruction (for EXT.SKIP)."""
        b = self.mem[pc % self.mem_size]
        f = (b >> 4) & 0xF
        n = b & 0xF
        sz = self._insn_size(f, n, pc)
        return (pc + sz) & MASK64

    @staticmethod
    def _insn_size(f: int, n: int, _pc: int = 0) -> int:
        """Return byte-length of an instruction given its family and sub-op."""
        if f <= 0x2: return 1
        if f == 0x3: return 2
        if f == 0x4: return 3
        if f == 0x5:
            return 3 if n == 0xF else 2  # LD.D has offset byte
        if f == 0x6:
            if n == 0x1: return 4  # LHI: reg + imm16
            if n <= 0x7: return 3  # reg + imm8
            return 2  # shifts / GLO,GHI,PLO,PHI
        if f == 0x7: return 2
        if f == 0x8: return 1
        if f == 0x9: return 1
        if f == 0xA: return 1
        if f == 0xB: return 1
        if f == 0xC: return 2
        if f == 0xD: return 2
        if f == 0xE: return 2  # MEX base (some variants longer)
        if f == 0xF: return 1
        return 1

    # -- 0x4  LBR (long branch, 3 bytes, big-endian offset) ---------------
    def _x_lbr(self, cc: int, pc: int) -> tuple[int, int]:
        hi = self.mem[pc % self.mem_size]
        lo = self.mem[(pc + 1) % self.mem_size]
        pc = (pc + 2) & MASK64
        off = self._sext16((hi << 8) | lo)
        if self._cond(cc):
            pc = (pc + off) & MASK64
        return pc, 3

    # -- 0x5  MEM (scalar load/store, 2–3 bytes) --------------------------
    def _x_mem(self, sub: int, pc: int) -> tuple[int, int]:
        b1 = self.mem[pc % self.mem_size]
        pc = (pc + 1) & MASK64
        rd = (b1 >> 4) & 0xF
        rs = b1 & 0xF
        R = self.regs
        if sub == 0x0:  # LDN
            R[rd] = self._r64(R[rs])
        elif sub == 0x1:  # LDA
            R[rd] = self._r64(R[rs])
            R[rs] = (R[rs] + 8) & MASK64
        elif sub == 0x2:  # LDX
            R[rd] = self._r64(R[self.xsel])
        elif sub == 0x3:  # LDXA
            R[rd] = self._r64(R[self.xsel])
            R[self.xsel] = (R[self.xsel] + 8) & MASK64
        elif sub == 0x4:  # STR
            self._w64(R[rd], R[rs])
        elif sub == 0x5:  # STXD
            self._w64(R[rd], R[rs])
            R[rd] = (R[rd] - 8) & MASK64
        elif sub == 0x6:  # LD.B
            R[rd] = self._r8(R[rs])
        elif sub == 0x7:  # ST.B
            self._w8(R[rd], R[rs] & MASK8)
        elif sub == 0x8:  # LD.H
            R[rd] = self._r16(R[rs])
        elif sub == 0x9:  # ST.H
            self._w16(R[rd], R[rs] & MASK16)
        elif sub == 0xA:  # LD.W
            R[rd] = self._r32(R[rs])
        elif sub == 0xB:  # ST.W
            self._w32(R[rd], R[rs] & MASK32)
        elif sub == 0xC:  # LD.SB
            R[rd] = self._sext8(self._r8(R[rs])) & MASK64
        elif sub == 0xD:  # LD.SH
            R[rd] = self._sext16(self._r16(R[rs])) & MASK64
        elif sub == 0xE:  # LD.SW
            R[rd] = self._sext32(self._r32(R[rs])) & MASK64
        elif sub == 0xF:  # LD.D Rd,Rs,off8
            off = self._sext8(self.mem[pc % self.mem_size])
            pc = (pc + 1) & MASK64
            R[rd] = self._r64((R[rs] + off * 8) & MASK64)
            return pc, 3
        return pc, 2

    # -- 0x6  IMM (immediate ops, 2–11 bytes) -----------------------------
    def _x_imm(self, sub: int, pc: int, ext: int) -> tuple[int, int]:
        R = self.regs
        if sub == 0x0:  # LDI
            rn = self.mem[pc % self.mem_size] & 0xF
            pc = (pc + 1) & MASK64
            if ext == 0:  # EXT.IMM64
                val = 0
                for i in range(8):
                    val |= self.mem[(pc + i) % self.mem_size] << (8 * i)
                pc = (pc + 8) & MASK64
                R[rn] = val & MASK64
                return pc, 4
            imm = self.mem[pc % self.mem_size]
            pc = (pc + 1) & MASK64
            R[rn] = imm
            return pc, 2
        if sub == 0x1:  # LHI
            rn = self.mem[pc % self.mem_size] & 0xF
            pc = (pc + 1) & MASK64
            hi = self.mem[pc % self.mem_size]
            lo = self.mem[(pc + 1) % self.mem_size]
            pc = (pc + 2) & MASK64
            imm16 = (hi << 8) | lo
            R[rn] = (R[rn] & 0x0000_FFFF_FFFF_FFFF) | (imm16 << 48)
            return pc, 3
        # Sub 2-7: reg + simm8/imm8, 3 bytes
        if 2 <= sub <= 7:
            rn = self.mem[pc % self.mem_size] & 0xF
            imm = self.mem[(pc + 1) % self.mem_size]
            pc = (pc + 2) & MASK64
            if sub == 0x2:  # ADDI
                simm = self._sext8(imm)
                a, b = R[rn], simm & MASK64
                r = a + b
                R[rn] = r & MASK64
                self._flags_arith_add(a, b, r)
            elif sub == 0x3:  # ANDI
                R[rn] = R[rn] & imm
                self._flags_logic(R[rn])
            elif sub == 0x4:  # ORI
                R[rn] = R[rn] | imm
                self._flags_logic(R[rn])
            elif sub == 0x5:  # XORI
                R[rn] = R[rn] ^ imm
                self._flags_logic(R[rn])
            elif sub == 0x6:  # CMPI
                simm = self._sext8(imm) & MASK64
                a = R[rn]
                r = (a - simm) & MASK64
                self._flags_arith_sub(a, simm, a - simm)
                self.flag_g = int(self._sext64(a) > self._sext64(simm))
            elif sub == 0x7:  # SUBI
                simm = self._sext8(imm) & MASK64
                a = R[rn]
                r = a - simm
                R[rn] = r & MASK64
                self._flags_arith_sub(a, simm, r)
            return pc, 2
        # Sub 8-B: shifts/rotates, 2 bytes (reg+imm4 packed in byte1)
        if 0x8 <= sub <= 0xB:
            b1 = self.mem[pc % self.mem_size]
            pc = (pc + 1) & MASK64
            rn = (b1 >> 4) & 0xF
            imm4 = b1 & 0xF
            if sub == 0x8:  # LSLI
                amt = imm4
                c = ((R[rn] >> (64 - amt)) & 1) if amt else 0
                R[rn] = (R[rn] << amt) & MASK64
                self._flags_shift(R[rn], c)
            elif sub == 0x9:  # LSRI
                amt = imm4
                c = ((R[rn] >> (amt - 1)) & 1) if amt else 0
                R[rn] = (R[rn] >> amt) & MASK64
                self._flags_shift(R[rn], c)
            elif sub == 0xA:  # ASRI
                amt = imm4
                c = ((R[rn] >> (amt - 1)) & 1) if amt else 0
                sv = self._sext64(R[rn])
                R[rn] = (sv >> amt) & MASK64
                self._flags_shift(R[rn], c)
            elif sub == 0xB:  # ROLI
                amt = imm4 & 0x3F
                if amt:
                    R[rn] = ((R[rn] << amt) | (R[rn] >> (64 - amt))) & MASK64
                self.flag_z = int(R[rn] == 0)
                self.flag_n = (R[rn] >> 63) & 1
                self.flag_p = self._parity8(R[rn])
            return pc, 1
        # Sub C-F: GLO, GHI, PLO, PHI  (2 bytes)
        b1 = self.mem[pc % self.mem_size] & 0xF
        pc = (pc + 1) & MASK64
        if sub == 0xC:  # GLO
            self.d = R[b1] & MASK8
        elif sub == 0xD:  # GHI
            self.d = (R[b1] >> 8) & MASK8
        elif sub == 0xE:  # PLO
            R[b1] = (R[b1] & ~MASK8) | (self.d & MASK8)
        elif sub == 0xF:  # PHI
            R[b1] = (R[b1] & ~(MASK8 << 8)) | ((self.d & MASK8) << 8)
        return pc, 1

    # -- 0x7  ALU (register-register, 2 bytes) ----------------------------
    def _x_alu(self, sub: int, pc: int) -> tuple[int, int]:
        b1 = self.mem[pc % self.mem_size]
        pc = (pc + 1) & MASK64
        rd = (b1 >> 4) & 0xF
        rs = b1 & 0xF
        R = self.regs
        a, b = R[rd], R[rs]

        if sub == 0x0:  # ADD
            r = a + b
            R[rd] = r & MASK64
            self._flags_arith_add(a, b, r)
        elif sub == 0x1:  # ADC
            r = a + b + self.flag_c
            R[rd] = r & MASK64
            self._flags_arith_add(a, b + self.flag_c, r)
        elif sub == 0x2:  # SUB
            r = a - b
            R[rd] = r & MASK64
            self._flags_arith_sub(a, b, r)
        elif sub == 0x3:  # SBB
            borrow = 1 - self.flag_c
            r = a - b - borrow
            R[rd] = r & MASK64
            self._flags_arith_sub(a, (b + borrow) & MASK64, r)
        elif sub == 0x4:  # AND
            R[rd] = a & b
            self._flags_logic(R[rd])
        elif sub == 0x5:  # OR
            R[rd] = a | b
            self._flags_logic(R[rd])
        elif sub == 0x6:  # XOR
            R[rd] = a ^ b
            self._flags_logic(R[rd])
        elif sub == 0x7:  # CMP
            r = a - b
            self._flags_arith_sub(a, b, r)
            self.flag_g = int(self._sext64(a) > self._sext64(b))
        elif sub == 0x8:  # MOV
            R[rd] = b
        elif sub == 0x9:  # NOT
            R[rd] = (~b) & MASK64
            self._flags_logic(R[rd])
        elif sub == 0xA:  # NEG
            r = -self._sext64(b)
            R[rd] = r & MASK64
            self._flags_arith_sub(0, b, r)
        elif sub == 0xB:  # SHL
            amt = b & 0x3F
            c = ((a >> (64 - amt)) & 1) if amt else 0
            R[rd] = (a << amt) & MASK64
            self._flags_shift(R[rd], c)
        elif sub == 0xC:  # SHR
            amt = b & 0x3F
            c = ((a >> (amt - 1)) & 1) if amt else 0
            R[rd] = (a >> amt) & MASK64
            self._flags_shift(R[rd], c)
        elif sub == 0xD:  # SAR
            amt = b & 0x3F
            c = ((a >> (amt - 1)) & 1) if amt else 0
            sv = self._sext64(a)
            R[rd] = (sv >> amt) & MASK64
            self._flags_shift(R[rd], c)
        elif sub == 0xE:  # ROL
            amt = b & 0x3F
            if amt:
                R[rd] = ((a << amt) | (a >> (64 - amt))) & MASK64
            self.flag_z = int(R[rd] == 0)
            self.flag_n = (R[rd] >> 63) & 1
            self.flag_p = self._parity8(R[rd])
        elif sub == 0xF:  # ROR
            amt = b & 0x3F
            if amt:
                R[rd] = ((a >> amt) | (a << (64 - amt))) & MASK64
            self.flag_z = int(R[rd] == 0)
            self.flag_n = (R[rd] >> 63) & 1
            self.flag_p = self._parity8(R[rd])
        return pc, 1

    # -- 0x8  MEMALU (1802-compatible, 1 byte) ----------------------------
    def _x_memalu(self, sub: int):
        xr = self.regs[self.xsel]
        m = self._r8(xr)
        if sub == 0x0:  # LDX
            self.d = m
        elif sub == 0x1:  # OR.X
            self.d = (self.d | m) & MASK8
        elif sub == 0x2:  # AND.X
            self.d = (self.d & m) & MASK8
        elif sub == 0x3:  # XOR.X
            self.d = (self.d ^ m) & MASK8
        elif sub == 0x4:  # ADD.X
            r = self.d + m
            self.flag_c = int(r > 0xFF)
            self.d = r & MASK8
        elif sub == 0x5:  # SD.X  (D = M - D)
            r = m - self.d
            self.flag_c = int(r >= 0)  # no borrow
            self.d = r & MASK8
        elif sub == 0x6:  # SHR.D
            self.flag_c = self.d & 1
            self.d = (self.d >> 1) & MASK8
        elif sub == 0x7:  # SM.X  (D = D - M)
            r = self.d - m
            self.flag_c = int(r >= 0)
            self.d = r & MASK8
        elif sub == 0x8:  # ADC.X
            r = self.d + m + self.flag_c
            self.flag_c = int(r > 0xFF)
            self.d = r & MASK8
        elif sub == 0x9:  # SDB.X (D = M - D - !borrow)
            borrow = 1 - self.flag_c
            r = m - self.d - borrow
            self.flag_c = int(r >= 0)
            self.d = r & MASK8
        elif sub == 0xA:  # SHRC.D
            old_c = self.flag_c
            self.flag_c = self.d & 1
            self.d = ((old_c << 7) | (self.d >> 1)) & MASK8
        elif sub == 0xB:  # SMB.X (D = D - M - !borrow)
            borrow = 1 - self.flag_c
            r = self.d - m - borrow
            self.flag_c = int(r >= 0)
            self.d = r & MASK8
        elif sub == 0xC:  # SHL.D
            self.flag_c = (self.d >> 7) & 1
            self.d = (self.d << 1) & MASK8
        elif sub == 0xD:  # SHLC.D
            old_c = self.flag_c
            self.flag_c = (self.d >> 7) & 1
            self.d = ((self.d << 1) | old_c) & MASK8
        elif sub == 0xE:  # IRX
            self.regs[self.xsel] = (xr + 1) & MASK64
        elif sub == 0xF:  # LDXA
            self.d = m
            self.regs[self.xsel] = (xr + 1) & MASK64

    # -- 0x9  I/O (1 byte) -----------------------------------------------
    def _x_io(self, n: int):
        if 1 <= n <= 7:  # OUT1–OUT7
            xr = self.regs[self.xsel]
            val = self._r8(xr)
            self.regs[self.xsel] = (xr + 1) & MASK64
            self.port_out[n] = val
            if self.on_output:
                self.on_output(n, val)
        elif 9 <= n <= 15:  # INP1–INP7
            port = n - 8
            val = 0
            if self.on_input:
                val = self.on_input(port) & MASK8
            self.port_in[port] = val
            self.d = val
            xr = self.regs[self.xsel]
            self._w8(xr, val)

    # -- 0xC  MULDIV (2 bytes) --------------------------------------------
    def _x_muldiv(self, sub: int, pc: int) -> tuple[int, int]:
        b1 = self.mem[pc % self.mem_size]
        pc = (pc + 1) & MASK64
        rd = (b1 >> 4) & 0xF
        rs = b1 & 0xF
        R = self.regs
        a, b = R[rd], R[rs]

        if sub == 0x0:  # MUL (signed low)
            sa, sb = self._sext64(a), self._sext64(b)
            R[rd] = (sa * sb) & MASK64
        elif sub == 0x1:  # MULH (signed high)
            sa, sb = self._sext64(a), self._sext64(b)
            R[rd] = ((sa * sb) >> 64) & MASK64
        elif sub == 0x2:  # UMUL
            R[rd] = (a * b) & MASK64
        elif sub == 0x3:  # UMULH
            R[rd] = ((a * b) >> 64) & MASK64
        elif sub == 0x4:  # DIV
            if b == 0:
                raise TrapError(IVEC_DIV_ZERO)
            sa, sb = self._sext64(a), self._sext64(b)
            # Python's // truncates toward negative infinity; we want toward zero
            q = int(sa / sb)  # float division then int truncation
            R[rd] = q & MASK64
        elif sub == 0x5:  # UDIV
            if b == 0:
                raise TrapError(IVEC_DIV_ZERO)
            R[rd] = (a // b) & MASK64
        elif sub == 0x6:  # MOD
            if b == 0:
                raise TrapError(IVEC_DIV_ZERO)
            sa, sb = self._sext64(a), self._sext64(b)
            q = int(sa / sb)
            R[rd] = (sa - q * sb) & MASK64
        elif sub == 0x7:  # UMOD
            if b == 0:
                raise TrapError(IVEC_DIV_ZERO)
            R[rd] = (a % b) & MASK64
        return pc, 4

    # -- 0xD  CSR (2 bytes) -----------------------------------------------
    def _x_csr(self, n: int, pc: int) -> tuple[int, int]:
        addr = self.mem[pc % self.mem_size]
        pc = (pc + 1) & MASK64
        direction = (n >> 3) & 1  # 0 = read, 1 = write
        reg = n & 0x7
        if direction == 0:  # CSRR
            self.regs[reg] = self._csr_read(addr)
        else:  # CSRW
            self._csr_write(addr, self.regs[reg])
        return pc, 2

    # -- 0xE  MEX (tile engine) ---------------------------------------------

    # Tile I/O helpers
    def _tile_rd(self, addr: int, eb: int, n: int) -> list[int]:
        """Read *n* elements of *eb* bytes each from memory."""
        rd = {1: self._r8, 2: self._r16, 4: self._r32, 8: self._r64}[eb]
        return [rd((addr + i * eb) & MASK64) for i in range(n)]

    def _tile_wr(self, addr: int, eb: int, elems: list[int], em: int):
        wr = {1: self._w8, 2: self._w16, 4: self._w32, 8: self._w64}[eb]
        for i, v in enumerate(elems):
            wr((addr + i * eb) & MASK64, v & em)

    def _x_mex(self, n: int, pc: int, ext: int) -> tuple[int, int]:
        funct = self.mem[pc % self.mem_size]
        pc = (pc + 1) & MASK64

        ss = (n >> 2) & 3        # element-size selector
        op = n & 3               # operation group
        eb = 1 << ss             # element bytes: 1, 2, 4, 8
        ne = 64 // eb            # elements per tile: 64, 32, 16, 8
        em = (1 << (eb * 8)) - 1 # element mask

        if op == 0:
            self._mex_talu(funct, eb, ne, em)
        elif op == 1:
            self._mex_tmul(funct, eb, ne, em)
        elif op == 2:
            self._mex_tred(funct, eb, ne, em)
        elif op == 3:
            self._mex_tsys(funct, eb, ne, em, ext)

        if self.perf_en:
            self.perf_tileops += 1
        return pc, 4

    # TALU: element-wise arithmetic (op=0)
    def _mex_talu(self, fn: int, eb: int, ne: int, em: int):
        s0 = self._tile_rd(self.tsrc0, eb, ne)
        s1 = self._tile_rd(self.tsrc1, eb, ne)
        if fn == 0:    dst = [(a + b) & em for a, b in zip(s0, s1)]
        elif fn == 1:  dst = [(a - b) & em for a, b in zip(s0, s1)]
        elif fn == 2:  dst = [(a * b) & em for a, b in zip(s0, s1)]
        elif fn == 3:  dst = [min(a, b) for a, b in zip(s0, s1)]
        elif fn == 4:  dst = [max(a, b) for a, b in zip(s0, s1)]
        elif fn == 5:  dst = [int(a > b) - int(a < b) for a, b in zip(s0, s1)]
        elif fn == 6:  dst = [abs(a - b) & em for a, b in zip(s0, s1)]
        elif fn == 7:  # CLAMP to [ACC0, ACC1]
            lo, hi = self.acc[0] & em, self.acc[1] & em
            dst = [max(lo, min(hi, a)) for a in s0]
        else:
            dst = s0
        self._tile_wr(self.tdst, eb, dst, em)

    # TMUL: multiply variants (op=1)
    def _mex_tmul(self, fn: int, eb: int, ne: int, em: int):
        s0 = self._tile_rd(self.tsrc0, eb, ne)
        s1 = self._tile_rd(self.tsrc1, eb, ne)
        if fn == 0:    # MUL
            self._tile_wr(self.tdst, eb,
                          [(a * b) & em for a, b in zip(s0, s1)], em)
        elif fn == 1:  # DOT product → scalar to ACC0
            self.acc[0] = sum(a * b for a, b in zip(s0, s1)) & MASK64
        elif fn == 2:  # WMUL (low bits)
            self._tile_wr(self.tdst, eb,
                          [(a * b) & em for a, b in zip(s0, s1)], em)
        elif fn == 3:  # MAC  dst += s0 * s1
            old = self._tile_rd(self.tdst, eb, ne)
            self._tile_wr(self.tdst, eb,
                          [(o + a * b) & em for o, a, b in zip(old, s0, s1)], em)
        elif fn == 4:  # FMA  s0 * s1 + dst
            old = self._tile_rd(self.tdst, eb, ne)
            self._tile_wr(self.tdst, eb,
                          [(a * b + o) & em for o, a, b in zip(old, s0, s1)], em)
        elif fn == 5:  # DOTACC  ACC0 += dot(s0, s1)
            self.acc[0] = (self.acc[0] + sum(a * b for a, b in zip(s0, s1))) & MASK64

    # TRED: reductions (op=2)
    def _mex_tred(self, fn: int, eb: int, ne: int, em: int):
        s = self._tile_rd(self.tsrc0, eb, ne)
        if fn == 0:    r = sum(s) & MASK64
        elif fn == 1:  r = min(s)
        elif fn == 2:  r = max(s)
        elif fn == 3:  r = sum(bin(x).count('1') for x in s)
        elif fn == 4:  r = sum(s) & MASK64   # L1 (unsigned)
        elif fn == 5:  r = sum(x * x for x in s) & MASK64
        elif fn == 6:  r = s.index(min(s))
        elif fn == 7:  r = s.index(max(s))
        else:          r = 0
        self.acc[0] = r & MASK64

    # TSYS: system / data-movement (op=3)
    def _mex_tsys(self, fn: int, eb: int, ne: int, em: int, ext: int):
        if fn == 0:    # TRANS (reverse as placeholder for real transpose)
            s = self._tile_rd(self.tsrc0, eb, ne)
            self._tile_wr(self.tdst, eb, list(reversed(s)), em)
        elif fn == 1:  # SHUFFLE (indices from src1)
            s0 = self._tile_rd(self.tsrc0, eb, ne)
            idx = self._tile_rd(self.tsrc1, eb, ne)
            self._tile_wr(self.tdst, eb, [s0[i % ne] for i in idx], em)
        elif fn == 2:  # MOVBANK (copy src0 → dst)
            s = self._tile_rd(self.tsrc0, eb, ne)
            self._tile_wr(self.tdst, eb, s, em)
        elif fn == 3:  # LOADC (broadcast ACC0)
            self._tile_wr(self.tdst, eb, [self.acc[0] & em] * ne, em)
        elif fn == 4:  # ZERO
            self._tile_wr(self.tdst, eb, [0] * ne, em)

    # =====================================================================
    #  C ACCELERATION
    # =====================================================================
    def load_accel(self, path: str | Path | None = None):
        """Load the C accelerator shared library."""
        if path is None:
            d = Path(__file__).resolve().parent.parent.parent / "accel"
            path = d / "chimera_accel.so"
        path = Path(path)
        if not path.exists():
            return False
        try:
            lib = ctypes.CDLL(str(path))
        except OSError:
            return False

        # Set up the C function prototype
        lib.mp64_run.argtypes = [
            ctypes.POINTER(CMP64State),   # state
            ctypes.c_char_p,              # mem
            ctypes.c_size_t,              # mem_size
            ctypes.c_uint64,              # mmio_start
            ctypes.c_uint64,              # mmio_end
            ctypes.c_int,                 # max_steps
        ]
        lib.mp64_run.restype = CRunResult

        self._accel_lib = lib
        self._accel_run = lib.mp64_run
        return True

    def _sync_to_c(self) -> "CMP64State":
        s = CMP64State()
        for i in range(16):
            s.regs[i] = self.regs[i]
        s.psel = self.psel
        s.xsel = self.xsel
        s.spsel = self.spsel
        s.d_reg = self.d
        s.t_reg = self.t
        s.q_out = self.q
        s.flag_z = self.flag_z
        s.flag_c = self.flag_c
        s.flag_n = self.flag_n
        s.flag_v = self.flag_v
        s.flag_p = self.flag_p
        s.flag_g = self.flag_g
        s.flag_i = self.flag_i
        s.flag_s = self.flag_s
        s.ivt_base = self.ivt_base
        s.priv_level = self.priv
        s.halted = int(self.halted)
        s.idle = int(self.idle)
        s.cycle_count = self.cycle_count
        s.ext_modifier = -1
        s.ivec_id = self.ivec_id
        s.trap_addr = self.trap_addr
        s.mpu_base = self.mpu_base
        s.mpu_limit = self.mpu_limit
        s.core_id = self.core_id
        s.n_cores = self.n_cores
        return s

    def _sync_from_c(self, s: "CMP64State"):
        for i in range(16):
            self.regs[i] = s.regs[i]
        self.psel = s.psel
        self.xsel = s.xsel
        self.spsel = s.spsel
        self.d = s.d_reg
        self.t = s.t_reg
        self.q = s.q_out
        self.flag_z = s.flag_z
        self.flag_c = s.flag_c
        self.flag_n = s.flag_n
        self.flag_v = s.flag_v
        self.flag_p = s.flag_p
        self.flag_g = s.flag_g
        self.flag_i = s.flag_i
        self.flag_s = s.flag_s
        self.ivt_base = s.ivt_base
        self.priv = s.priv_level
        self.halted = bool(s.halted)
        self.idle = bool(s.idle)
        self.cycle_count = s.cycle_count
        self.ivec_id = s.ivec_id
        self.trap_addr = s.trap_addr
        self.mpu_base = s.mpu_base
        self.mpu_limit = s.mpu_limit

    def run_accel(self, max_steps: int = 100_000) -> int:
        """Execute instructions using the C accelerator.

        Falls back to Python step() for instructions the C code
        cannot handle (MMIO, I/O, MEX, CSR with side-effects).
        Returns total cycles.
        """
        if self._accel_run is None:
            return self.run(max_steps)

        total_cycles = 0
        remaining = max_steps

        while remaining > 0 and not self.halted:
            cs = self._sync_to_c()
            mem_buf = (ctypes.c_char * self.mem_size).from_buffer(self.mem)
            result = self._accel_run(
                ctypes.byref(cs), mem_buf, self.mem_size,
                self.mmio_start, self.mmio_end, remaining,
            )
            self._sync_from_c(cs)
            total_cycles += result.total_cycles
            remaining -= result.steps_executed

            if result.stop_reason == 0:  # max steps
                break
            if result.stop_reason == 1:  # halt
                break
            if result.stop_reason == 2:  # idle
                break
            if result.stop_reason == 3:  # fallback — execute one Python step
                total_cycles += self.step()
                remaining -= 1
            if result.stop_reason == 4:  # trap
                self._trap(cs.ivec_id, cs.trap_addr)
                remaining -= 1

        return total_cycles


# =========================================================================
#  ctypes struct for C acceleration
# =========================================================================
class CMP64State(ctypes.Structure):
    _fields_ = [
        ("regs", ctypes.c_uint64 * 16),
        ("psel", ctypes.c_uint8),
        ("xsel", ctypes.c_uint8),
        ("spsel", ctypes.c_uint8),
        ("d_reg", ctypes.c_uint8),
        ("t_reg", ctypes.c_uint8),
        ("q_out", ctypes.c_uint8),
        ("flag_z", ctypes.c_uint8),
        ("flag_c", ctypes.c_uint8),
        ("flag_n", ctypes.c_uint8),
        ("flag_v", ctypes.c_uint8),
        ("flag_p", ctypes.c_uint8),
        ("flag_g", ctypes.c_uint8),
        ("flag_i", ctypes.c_uint8),
        ("flag_s", ctypes.c_uint8),
        ("ivt_base", ctypes.c_uint64),
        ("priv_level", ctypes.c_uint8),
        ("halted", ctypes.c_uint8),
        ("idle", ctypes.c_uint8),
        ("_pad0", ctypes.c_uint8),
        ("ext_modifier", ctypes.c_int32),
        ("cycle_count", ctypes.c_uint64),
        ("ivec_id", ctypes.c_uint8),
        ("_pad1", ctypes.c_uint8 * 7),
        ("trap_addr", ctypes.c_uint64),
        ("mpu_base", ctypes.c_uint64),
        ("mpu_limit", ctypes.c_uint64),
        ("core_id", ctypes.c_uint32),
        ("n_cores", ctypes.c_uint32),
    ]


class CRunResult(ctypes.Structure):
    _fields_ = [
        ("total_cycles", ctypes.c_uint64),
        ("steps_executed", ctypes.c_int32),
        ("stop_reason", ctypes.c_int32),
    ]
