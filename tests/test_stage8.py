"""Stage 8: DMA engine, GC movement opcodes, Inline Cache, Framebuffer, and
missing LM-1 opcodes (TST.SHAPE, ALLOCV, ALLOC.CLOSURE, CALL.CLOSURE).
Also tests new MP64 CSRs (DMA, QoS, BIST, I-cache, barrier).
"""
from __future__ import annotations

import struct
import pytest

from chimera.devices.dma import DMAEngine
from chimera.devices.framebuffer import Framebuffer
from chimera.devices.bus import DeviceBus

from chimera.mp64.core import MP64Core

from chimera.lm1.core import LM1Core, LM1Trap, TRAP_IC_MISS
from chimera.lm1.core import (
    OP_TST_SHAPE, OP_ALLOCV, OP_ALLOC_CLOSURE, OP_CALL_CLOSURE,
    OP_CALL_IC, OP_IC_INSTALL, OP_TAILCALL_IC,
    OP_ENQ_SCAN, OP_ENQ_COPY, OP_ENQ_FIXUP, OP_ENQ_COMPACT,
    OP_CALL_DIRECT, OP_RET, OP_HALT_NOP,
)
from chimera.lm1.tagged import (
    tag_fixnum, untag_fixnum, tag_ref, untag_ref,
    make_header, HDR_INSTANCE, HDR_CLOSURE, is_ref, MASK64, NIL,
)


# ═════════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════════

def _lm1_encode(op, rd=0, rs1=0, rs2=0, imm16=0, func=0):
    """Encode a 32-bit LM-1 instruction."""
    w = (op & 0x3F) << 26
    w |= (rd & 0x1F) << 21
    w |= (rs1 & 0x1F) << 16
    w |= (rs2 & 0x1F) << 11
    w |= (func & 0x1F) << 6
    w |= imm16 & 0xFFFF
    return w


def _lm1_write_instr(mem, addr, instr):
    struct.pack_into("<I", mem, addr, instr)


def _make_lm1(prog_words, tgt_addr=0x1000, sp=0x2_0000):
    """Create an LM1Core, write program at tgt_addr, set PC&SP."""
    mem = bytearray(1 << 20)
    for i, w in enumerate(prog_words):
        _lm1_write_instr(mem, tgt_addr + i * 4, w)
    core = LM1Core(mem)
    core.init_nursery()
    core.thread.pc = tgt_addr
    core.thread.sp = sp
    core.thread.fp = sp
    return core


# ═════════════════════════════════════════════════════════════════════
#  DMA Engine
# ═════════════════════════════════════════════════════════════════════

class TestDMAEngine:
    def test_register_readback(self):
        dma = DMAEngine()
        dma.ring_base = 0x1000
        for i in range(8):
            assert dma.read8(0x00 + i) == ((0x1000 >> (i * 8)) & 0xFF)

    def test_simple_transfer(self):
        """DMA copies data from src to dst in memory."""
        mem = bytearray(4096)
        # Source data
        mem[0x100:0x108] = b"DMA TEST"

        dma = DMAEngine()
        dma._mem_read = lambda a: mem[a % len(mem)]
        dma._mem_write = lambda a, v: mem.__setitem__(a % len(mem), v)

        # Build descriptor ring at 0x200
        ring_addr = 0x200
        # Descriptor 0: src=0x100, dst=0x300, len=8, flags=valid
        struct.pack_into("<Q", mem, ring_addr + 0x00, 0x100)  # SRC
        struct.pack_into("<Q", mem, ring_addr + 0x08, 0x300)  # DST
        struct.pack_into("<I", mem, ring_addr + 0x10, 8)       # LENGTH
        struct.pack_into("<I", mem, ring_addr + 0x14, 0x01)    # FLAGS: valid
        struct.pack_into("<I", mem, ring_addr + 0x18, 0)       # STATUS: pending

        dma.ring_base = ring_addr
        dma.ring_size = 4  # 4 entries
        dma.head = 0
        dma.tail = 1
        dma.ctrl = 0x01  # enable

        dma.process()

        assert mem[0x300:0x308] == b"DMA TEST"
        assert dma.xfer_count == 1
        # Descriptor status should be 1 (done)
        assert struct.unpack_from("<I", mem, ring_addr + 0x18)[0] == 1

    def test_ctrl_reset(self):
        dma = DMAEngine()
        dma.xfer_count = 10
        dma.head = 5
        dma._execute_ctrl(0x04)  # reset
        assert dma.xfer_count == 0
        assert dma.head == 0
        assert dma.ctrl == 0

    def test_ctrl_start(self):
        """CTRL bit1 triggers process()."""
        mem = bytearray(4096)
        mem[0x10:0x14] = b"ABCD"

        dma = DMAEngine()
        dma._mem_read = lambda a: mem[a % len(mem)]
        dma._mem_write = lambda a, v: mem.__setitem__(a % len(mem), v)

        ring_addr = 0x100
        struct.pack_into("<Q", mem, ring_addr, 0x10)       # SRC
        struct.pack_into("<Q", mem, ring_addr + 8, 0x50)   # DST
        struct.pack_into("<I", mem, ring_addr + 16, 4)     # LENGTH
        struct.pack_into("<I", mem, ring_addr + 20, 1)     # FLAGS: valid

        dma.ring_base = ring_addr
        dma.ring_size = 2
        dma.head = 0
        dma.tail = 1
        dma._execute_ctrl(0x03)  # enable + start
        assert mem[0x50:0x54] == b"ABCD"

    def test_bus_registration(self):
        bus = DeviceBus()
        dma = DMAEngine()
        bus.register(0x0B00, 0x40, dma)
        # Write ring_base via bus
        base = bus.base
        bus.write(base + 0x0B00, 0x42)
        assert dma.ring_base & 0xFF == 0x42


# ═════════════════════════════════════════════════════════════════════
#  Framebuffer
# ═════════════════════════════════════════════════════════════════════

class TestFramebuffer:
    def test_present_bit(self):
        fb = Framebuffer()
        assert fb.read8(0x01) & 0x80

    def test_default_resolution(self):
        fb = Framebuffer(320, 240)
        w = fb.read8(0x02) | (fb.read8(0x03) << 8)
        h = fb.read8(0x04) | (fb.read8(0x05) << 8)
        assert w == 320
        assert h == 240

    def test_bpp_from_mode(self):
        fb = Framebuffer()
        assert fb.read8(0x07) == 2  # RGB565 → 2 bpp
        fb.write8(0x06, 2)  # RGBA8888
        assert fb.read8(0x07) == 4

    def test_fb_size(self):
        fb = Framebuffer(320, 240, mode=0)  # RGB565
        assert fb.fb_size == 320 * 240 * 2

    def test_flip_increments_frame(self):
        fb = Framebuffer()
        fb.write8(0x00, 0x02)  # FLIP
        fb.write8(0x00, 0x02)  # FLIP
        assert fb.frame_count == 2
        assert fb.vsync

    def test_sync_clears_vsync(self):
        fb = Framebuffer()
        fb.write8(0x00, 0x02)  # FLIP
        assert fb.vsync
        fb.write8(0x00, 0x03)  # SYNC
        assert not fb.vsync

    def test_fb_base_readback(self):
        fb = Framebuffer()
        fb.fb_base = 0xDEAD_BEEF
        b0 = fb.read8(0x08)
        b1 = fb.read8(0x09)
        b2 = fb.read8(0x0A)
        b3 = fb.read8(0x0B)
        assert b0 == 0xEF
        assert b1 == 0xBE
        assert b2 == 0xAD
        assert b3 == 0xDE


# ═════════════════════════════════════════════════════════════════════
#  MP64 — New CSRs (DMA, QoS, BIST, I-cache, Barrier)
# ═════════════════════════════════════════════════════════════════════

class TestMP64NewCSRs:
    def _core(self):
        mem = bytearray(4096)
        return MP64Core(mem)

    def test_dma_csrs(self):
        c = self._core()
        c._csr_write(0x50, 0x1000)
        assert c._csr_read(0x50) == 0x1000
        c._csr_write(0x51, 8)
        assert c._csr_read(0x51) == 8
        c._csr_write(0x52, 2)
        assert c._csr_read(0x52) == 2
        # DMA_STATUS is read-only
        assert c._csr_read(0x54) == 0

    def test_qos_csrs(self):
        c = self._core()
        c._csr_write(0x58, 4)
        assert c._csr_read(0x58) == 4
        c._csr_write(0x59, 1000)
        assert c._csr_read(0x59) == 1000

    def test_bist_csrs(self):
        c = self._core()
        c._csr_write(0x60, 1)
        assert c._csr_read(0x60) == 1
        assert c._csr_read(0x61) == 0  # BIST_STATUS = pass

    def test_icache_csrs(self):
        c = self._core()
        c._csr_write(0x70, 0x01)  # enable
        assert c._csr_read(0x70) == 1
        assert c._csr_read(0x71) == 0  # hits
        assert c._csr_read(0x72) == 0  # misses

    def test_cluster_csrs(self):
        c = self._core()
        c._csr_write(0x6D, 1)
        assert c._csr_read(0x6D) == 1
        c._csr_write(0x6E, 0xA000)
        assert c._csr_read(0x6E) == 0xA000

    def test_barrier_csrs(self):
        c = self._core()
        c._csr_write(0x74, 0xFF)
        assert c._csr_read(0x74) == 0xFF
        assert c._csr_read(0x75) == 0  # no barrier active


# ═════════════════════════════════════════════════════════════════════
#  LM-1 — Inline Cache
# ═════════════════════════════════════════════════════════════════════

class TestLM1InlineCache:
    def test_ic_install_and_call(self):
        """Install an IC entry, then CALL.IC resolves it."""
        # Set up IC entry: shape=42 at callsite=0x1000 → target=0x2000
        # Build a tiny function at 0x2000 that does R5 = fixnum(99), then HALT
        halt_w = _lm1_encode(OP_HALT_NOP, func=0)
        prog = [
            # 0x1000: IC.INSTALL rs1=R1(entry), rs2=R2(callsite), rd=R3(shape)
            _lm1_encode(OP_IC_INSTALL, rd=3, rs1=1, rs2=2),
            # 0x1004: CALL.IC rd=0, rs1=0, rs2=R3(shape)
            _lm1_encode(OP_CALL_IC, rd=0, rs1=0, rs2=3),
            # 0x1008: (return here) HALT
            halt_w,
        ]
        core = _make_lm1(prog)
        # R1 = target address = 0x2000
        core.thread.regs[1] = 0x2000
        # R2 = callsite PC = 0x1004 (the CALL.IC instruction)
        core.thread.regs[2] = 0x1004
        # R3 = shape_id = 42
        core.thread.regs[3] = 42

        # Place target function at 0x2000: LI R5, 99; RET
        _lm1_write_instr(core.mem, 0x2000, _lm1_encode(55, rd=5, imm16=99))  # LI R5, 99
        _lm1_write_instr(core.mem, 0x2004, _lm1_encode(OP_RET))
        _lm1_write_instr(core.mem, 0x2008, halt_w)

        # Step: IC.INSTALL
        core.step()
        assert (0x1004, 42) in core.ic_table
        assert core.ic_table[(0x1004, 42)] == 0x2000

        # Step: CALL.IC → should jump to 0x2000
        core.step()
        assert core.thread.pc == 0x2000

        # Run to completion
        core.run(10)
        assert core.thread.regs[5] == 99

    def test_ic_miss_traps(self):
        """CALL.IC with no installed entry raises TRAP_IC_MISS."""
        prog = [
            _lm1_encode(OP_CALL_IC, rd=0, rs1=0, rs2=1),
            _lm1_encode(OP_HALT_NOP, func=0),
        ]
        core = _make_lm1(prog)
        core.thread.regs[1] = 99  # shape_id = 99
        # Should trap — trap handler will be entered
        core.step()
        assert core.thread.trap_cause == TRAP_IC_MISS

    def test_tailcall_ic(self):
        """TAILCALL.IC reuses current frame."""
        prog = [
            _lm1_encode(OP_IC_INSTALL, rd=3, rs1=1, rs2=2),
            _lm1_encode(OP_TAILCALL_IC, rd=0, rs1=0, rs2=3),
        ]
        core = _make_lm1(prog)
        core.thread.regs[1] = 0x2000  # target
        core.thread.regs[2] = 0x1004  # callsite
        core.thread.regs[3] = 7       # shape_id
        _lm1_write_instr(core.mem, 0x2000, _lm1_encode(OP_HALT_NOP, func=0))

        old_sp = core.thread.sp
        core.step()  # IC.INSTALL
        core.step()  # TAILCALL.IC
        # SP should not change (no new frame)
        assert core.thread.sp == old_sp
        assert core.thread.pc == 0x2000


# ═════════════════════════════════════════════════════════════════════
#  LM-1 — GC Movement Engines
# ═════════════════════════════════════════════════════════════════════

class TestLM1GCEngines:
    def test_enq_scan(self):
        prog = [
            _lm1_encode(OP_ENQ_SCAN, rd=3, rs1=1, rs2=2),
            _lm1_encode(OP_HALT_NOP, func=0),
        ]
        core = _make_lm1(prog)
        core.thread.regs[1] = 0x5000  # region_base
        core.thread.regs[2] = 0x1000  # region_len
        core.step()
        assert len(core.gc_queue) == 1
        assert core.gc_queue[0] == (OP_ENQ_SCAN, 0x5000, 0x1000)
        assert core.thread.regs[3] == 1  # queue depth

    def test_all_gc_ops(self):
        """All four GC ops enqueue correctly."""
        ops = [OP_ENQ_SCAN, OP_ENQ_COPY, OP_ENQ_FIXUP, OP_ENQ_COMPACT]
        prog = [_lm1_encode(op, rd=3, rs1=1, rs2=2) for op in ops]
        prog.append(_lm1_encode(OP_HALT_NOP, func=0))
        core = _make_lm1(prog)
        core.thread.regs[1] = 0x8000
        core.thread.regs[2] = 256
        core.run(5)
        assert len(core.gc_queue) == 4
        for i, expected_op in enumerate(ops):
            assert core.gc_queue[i][0] == expected_op

    def test_gc_queue_depth_in_rd(self):
        """Rd gets the current queue depth after enqueue."""
        prog = [
            _lm1_encode(OP_ENQ_SCAN, rd=3, rs1=1, rs2=2),
            _lm1_encode(OP_ENQ_COPY, rd=4, rs1=1, rs2=2),
            _lm1_encode(OP_HALT_NOP, func=0),
        ]
        core = _make_lm1(prog)
        core.thread.regs[1] = 0x1000
        core.thread.regs[2] = 64
        core.run(3)
        assert core.thread.regs[3] == 1
        assert core.thread.regs[4] == 2


# ═════════════════════════════════════════════════════════════════════
#  LM-1 — Missing opcodes: TST.SHAPE, ALLOCV, ALLOC.CLOSURE, CALL.CLOSURE
# ═════════════════════════════════════════════════════════════════════

class TestLM1MissingOps:
    def test_tst_shape_match(self):
        """TST.SHAPE returns T when shape matches."""
        core = _make_lm1([
            _lm1_encode(OP_TST_SHAPE, rd=3, rs1=1, imm16=0x0042),
            _lm1_encode(OP_HALT_NOP, func=0),
        ])
        core.init_nursery()
        # Create a fake object at 0x3000 with header containing shape 0x42
        hdr = make_header(HDR_INSTANCE, 2, shape=0x42)
        struct.pack_into("<Q", core.mem, 0x3000, hdr)
        core.thread.regs[1] = tag_ref(0x3008)  # ref points past header
        core.run(2)
        assert core.thread.regs[3] != 0  # truthy

    def test_tst_shape_mismatch(self):
        """TST.SHAPE returns NIL on mismatch."""
        core = _make_lm1([
            _lm1_encode(OP_TST_SHAPE, rd=3, rs1=1, imm16=0x0099),
            _lm1_encode(OP_HALT_NOP, func=0),
        ])
        hdr = make_header(HDR_INSTANCE, 2, shape=0x42)
        struct.pack_into("<Q", core.mem, 0x3000, hdr)
        core.thread.regs[1] = tag_ref(0x3008)
        core.run(2)
        assert core.thread.regs[3] == NIL  # shape mismatch → NIL

    def test_allocv(self):
        """ALLOCV allocates variable-sized objects."""
        core = _make_lm1([
            # ALLOCV: rd=3, size from R1
            _lm1_encode(OP_ALLOCV, rd=3, rs1=0, rs2=0,
                        imm16=(3 << 5) | (1 << 0)),  # pack alloc_rd=3, size_reg=R1
            _lm1_encode(OP_HALT_NOP, func=0),
        ])
        # Actually, the encoding is: payload = (alloc_rd<<21)|(size_reg<<16)|...
        # Let me re-encode properly
        alloc_rd = 3
        size_reg = 1
        payload = (alloc_rd << 21) | (size_reg << 16)
        raw = (OP_ALLOCV << 26) | (payload & 0x03FF_FFFF)
        _lm1_write_instr(core.mem, 0x1000, raw)

        core.init_nursery()
        core.thread.regs[1] = tag_fixnum(4)  # allocate 4 words
        core.run(2)
        ref = core.thread.regs[3]
        assert is_ref(ref)

    def test_alloc_closure(self):
        """ALLOC.CLOSURE creates a closure with code pointer at slot 0."""
        core = _make_lm1([_lm1_encode(OP_HALT_NOP, func=0)] * 3)
        # Encode: alloc_rd=3, code_reg=R1, env_words=2
        alloc_rd = 3
        code_reg = 1
        env_words = 2
        payload = (alloc_rd << 21) | (code_reg << 16) | (env_words << 6)
        raw = (OP_ALLOC_CLOSURE << 26) | (payload & 0x03FF_FFFF)
        _lm1_write_instr(core.mem, 0x1000, raw)
        _lm1_write_instr(core.mem, 0x1004, _lm1_encode(OP_HALT_NOP, func=0))

        core.init_nursery()
        core.thread.regs[1] = 0xBEEF  # code pointer
        core.run(2)
        ref = core.thread.regs[3]
        assert is_ref(ref)
        # Slot 0 should be code pointer
        addr = untag_ref(ref)
        code_ptr = struct.unpack_from("<Q", core.mem, addr % core.mem_size)[0]
        assert code_ptr == 0xBEEF

    def test_call_closure(self):
        """CALL.CLOSURE reads target from slot 0 and calls."""
        core = _make_lm1([_lm1_encode(OP_HALT_NOP, func=0)] * 5)
        # First allocate a closure
        alloc_rd = 3
        code_reg = 1
        env_words = 1
        payload = (alloc_rd << 21) | (code_reg << 16) | (env_words << 6)
        raw_alloc = (OP_ALLOC_CLOSURE << 26) | (payload & 0x03FF_FFFF)
        _lm1_write_instr(core.mem, 0x1000, raw_alloc)
        # Then call it: CALL.CLOSURE R3
        call_payload = (3 << 21)  # rs = R3
        raw_call = (OP_CALL_CLOSURE << 26) | (call_payload & 0x03FF_FFFF)
        _lm1_write_instr(core.mem, 0x1004, raw_call)
        _lm1_write_instr(core.mem, 0x1008, _lm1_encode(OP_HALT_NOP, func=0))

        # Target function at 0x4000
        _lm1_write_instr(core.mem, 0x4000, _lm1_encode(OP_HALT_NOP, func=0))

        core.init_nursery()
        core.thread.regs[1] = 0x4000  # code pointer
        core.step()  # ALLOC.CLOSURE
        core.step()  # CALL.CLOSURE
        assert core.thread.pc == 0x4000
