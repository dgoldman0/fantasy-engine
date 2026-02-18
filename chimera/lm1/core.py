"""LM-1 Lisp Machine tile emulator.

Implements the complete LM-1 instruction set with tagged values,
nursery allocation, write barriers, and optional C acceleration.
"""

from __future__ import annotations
import ctypes, struct
from pathlib import Path
from collections import deque

from . import tagged as T
from .tagged import (
    MASK64, NIL, is_fixnum, is_ref, is_cons, is_special,
    is_truthy, tag_fixnum, untag_fixnum, tag_ref, untag_ref,
    tag_cons, untag_cons, make_header, header_size, header_type,
    HDR_CONS, HDR_INSTANCE, HDR_CLOSURE,
)

# ── Trap codes ───────────────────────────────────────────────────────
TRAP_NOT_FIXNUM       = 0x01
TRAP_FIXNUM_OVERFLOW  = 0x02
TRAP_DIVIDE_BY_ZERO   = 0x03
TRAP_TYPE_MISMATCH    = 0x04
TRAP_NOT_REF          = 0x05
TRAP_NOT_CONS         = 0x06
TRAP_NOT_CLOSURE      = 0x07
TRAP_NURSERY_OVERFLOW = 0x10
TRAP_IC_MISS          = 0x20
TRAP_UNIMPLEMENTED    = 0xFF

# ── Opcode constants ─────────────────────────────────────────────────
OP_TST = 0;   OP_TST_SHAPE = 1;   OP_ARITH_FIX = 2;   OP_ADD_FIX_IMM = 3
OP_CMP_TAGGED = 4
OP_ALLOC = 8; OP_ALLOC_CONS = 9;  OP_ALLOCV = 10;     OP_ALLOC_CLOSURE = 11
OP_LD = 16;   OP_LD_CAR_CDR = 17; OP_ST = 18;          OP_ST_WB = 19
OP_ST_CAR_CDR = 20
OP_CALL_IC = 24;  OP_IC_INSTALL = 25
OP_CALL_DIRECT = 26;  OP_CALL_CLOSURE = 27;  OP_RET = 28
OP_TAILCALL_IC = 29
OP_TAILCALL_DIRECT = 30
OP_SEND = 36; OP_RECV = 37; OP_CAS_TAGGED = 38; OP_FAA_FENCE = 39
OP_ENQ_SCAN = 40; OP_ENQ_COPY = 41; OP_ENQ_FIXUP = 42; OP_ENQ_COMPACT = 43
OP_ARITH_RAW = 48;   OP_BITWISE = 49;  OP_LDR = 50;   OP_STR = 51
OP_BR = 52;   OP_BR_COND = 53;   OP_PUSH_POP = 54
OP_LI = 55;   OP_LUI = 56;   OP_PUSH_MULTI = 57;  OP_POP_MULTI = 58
OP_LI32 = 59; OP_TRAP = 60;  OP_ERET = 61; OP_SYS_INFO = 62
OP_HALT_NOP = 63


class LM1Trap(Exception):
    def __init__(self, code: int):
        self.code = code


class LM1Thread:
    """Per-thread register state."""
    __slots__ = (
        "pc", "sp", "fp", "lr", "regs", "halted",
        "cycle_count", "trap_cause", "trap_pc", "in_trap",
        "trap_table_base", "np", "nl",
        "tile_id", "thread_id",
    )

    def __init__(self, *, tile_id: int = 0, thread_id: int = 0):
        self.pc = 0
        self.sp = 0
        self.fp = 0
        self.lr = 0
        self.regs = [0] * 32
        self.halted = False
        self.cycle_count = 0
        self.trap_cause = 0
        self.trap_pc = 0
        self.in_trap = False
        self.trap_table_base = 0
        self.np = 0           # nursery bump pointer
        self.nl = 0           # nursery limit
        self.tile_id = tile_id
        self.thread_id = thread_id


class LM1Core:
    """Single LM-1 tile emulator."""

    def __init__(self, mem: bytearray, *, tile_id: int = 0):
        self.mem = mem
        self.mem_size = len(mem)
        self.tile_id = tile_id
        # Threads
        self.threads = [LM1Thread(tile_id=tile_id)]
        self.thread = self.threads[0]
        # GC
        self.nursery_base = 0x3_0000
        self.nursery_size = 0x1_0000    # 64 KiB
        self.oldgen_base  = 0x8_0000
        self.oldgen_size  = 0x4_0000    # 256 KiB
        self.oldgen_ptr   = self.oldgen_base
        self.card_table   = bytearray(self.oldgen_size // 256)
        # Header templates
        self.header_templates = [0] * 256
        # Queues
        self.queues: list[deque] = [deque(maxlen=64) for _ in range(4)]
        # Inline cache table: (callsite_pc, shape_id) → target_addr
        self.ic_table: dict[tuple[int, int], int] = {}
        # GC movement queue: list of (op, region_base, region_len) tuples
        self.gc_queue: list[tuple[int, int, int]] = []
        # Acceleration
        self._accel_lib = None
        self._accel_run = None

    def init_nursery(self):
        """Set up nursery pointers on the current thread."""
        t = self.thread
        t.np = self.nursery_base
        t.nl = self.nursery_base + self.nursery_size

    # ── Memory access ────────────────────────────────────────────────
    def _r64(self, addr: int) -> int:
        o = addr % self.mem_size
        return struct.unpack_from("<Q", self.mem, o)[0]

    def _w64(self, addr: int, val: int):
        o = addr % self.mem_size
        struct.pack_into("<Q", self.mem, o, val & MASK64)

    def _r32(self, addr: int) -> int:
        o = addr % self.mem_size
        return struct.unpack_from("<I", self.mem, o)[0]

    # ── Nursery allocation ───────────────────────────────────────────
    def _alloc(self, header: int, n_words: int) -> int:
        """Allocate *n_words* data words + 1 header word in the nursery.
        Returns the tagged ref pointing past the header."""
        t = self.thread
        total = (n_words + 1) * 8
        if t.np + total > t.nl:
            raise LM1Trap(TRAP_NURSERY_OVERFLOW)
        obj_addr = t.np
        self._w64(obj_addr, header)
        # Zero-init data words
        for i in range(n_words):
            self._w64(obj_addr + (i + 1) * 8, NIL)
        t.np += total
        return tag_ref(obj_addr + 8)   # ref points past header

    def _alloc_cons(self) -> int:
        """Allocate a cons cell (header + car + cdr = 3 words = 24 bytes)."""
        t = self.thread
        total = 24
        if t.np + total > t.nl:
            raise LM1Trap(TRAP_NURSERY_OVERFLOW)
        addr = t.np
        self._w64(addr, make_header(HDR_CONS, 2))
        self._w64(addr + 8, NIL)   # car
        self._w64(addr + 16, NIL)  # cdr
        t.np += total
        return tag_cons(addr + 8)

    # ── Write barrier ────────────────────────────────────────────────
    def _write_barrier(self, obj_addr: int, val: int):
        """Mark card dirty if storing a nursery pointer into old-gen."""
        if (self.oldgen_base <= obj_addr < self.oldgen_base + self.oldgen_size
                and self.nursery_base <= val < self.nursery_base + self.nursery_size):
            card = (obj_addr - self.oldgen_base) // 256
            if card < len(self.card_table):
                self.card_table[card] = 1

    # ── Trap delivery ────────────────────────────────────────────────
    def _deliver_trap(self, code: int):
        t = self.thread
        t.trap_cause = code
        t.trap_pc = t.pc
        if t.trap_table_base:
            # Push PC and LR, jump to handler
            t.sp -= 8; self._w64(t.sp, t.lr)
            t.sp -= 8; self._w64(t.sp, t.pc)
            t.lr = t.pc
            t.in_trap = True
            t.pc = t.trap_table_base + code * 8  # handler address table
        else:
            t.halted = True   # no handler → halt

    # ── Simple GC (minor collection) ─────────────────────────────────
    def gc_collect(self):
        """Cheney-copy nursery → old-gen.  Simplified: copies all live objects."""
        t = self.thread
        # Scan roots: registers, stack
        for i in range(32):
            t.regs[i] = self._gc_forward(t.regs[i])
        # Scan stack
        addr = t.sp
        while addr < self.mem_size - 8:
            w = self._r64(addr)
            fw = self._gc_forward(w)
            if fw != w:
                self._w64(addr, fw)
            addr += 8
            if addr > t.sp + 4096:
                break  # safety limit
        # Scan copied objects in old-gen
        scan = self.oldgen_ptr  # start of newly copied data
        # (simplified: not a full Cheney scan)
        # Reset nursery
        t.np = self.nursery_base

    def _gc_forward(self, w: int) -> int:
        """If *w* is a nursery ref/cons, copy the object to old-gen and return forwarded ref."""
        if is_ref(w):
            addr = untag_ref(w) - 8  # header is 8 bytes before ref
            if self.nursery_base <= addr < self.nursery_base + self.nursery_size:
                return self._gc_copy(addr, tag_ref)
        elif is_cons(w):
            addr = untag_cons(w) - 8
            if self.nursery_base <= addr < self.nursery_base + self.nursery_size:
                return self._gc_copy(addr, tag_cons)
        return w

    def _gc_copy(self, header_addr: int, tagger) -> int:
        """Copy an object from nursery to old-gen, return new tagged ref."""
        h = self._r64(header_addr)
        if is_ref(h):
            # Already forwarded — return the forwarding pointer
            return h
        size = header_size(h)
        total = (size + 1) * 8
        dst = self.oldgen_ptr
        if dst + total > self.oldgen_base + self.oldgen_size:
            return tagger(header_addr + 8)  # out of old-gen space, don't copy
        # Copy
        for i in range(0, total, 8):
            self._w64(dst + i, self._r64(header_addr + i))
        self.oldgen_ptr += total
        # Install forwarding pointer
        fwd = tagger(dst + 8)
        self._w64(header_addr, fwd)
        return fwd

    # ── Load program ─────────────────────────────────────────────────
    def load_program(self, words: list[int], base: int = 0):
        """Load 32-bit instruction words into memory."""
        for i, w in enumerate(words):
            struct.pack_into("<I", self.mem, base + i * 4, w & 0xFFFF_FFFF)

    # ═════════════════════════════════════════════════════════════════
    #  MAIN STEP FUNCTION
    # ═════════════════════════════════════════════════════════════════
    def step(self) -> int:
        t = self.thread
        if t.halted:
            return 0

        raw = self._r32(t.pc)
        op   = (raw >> 26) & 0x3F
        rd   = (raw >> 21) & 0x1F
        rs1  = (raw >> 16) & 0x1F
        rs2  = (raw >> 11) & 0x1F
        func = (raw >> 6)  & 0x1F
        imm16 = raw & 0xFFFF
        simm16 = imm16 - 0x10000 if imm16 >= 0x8000 else imm16
        field  = rs2   # alias for S-format
        imm11  = raw & 0x7FF
        simm11 = imm11 - 0x800 if imm11 >= 0x400 else imm11

        R = t.regs
        npc = t.pc + 4

        try:
            # ── HALT / NOP ───────────────────────────────────────
            if op == OP_HALT_NOP:
                sub = raw & 0x03FF_FFFF
                if sub == 0:
                    t.halted = True
                # sub==1 → NOP

            # ── LI (load sign-extended 16-bit immediate) ─────────
            elif op == OP_LI:
                R[rd] = simm16 & MASK64

            # ── LUI (load upper 16 bits into 31:16) ──────────────
            elif op == OP_LUI:
                R[rd] = (R[rd] & ~0xFFFF_0000) | ((imm16 & 0xFFFF) << 16)
                R[rd] &= MASK64

            # ── LI32 (next word is a full 32-bit immediate) ──────
            elif op == OP_LI32:
                imm32 = self._r32(npc)
                npc += 4
                # Sign-extend 32 → 64
                if imm32 >= 0x8000_0000:
                    R[rd] = (imm32 | 0xFFFF_FFFF_0000_0000) & MASK64
                else:
                    R[rd] = imm32

            # ── ARITH_RAW (64-bit arithmetic) ────────────────────
            elif op == OP_ARITH_RAW:
                a, b = R[rs1], R[rs2]
                if func == 0:   R[rd] = (a + b) & MASK64
                elif func == 1: R[rd] = (a - b) & MASK64
                elif func == 2: R[rd] = (a * b) & MASK64
                elif func == 3:
                    if b == 0: raise LM1Trap(TRAP_DIVIDE_BY_ZERO)
                    sa = a if a < (1 << 63) else a - (1 << 64)
                    sb = b if b < (1 << 63) else b - (1 << 64)
                    R[rd] = int(sa / sb) & MASK64
                elif func == 4:
                    if b == 0: raise LM1Trap(TRAP_DIVIDE_BY_ZERO)
                    R[rd] = (a % b) & MASK64

            # ── BITWISE ──────────────────────────────────────────
            elif op == OP_BITWISE:
                a, b = R[rs1], R[rs2]
                if func == 0:   R[rd] = a & b
                elif func == 1: R[rd] = a | b
                elif func == 2: R[rd] = a ^ b
                elif func == 3: R[rd] = (a << (b & 63)) & MASK64
                elif func == 4: R[rd] = (a >> (b & 63)) & MASK64
                elif func == 5:  # ASR
                    sa = a if a < (1 << 63) else a - (1 << 64)
                    R[rd] = (sa >> (b & 63)) & MASK64
                elif func == 6: R[rd] = (~a) & MASK64

            # ── LDR (raw 64-bit load) ────────────────────────────
            elif op == OP_LDR:
                addr = (R[rs1] + simm16 * 8) & MASK64
                R[rd] = self._r64(addr)

            # ── STR (raw 64-bit store) ────────────────────────────
            elif op == OP_STR:
                addr = (R[rd] + simm16 * 8) & MASK64
                self._w64(addr, R[rs1])

            # ── BR (unconditional branch, word offset) ────────────
            elif op == OP_BR:
                npc = (t.pc + simm16 * 4) & MASK64

            # ── BR_COND ──────────────────────────────────────────
            elif op == OP_BR_COND:
                cond = rs1  # condition type in bits 20:16 (rs2 of encode_b)
                w = R[rd]   # value to test in bits 25:21
                taken = False
                if cond == 0:   taken = is_truthy(w)        # BR.T
                elif cond == 1: taken = (w == NIL)           # BR.NIL
                elif cond == 2: taken = is_fixnum(w) and untag_fixnum(w) < 0  # FIX.LT
                elif cond == 3: taken = (w == 0)             # FIX.EQ (fixnum 0)
                elif cond == 4: taken = is_fixnum(w) and untag_fixnum(w) > 0  # FIX.GT
                elif cond == 5: taken = (w == 0)             # EQ (word-equal 0)
                if taken:
                    npc = (t.pc + simm16 * 4) & MASK64

            # ── PUSH / POP ───────────────────────────────────────
            elif op == OP_PUSH_POP:
                if func == 0:  # PUSH
                    t.sp = (t.sp - 8) & MASK64
                    self._w64(t.sp, R[rs1])
                elif func == 1:  # POP
                    R[rd] = self._r64(t.sp)
                    t.sp = (t.sp + 8) & MASK64

            # ── PUSH_MULTI / POP_MULTI ───────────────────────────
            elif op == OP_PUSH_MULTI:
                mask = imm16
                for i in range(31, -1, -1):
                    if mask & (1 << i):
                        t.sp = (t.sp - 8) & MASK64
                        self._w64(t.sp, R[i])
            elif op == OP_POP_MULTI:
                mask = imm16
                for i in range(32):
                    if mask & (1 << i):
                        R[i] = self._r64(t.sp)
                        t.sp = (t.sp + 8) & MASK64

            # ── TST (type test) ──────────────────────────────────
            elif op == OP_TST:
                w = R[rs1]
                tag = imm16 & 7
                result = False
                if tag == 0:   result = is_fixnum(w)
                elif tag == 1: result = is_ref(w)
                elif tag == 2: result = is_cons(w)
                elif tag == 3: result = is_special(w)
                elif tag == 4: result = (w == NIL)
                R[rd] = T.T if result else NIL

            # ── TST.SHAPE (check object shape/class id) ──────────
            elif op == OP_TST_SHAPE:
                w = R[rs1]
                expected_shape = imm16
                if is_ref(w):
                    obj_addr = untag_ref(w)
                    hdr = self._r64(obj_addr - 8)
                    obj_shape = (hdr >> 24) & 0xFFFF_FFFF
                    R[rd] = T.T if obj_shape == expected_shape else NIL
                else:
                    R[rd] = NIL

            # ── ARITH_FIX (tagged fixnum arithmetic) ─────────────
            elif op == OP_ARITH_FIX:
                a, b = R[rs1], R[rs2]
                if not is_fixnum(a): raise LM1Trap(TRAP_NOT_FIXNUM)
                if not is_fixnum(b): raise LM1Trap(TRAP_NOT_FIXNUM)
                va, vb = untag_fixnum(a), untag_fixnum(b)
                if func == 0:   R[rd] = tag_fixnum(va + vb)
                elif func == 1: R[rd] = tag_fixnum(va - vb)
                elif func == 2: R[rd] = tag_fixnum(va * vb)
                elif func == 3:
                    if vb == 0: raise LM1Trap(TRAP_DIVIDE_BY_ZERO)
                    R[rd] = tag_fixnum(int(va / vb))

            # ── ADD.FIX.IMM ──────────────────────────────────────
            elif op == OP_ADD_FIX_IMM:
                a = R[rs1]
                if not is_fixnum(a): raise LM1Trap(TRAP_NOT_FIXNUM)
                # immediate is the mathematical value; tag it before adding
                R[rd] = (a + tag_fixnum(simm16)) & MASK64

            # ── CMP_TAGGED ───────────────────────────────────────
            elif op == OP_CMP_TAGGED:
                a, b = R[rs1], R[rs2]
                if func == 0:  # CMP → fixnum(-1/0/1)
                    if a == b:      R[rd] = tag_fixnum(0)
                    elif is_fixnum(a) and is_fixnum(b):
                        va, vb = untag_fixnum(a), untag_fixnum(b)
                        R[rd] = tag_fixnum(-1 if va < vb else 1)
                    else:
                        R[rd] = tag_fixnum(-1 if a < b else 1)
                elif func == 1:  # EQ
                    R[rd] = T.T if a == b else NIL

            # ── ALLOC ────────────────────────────────────────────
            elif op == OP_ALLOC:
                payload = raw & 0x03FF_FFFF
                alloc_rd = (payload >> 21) & 0x1F
                words    = (payload >> 11) & 0x3FF
                tmpl     = payload & 0x7FF
                hdr = self.header_templates[tmpl] if tmpl < len(self.header_templates) and self.header_templates[tmpl] else make_header(HDR_INSTANCE, words)
                R[alloc_rd] = self._alloc(hdr, words)

            # ── ALLOC.CONS ───────────────────────────────────────
            elif op == OP_ALLOC_CONS:
                payload = raw & 0x03FF_FFFF
                alloc_rd = (payload >> 21) & 0x1F
                R[alloc_rd] = self._alloc_cons()

            # ── ALLOCV (variable-size allocation) ────────────────
            elif op == OP_ALLOCV:
                payload = raw & 0x03FF_FFFF
                alloc_rd = (payload >> 21) & 0x1F
                size_reg = (payload >> 16) & 0x1F
                words = R[size_reg]
                if is_fixnum(words):
                    words = untag_fixnum(words)
                hdr = make_header(HDR_INSTANCE, words)
                R[alloc_rd] = self._alloc(hdr, words)

            # ── ALLOC.CLOSURE ────────────────────────────────────
            elif op == OP_ALLOC_CLOSURE:
                payload = raw & 0x03FF_FFFF
                alloc_rd = (payload >> 21) & 0x1F
                code_reg = (payload >> 16) & 0x1F
                env_words = (payload >> 6) & 0x3FF
                hdr = make_header(HDR_CLOSURE, env_words + 1)  # +1 for code ptr
                ref = self._alloc(hdr, env_words + 1)
                addr = untag_ref(ref)
                self._w64(addr, R[code_reg])  # store code pointer at slot 0
                R[alloc_rd] = ref

            # ── LD (tagged field load) ───────────────────────────
            elif op == OP_LD:
                base_val = R[rs1]
                if not (is_ref(base_val) or is_cons(base_val)):
                    raise LM1Trap(TRAP_NOT_REF)
                base_addr = untag_ref(base_val) if is_ref(base_val) else untag_cons(base_val)
                R[rd] = self._r64((base_addr + imm16 * 8) & MASK64)

            # ── LD.CAR / LD.CDR ──────────────────────────────────
            elif op == OP_LD_CAR_CDR:
                w = R[rs1]
                if not is_cons(w): raise LM1Trap(TRAP_NOT_CONS)
                addr = untag_cons(w)
                if imm16 == 0:  # CAR
                    R[rd] = self._r64(addr)
                else:           # CDR
                    R[rd] = self._r64(addr + 8)

            # ── ST (field store, no barrier) ─────────────────────
            elif op == OP_ST:
                base_val = R[rd]
                if not (is_ref(base_val) or is_cons(base_val)):
                    raise LM1Trap(TRAP_NOT_REF)
                base_addr = untag_ref(base_val) if is_ref(base_val) else untag_cons(base_val)
                self._w64((base_addr + field * 8) & MASK64, R[rs1])

            # ── ST.WB (field store with write barrier) ───────────
            elif op == OP_ST_WB:
                base_val = R[rd]
                if not (is_ref(base_val) or is_cons(base_val)):
                    raise LM1Trap(TRAP_NOT_REF)
                base_addr = untag_ref(base_val) if is_ref(base_val) else untag_cons(base_val)
                store_addr = (base_addr + field * 8) & MASK64
                val = R[rs1]
                self._w64(store_addr, val)
                self._write_barrier(store_addr, val)

            # ── ST.CAR / ST.CDR ──────────────────────────────────
            elif op == OP_ST_CAR_CDR:
                w = R[rd]
                if not is_cons(w): raise LM1Trap(TRAP_NOT_CONS)
                addr = untag_cons(w)
                if field == 0:
                    self._w64(addr, R[rs1])
                else:
                    self._w64(addr + 8, R[rs1])

            # ── CALL.DIRECT ──────────────────────────────────────
            elif op == OP_CALL_DIRECT:
                payload = raw & 0x03FF_FFFF
                rs = (payload >> 21) & 0x1F
                target = R[rs]
                # Save return address
                t.sp -= 8; self._w64(t.sp, npc)
                t.sp -= 8; self._w64(t.sp, t.fp)
                t.fp = t.sp
                t.lr = npc
                npc = target

            # ── CALL.IC (inline-cache call) ──────────────────────
            elif op == OP_CALL_IC:
                callsite = t.pc  # current PC as callsite key
                shape_id = R[rs2] & MASK64
                key = (callsite, shape_id)
                if key in self.ic_table:
                    target = self.ic_table[key]
                    t.sp -= 8; self._w64(t.sp, npc)
                    t.sp -= 8; self._w64(t.sp, t.fp)
                    t.fp = t.sp
                    t.lr = npc
                    npc = target
                else:
                    raise LM1Trap(TRAP_IC_MISS)

            # ── IC.INSTALL (install IC entry) ────────────────────
            elif op == OP_IC_INSTALL:
                entry_target = R[rs1]
                callsite_pc = R[rs2]
                shape_id = R[rd]
                self.ic_table[(callsite_pc, shape_id)] = entry_target

            # ── CALL.CLOSURE ─────────────────────────────────────
            elif op == OP_CALL_CLOSURE:
                payload = raw & 0x03FF_FFFF
                rs = (payload >> 21) & 0x1F
                closure = R[rs]
                if not is_ref(closure):
                    raise LM1Trap(TRAP_NOT_CLOSURE)
                closure_addr = untag_ref(closure)
                target = self._r64(closure_addr)  # code pointer at slot 0
                t.sp -= 8; self._w64(t.sp, npc)
                t.sp -= 8; self._w64(t.sp, t.fp)
                t.fp = t.sp
                t.lr = npc
                npc = target

            # ── RET ──────────────────────────────────────────────
            elif op == OP_RET:
                t.sp = t.fp
                t.fp = self._r64(t.sp); t.sp += 8
                npc = self._r64(t.sp);  t.sp += 8

            # ── TAILCALL.DIRECT ──────────────────────────────────
            elif op == OP_TAILCALL_DIRECT:
                payload = raw & 0x03FF_FFFF
                rs = (payload >> 21) & 0x1F
                npc = R[rs]
                # Don't create new frame — reuse current

            # ── TAILCALL.IC (tail inline-cache call) ─────────────
            elif op == OP_TAILCALL_IC:
                callsite = t.pc
                shape_id = R[rs2] & MASK64
                key = (callsite, shape_id)
                if key in self.ic_table:
                    npc = self.ic_table[key]
                else:
                    raise LM1Trap(TRAP_IC_MISS)

            # ── TRAP ─────────────────────────────────────────────
            elif op == OP_TRAP:
                code = raw & 0x03FF_FFFF
                raise LM1Trap(code)

            # ── ERET ─────────────────────────────────────────────
            elif op == OP_ERET:
                npc = self._r64(t.sp); t.sp += 8
                t.lr = self._r64(t.sp); t.sp += 8
                t.in_trap = False

            # ── SYS_INFO ─────────────────────────────────────────
            elif op == OP_SYS_INFO:
                payload = raw & 0x03FF_FFFF
                info_rd = (payload >> 21) & 0x1F
                sub = payload & 0x1F
                if sub == 0:   R[info_rd] = t.tile_id
                elif sub == 1: R[info_rd] = t.thread_id
                elif sub == 2: R[info_rd] = t.cycle_count
                elif sub == 3: R[info_rd] = t.trap_cause
                elif sub == 4: R[info_rd] = t.trap_pc

            # ── Prefetch (no-ops) ────────────────────────────────
            elif 32 <= op <= 35:
                pass

            # ── SEND (enqueue to HW queue) ───────────────────────
            elif op == OP_SEND:
                queue_id = imm16 & 3
                val = R[rs1]
                q = self.queues[queue_id]
                if len(q) < q.maxlen:
                    q.append(val)
                # Silently drop if full

            # ── RECV / TRY.RECV ──────────────────────────────────
            elif op == OP_RECV:
                queue_id = imm16 & 3
                q = self.queues[queue_id]
                if func == 0:  # RECV (blocking → here we just return 0 if empty)
                    R[rd] = q.popleft() if q else 0
                elif func == 1:  # TRY.RECV → rd=value, rd+1=success flag
                    if q:
                        R[rd] = q.popleft()
                        if rd + 1 < 32:
                            R[rd + 1] = T.T
                    else:
                        R[rd] = NIL
                        if rd + 1 < 32:
                            R[rd + 1] = NIL

            # ── CAS.TAGGED ───────────────────────────────────────
            elif op == OP_CAS_TAGGED:
                addr = R[rs1]
                old_val = R[rs2]
                new_val = R[rd]
                current = self._r64(addr)
                if current == old_val:
                    self._w64(addr, new_val)
                    R[rd] = T.T
                else:
                    R[rd] = NIL

            # ── FAA / FENCE.GC ───────────────────────────────────
            elif op == OP_FAA_FENCE:
                if func == 0:  # FAA
                    addr = R[rs1]
                    old = self._r64(addr)
                    self._w64(addr, (old + R[rs2]) & MASK64)
                    R[rd] = old
                # func==31 → FENCE.GC (no-op in single-threaded emulator)

            # ── GC Movement Engines (ENQ.SCAN/COPY/FIXUP/COMPACT) ─
            elif op in (OP_ENQ_SCAN, OP_ENQ_COPY, OP_ENQ_FIXUP, OP_ENQ_COMPACT):
                region_base = R[rs1]
                region_len = R[rs2]
                self.gc_queue.append((op, region_base, region_len))
                R[rd] = len(self.gc_queue)  # return queue depth

            else:
                raise LM1Trap(TRAP_UNIMPLEMENTED)

        except LM1Trap as trap:
            if trap.code == TRAP_NURSERY_OVERFLOW:
                self.gc_collect()
                return 1  # retry instruction (don't advance PC)
            self._deliver_trap(trap.code)
            return 1

        t.pc = npc
        t.cycle_count += 1
        return 1

    def run(self, max_steps: int = 0) -> int:
        n = 0
        while not self.thread.halted:
            self.step()
            n += 1
            if max_steps and n >= max_steps:
                break
        return n

    # ═════════════════════════════════════════════════════════════════
    #  C ACCELERATION
    # ═════════════════════════════════════════════════════════════════
    def load_accel(self, path: str | Path | None = None) -> bool:
        if path is None:
            d = Path(__file__).resolve().parent.parent.parent / "accel"
            path = d / "lm1_accel.so"
        path = Path(path)
        if not path.exists():
            return False
        try:
            lib = ctypes.CDLL(str(path))
        except OSError:
            return False
        lib.lm1_run.argtypes = [
            ctypes.POINTER(CLM1State),
            ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int,
        ]
        lib.lm1_run.restype = CLM1Result
        self._accel_lib = lib
        self._accel_run = lib.lm1_run
        return True

    def _sync_to_c(self) -> "CLM1State":
        s = CLM1State()
        t = self.thread
        for i in range(32):
            s.regs[i] = t.regs[i]
        s.pc = t.pc
        s.sp = t.sp
        s.fp = t.fp
        s.lr = t.lr
        s.halted = int(t.halted)
        s.cycle_count = t.cycle_count
        return s

    def _sync_from_c(self, s: "CLM1State"):
        t = self.thread
        for i in range(32):
            t.regs[i] = s.regs[i]
        t.pc = s.pc
        t.sp = s.sp
        t.fp = s.fp
        t.lr = s.lr
        t.halted = bool(s.halted)
        t.cycle_count = s.cycle_count

    def run_accel(self, max_steps: int = 100_000) -> int:
        if self._accel_run is None:
            return self.run(max_steps)
        total = 0
        remaining = max_steps
        while remaining > 0 and not self.thread.halted:
            cs = self._sync_to_c()
            mem_buf = (ctypes.c_char * self.mem_size).from_buffer(self.mem)
            result = self._accel_run(
                ctypes.byref(cs), mem_buf, self.mem_size, remaining,
            )
            self._sync_from_c(cs)
            total += result.steps_executed
            remaining -= result.steps_executed
            if result.stop_reason == 0:
                break  # max steps
            if result.stop_reason == 1:
                break  # halt
            if result.stop_reason == 3:  # fallback
                self.step()
                remaining -= 1
                total += 1
        return total


# ── ctypes structs for C acceleration ────────────────────────────────
class CLM1State(ctypes.Structure):
    _fields_ = [
        ("regs", ctypes.c_uint64 * 32),
        ("pc", ctypes.c_uint64),
        ("sp", ctypes.c_uint64),
        ("fp", ctypes.c_uint64),
        ("lr", ctypes.c_uint64),
        ("halted", ctypes.c_uint8),
        ("_pad", ctypes.c_uint8 * 7),
        ("cycle_count", ctypes.c_uint64),
    ]

class CLM1Result(ctypes.Structure):
    _fields_ = [
        ("steps_executed", ctypes.c_int32),
        ("stop_reason", ctypes.c_int32),   # 0=max, 1=halt, 3=fallback
    ]
