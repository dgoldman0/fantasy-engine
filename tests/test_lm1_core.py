"""Tests for the LM-1 Lisp Machine tile emulator (Stage 3)."""
from __future__ import annotations
import struct, pytest
from chimera.lm1.core import LM1Core, LM1Thread, LM1Trap
from chimera.lm1 import tagged as T, asm as A

# ── Helpers ──────────────────────────────────────────────────────────
MEMSZ = 1 << 20  # 1 MiB

def make_core(prog: list[int], *, sp: int = 0x2_0000) -> LM1Core:
    """Create an LM1Core, load *prog* at address 0, set SP."""
    mem = bytearray(MEMSZ)
    c = LM1Core(mem)
    c.load_program(prog)
    c.thread.sp = sp
    c.thread.fp = sp
    c.init_nursery()
    return c

def run_prog(prog: list[int], **kw) -> LM1Core:
    c = make_core(prog, **kw)
    c.run(max_steps=10_000)
    return c


# ═════════════════════════════════════════════════════════════════════
#  1. SCALAR OPERATIONS
# ═════════════════════════════════════════════════════════════════════

class TestScalarArith:
    def test_add(self):
        c = run_prog(A.program(
            A.li(1, 10), A.li(2, 20),
            A.add(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 30

    def test_sub(self):
        c = run_prog(A.program(
            A.li(1, 100), A.li(2, 37),
            A.sub(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 63

    def test_mul(self):
        c = run_prog(A.program(
            A.li(1, 7), A.li(2, 6),
            A.mul(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 42

    def test_div(self):
        c = run_prog(A.program(
            A.li(1, 100), A.li(2, 7),
            A.div(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 14  # truncated toward zero

    def test_mod(self):
        c = run_prog(A.program(
            A.li(1, 100), A.li(2, 7),
            A.mod(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 2

    def test_sub_negative(self):
        c = run_prog(A.program(
            A.li(1, 5), A.li(2, 10),
            A.sub(3, 1, 2), A.halt(),
        ))
        # 5 - 10 = -5 as uint64
        assert c.thread.regs[3] == ((-5) & T.MASK64)


class TestBitwise:
    def test_and(self):
        c = run_prog(A.program(
            A.li(1, 0xFF), A.li(2, 0x0F),
            A.and_(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 0x0F

    def test_or(self):
        c = run_prog(A.program(
            A.li(1, 0xF0), A.li(2, 0x0F),
            A.or_(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 0xFF

    def test_xor(self):
        c = run_prog(A.program(
            A.li(1, 0xFF), A.li(2, 0x0F),
            A.xor(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 0xF0

    def test_shl(self):
        c = run_prog(A.program(
            A.li(1, 1), A.li(2, 8),
            A.shl(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 256

    def test_shr(self):
        c = run_prog(A.program(
            A.li(1, 256), A.li(2, 4),
            A.shr(3, 1, 2), A.halt(),
        ))
        assert c.thread.regs[3] == 16

    def test_not(self):
        c = run_prog(A.program(
            A.li(1, 0), A.not_(2, 1), A.halt(),
        ))
        assert c.thread.regs[2] == T.MASK64


class TestLoadImm:
    def test_li_positive(self):
        c = run_prog(A.program(A.li(5, 1234), A.halt()))
        assert c.thread.regs[5] == 1234

    def test_li_negative(self):
        c = run_prog(A.program(A.li(5, -1 & 0xFFFF), A.halt()))
        assert c.thread.regs[5] == T.MASK64  # sign-extended -1

    def test_lui(self):
        c = run_prog(A.program(
            A.li(3, 0x1234), A.lui(3, 0xABCD), A.halt(),
        ))
        assert c.thread.regs[3] == 0xABCD_1234

    def test_li32(self):
        c = run_prog(A.program(
            A.encode_i(A.OP_LI32, 4, 0, 0),  # LI32 r4
            0xDEAD_BEEF,                       # immediate word
            A.halt(),
        ))
        # 0xDEADBEEF ≥ 0x80000000 → sign-extended
        assert c.thread.regs[4] == 0xFFFF_FFFF_DEAD_BEEF


class TestMemory:
    def test_ldr_str(self):
        c = run_prog(A.program(
            A.li(1, 42),
            A.li(2, 0x1000 // 8),     # base addr in words
            A.shl(2, 2, 0),           # no-op (shift by r0=0)
            A.halt(),
        ))
        # Manual: set r2 to the address, store r1 there, load it back
        prog = A.program(
            A.li(1, 42),
            A.li(2, 0x1000),          # byte address
            A.str_(2, 1, 0),          # mem[r2+0] = r1
            A.ldr(3, 2, 0),           # r3 = mem[r2+0]
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[3] == 42

    def test_ldr_offset(self):
        """LDR with non-zero word offset."""
        prog = A.program(
            A.li(1, 99),
            A.li(2, 100),
            A.li(3, 0x2000),
            A.str_(3, 1, 0),          # mem[0x2000+0*8] = 99
            A.str_(3, 2, 1),          # mem[0x2000+1*8] = 100
            A.ldr(4, 3, 1),           # r4 = mem[0x2000+1*8]
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[4] == 100


class TestPushPop:
    def test_push_pop(self):
        c = run_prog(A.program(
            A.li(1, 0x1234),
            A.push(1),
            A.li(1, 0),
            A.pop(2),
            A.halt(),
        ))
        assert c.thread.regs[2] == 0x1234


# ═════════════════════════════════════════════════════════════════════
#  2. BRANCHES
# ═════════════════════════════════════════════════════════════════════

class TestBranches:
    def test_br_unconditional(self):
        """BR skips one instruction."""
        prog = A.program(
            A.br(2),          # 0: jump to addr 0+2*4=8
            A.li(1, 999),     # 4: skipped
            A.li(1, 42),      # 8: target
            A.halt(),         # 12
        )
        c = run_prog(prog)
        assert c.thread.regs[1] == 42

    def test_br_t_taken(self):
        prog = A.program(
            A.li(1, 1),          # r1 = 1 (truthy)
            A.br_t(1, 2),        # 4: if truthy, jump to 4+2*4=12
            A.li(2, 999),        # 8: skipped
            A.li(2, 42),         # 12: target
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == 42

    def test_br_t_not_taken(self):
        """BR.T with NIL → not taken."""
        prog = A.program(
            A.li(1, T.NIL),      # r1 = NIL (5)
            A.br_t(1, 2),        # not taken
            A.li(2, 42),         # executed
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == 42

    def test_br_nil(self):
        prog = A.program(
            A.li(1, T.NIL),      # r1 = NIL
            A.br_nil(1, 2),      # 4: if nil, jump to 4+2*4=12
            A.li(2, 999),        # 8: skipped
            A.li(2, 42),         # 12
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == 42

    def test_br_fix_lt(self):
        """BR.FIX.LT taken when fixnum is negative."""
        prog = A.program(
            A.li(1, T.tag_fixnum(-5) & 0xFFFF),  # negative fixnum (low 16 bits)
            A.lui(1, (T.tag_fixnum(-5) >> 16) & 0xFFFF),
            A.br_fix_lt(1, 2),                     # taken
            A.li(2, 999),
            A.li(2, 42),
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == 42

    def test_backward_branch_loop(self):
        """Sum 1..5 using backward branch."""
        # r1 = counter (5), r2 = accumulator (0)
        prog = A.program(
            A.li(1, 5),           # 0: r1 = 5
            A.li(2, 0),           # 4: r2 = 0
            # loop:
            A.add(2, 2, 1),       # 8: r2 += r1
            A.li(3, 1),           # 12: r3 = 1
            A.sub(1, 1, 3),       # 16: r1 -= 1
            A.br_t(1, -3),        # 20: if r1 truthy, jump to 20+(-3)*4=8
            A.halt(),             # 24
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == 15  # 5+4+3+2+1


# ═════════════════════════════════════════════════════════════════════
#  3. TAGGED OPERATIONS
# ═════════════════════════════════════════════════════════════════════

class TestTaggedArith:
    def test_add_fix(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(10)),
            A.li(2, T.tag_fixnum(20)),
            A.add_fix(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[3]) == 30

    def test_sub_fix(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(50)),
            A.li(2, T.tag_fixnum(17)),
            A.sub_fix(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[3]) == 33

    def test_mul_fix(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(6)),
            A.li(2, T.tag_fixnum(7)),
            A.mul_fix(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[3]) == 42

    def test_add_fix_imm(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(100)),
            A.add_fix_imm(2, 1, 5),    # add 5 (mathematical)
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[2]) == 105

    def test_add_fix_imm_negative(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(10)),
            A.add_fix_imm(2, 1, -3 & 0xFFFF),   # subtract 3
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[2]) == 7

    def test_arith_fix_not_fixnum_trap(self):
        """ARITH_FIX on non-fixnum should trap."""
        prog = A.program(
            A.li(1, T.NIL),              # not a fixnum
            A.li(2, T.tag_fixnum(1)),
            A.add_fix(3, 1, 2),
            A.halt(),
        )
        c = make_core(prog)
        c.run(max_steps=100)
        assert c.thread.halted  # trapped (no handler → halt)


class TestTaggedCompare:
    def test_cmp_equal(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(42)),
            A.li(2, T.tag_fixnum(42)),
            A.cmp_tagged(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[3]) == 0

    def test_cmp_less(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(10)),
            A.li(2, T.tag_fixnum(20)),
            A.cmp_tagged(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[3]) == -1

    def test_cmp_greater(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(20)),
            A.li(2, T.tag_fixnum(10)),
            A.cmp_tagged(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[3]) == 1

    def test_eq_tagged_true(self):
        prog = A.program(
            A.li(1, T.NIL),
            A.li(2, T.NIL),
            A.eq_tagged(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[3] == T.T

    def test_eq_tagged_false(self):
        prog = A.program(
            A.li(1, T.NIL),
            A.li(2, T.T),
            A.eq_tagged(3, 1, 2),
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[3] == T.NIL


class TestTST:
    def test_tst_fixnum(self):
        prog = A.program(
            A.li(1, T.tag_fixnum(42)),
            A.tst(2, 1, 0),   # tag=0 → fixnum?
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == T.T

    def test_tst_fixnum_false(self):
        prog = A.program(
            A.li(1, T.NIL),   # special, not fixnum
            A.tst(2, 1, 0),
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == T.NIL

    def test_tst_nil(self):
        prog = A.program(
            A.li(1, T.NIL),
            A.tst(2, 1, 4),   # tag=4 → nil?
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == T.T

    def test_tst_special(self):
        prog = A.program(
            A.li(1, T.T),     # T is a special
            A.tst(2, 1, 3),   # tag=3 → special?
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == T.T


# ═════════════════════════════════════════════════════════════════════
#  4. ALLOCATION & FIELD ACCESS
# ═════════════════════════════════════════════════════════════════════

class TestAlloc:
    def test_alloc_basic(self):
        """ALLOC 3-word object, check ref is valid."""
        prog = A.program(
            A.alloc(5, 3),    # r5 = alloc(3 words)
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        c.run(max_steps=100)
        ref = c.thread.regs[5]
        assert T.is_ref(ref)
        # Header should be at ref-8
        header_addr = T.untag_ref(ref) - 8
        hdr = c._r64(header_addr)
        assert T.is_header(hdr)
        assert T.header_size(hdr) == 3

    def test_alloc_cons(self):
        """ALLOC.CONS, set car & cdr, read back."""
        prog = A.program(
            A.alloc_cons(5),               # r5 = cons cell
            A.li(1, T.tag_fixnum(10)),     # car value
            A.li(2, T.tag_fixnum(20)),     # cdr value
            A.st_car(5, 1),                # (set-car! r5 r1)
            A.st_cdr(5, 2),                # (set-cdr! r5 r2)
            A.ld_car(3, 5),                # r3 = (car r5)
            A.ld_cdr(4, 5),                # r4 = (cdr r5)
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        c.run(max_steps=100)
        assert T.is_cons(c.thread.regs[5])
        assert T.untag_fixnum(c.thread.regs[3]) == 10
        assert T.untag_fixnum(c.thread.regs[4]) == 20


class TestFieldAccess:
    def test_ld_st_field(self):
        """Allocate object, write field, read it back."""
        prog = A.program(
            A.alloc(5, 2),                 # r5 = alloc(2 words)
            A.li(1, T.tag_fixnum(42)),
            A.st_field(5, 1, 0),           # field[0] = r1
            A.ld_field(2, 5, 0),           # r2 = field[0]
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        c.run(max_steps=100)
        assert T.untag_fixnum(c.thread.regs[2]) == 42

    def test_ld_st_multiple_fields(self):
        prog = A.program(
            A.alloc(5, 3),
            A.li(1, T.tag_fixnum(10)),
            A.li(2, T.tag_fixnum(20)),
            A.li(3, T.tag_fixnum(30)),
            A.st_field(5, 1, 0),
            A.st_field(5, 2, 1),
            A.st_field(5, 3, 2),
            A.ld_field(6, 5, 0),
            A.ld_field(7, 5, 1),
            A.ld_field(8, 5, 2),
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        c.run(max_steps=200)
        assert T.untag_fixnum(c.thread.regs[6]) == 10
        assert T.untag_fixnum(c.thread.regs[7]) == 20
        assert T.untag_fixnum(c.thread.regs[8]) == 30

    def test_build_list(self):
        """Build the list (1 2 3) using cons cells."""
        prog = A.program(
            # (cons 3 nil)
            A.alloc_cons(10),                      # r10
            A.li(1, T.tag_fixnum(3)),
            A.st_car(10, 1),
            A.li(2, T.NIL),
            A.st_cdr(10, 2),
            # (cons 2 r10)
            A.alloc_cons(11),                      # r11
            A.li(1, T.tag_fixnum(2)),
            A.st_car(11, 1),
            A.st_cdr(11, 10),
            # (cons 1 r11)
            A.alloc_cons(12),                      # r12
            A.li(1, T.tag_fixnum(1)),
            A.st_car(12, 1),
            A.st_cdr(12, 11),
            # Read car of head
            A.ld_car(20, 12),                      # 1
            A.ld_cdr(21, 12),                      # (2 3)
            A.ld_car(22, 21),                      # 2
            A.ld_cdr(23, 21),                      # (3)
            A.ld_car(24, 23),                      # 3
            A.ld_cdr(25, 23),                      # nil
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        c.run(max_steps=500)
        assert T.untag_fixnum(c.thread.regs[20]) == 1
        assert T.untag_fixnum(c.thread.regs[22]) == 2
        assert T.untag_fixnum(c.thread.regs[24]) == 3
        assert c.thread.regs[25] == T.NIL


# ═════════════════════════════════════════════════════════════════════
#  5. CALL / RETURN
# ═════════════════════════════════════════════════════════════════════

class TestCallReturn:
    def test_call_direct_ret(self):
        """Call a subroutine, return a value."""
        # main: li r1, <func_addr>; call r1; halt
        # func: li r2, 42; ret
        func_addr = 5 * 4  # address of the function (5th instruction)
        prog = A.program(
            A.li(1, func_addr),     # 0: r1 = func_addr
            A.call_direct(1),       # 4: call r1
            A.halt(),               # 8: return here after func
            A.nop(),                # 12: padding
            A.nop(),                # 16: padding
            # func at offset 20:
            A.li(2, 42),            # 20: r2 = 42
            A.ret(),                # 24
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == 42
        assert c.thread.pc == 12  # halted at instruction after call

    def test_nested_calls(self):
        """Two levels of calls."""
        # main calls foo(28), foo calls bar(44)
        # bar sets r3=99 and returns, foo sets r2=42 and returns
        prog = A.program(
            A.li(1, 28),           # 0: r1 = foo_addr
            A.call_direct(1),      # 4: call foo
            A.halt(),              # 8
            A.nop(),               # 12
            A.nop(),               # 16
            A.nop(),               # 20
            A.nop(),               # 24
            # foo at 28:
            A.li(4, 44),           # 28: r4 = bar_addr
            A.call_direct(4),      # 32: call bar
            A.li(2, 42),           # 36: r2 = 42
            A.ret(),               # 40
            # bar at 44:
            A.li(3, 99),           # 44: r3 = 99
            A.ret(),               # 48
        )
        c = run_prog(prog)
        assert c.thread.regs[2] == 42
        assert c.thread.regs[3] == 99


# ═════════════════════════════════════════════════════════════════════
#  6. SYSTEM & TRAP
# ═════════════════════════════════════════════════════════════════════

class TestSystem:
    def test_nop(self):
        prog = A.program(A.nop(), A.nop(), A.halt())
        c = run_prog(prog)
        assert c.thread.halted
        assert c.thread.cycle_count == 3

    def test_sys_info_tile_id(self):
        prog = A.program(A.sys_info(1, 0), A.halt())
        c = run_prog(prog)
        assert c.thread.regs[1] == 0  # default tile_id

    def test_sys_info_cycle_count(self):
        prog = A.program(
            A.nop(), A.nop(), A.nop(),
            A.sys_info(1, 2),       # r1 = cycle_count
            A.halt(),
        )
        c = run_prog(prog)
        assert c.thread.regs[1] == 3  # 3 NOPs before sys_info

    def test_trap_no_handler(self):
        """TRAP without handler → halt."""
        prog = A.program(A.trap(0x80), A.halt())
        c = make_core(prog)
        c.run(max_steps=100)
        assert c.thread.halted
        assert c.thread.trap_cause == 0x80


# ═════════════════════════════════════════════════════════════════════
#  7. GC
# ═════════════════════════════════════════════════════════════════════

class TestGC:
    def test_nursery_allocation_bump(self):
        """Verify nursery bump pointer advances."""
        prog = A.program(
            A.alloc(1, 2),       # 3 words = 24 bytes
            A.alloc(2, 3),       # 4 words = 32 bytes
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        initial_np = c.thread.np
        c.run(max_steps=100)
        # np should advance by 24 + 32 = 56
        assert c.thread.np == initial_np + 56

    def test_gc_collect_resets_nursery(self):
        """Manual GC collect resets nursery pointer."""
        prog = A.program(
            A.alloc(1, 2),
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        c.run(max_steps=100)
        assert c.thread.np > c.nursery_base
        c.gc_collect()
        assert c.thread.np == c.nursery_base


# ═════════════════════════════════════════════════════════════════════
#  8. WRITE BARRIER
# ═════════════════════════════════════════════════════════════════════

class TestWriteBarrier:
    def test_st_wb_marks_card(self):
        """ST.WB marks card dirty when storing nursery ref in old-gen."""
        c = make_core(A.program(A.halt()))
        c.init_nursery()

        # Place a fake object in old-gen
        old_addr = c.oldgen_base
        c._w64(old_addr, T.make_header(T.HDR_INSTANCE, 2))
        old_ref = T.tag_ref(old_addr + 8)

        # Nursery ref
        nursery_ref = T.tag_ref(c.nursery_base + 8)

        # Simulate write barrier
        c._write_barrier(old_addr + 8, nursery_ref)
        card = (old_addr + 8 - c.oldgen_base) // 256
        assert c.card_table[card] == 1


# ═════════════════════════════════════════════════════════════════════
#  9. INTEGRATION
# ═════════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_factorial(self):
        """Compute 5! = 120 using a loop with tagged fixnums."""
        # r1 = n (5), r2 = acc (1)
        # loop: if n == 0, done; acc *= n; n -= 1; goto loop
        prog = A.program(
            A.li(1, T.tag_fixnum(5)),      # 0: n = 5
            A.li(2, T.tag_fixnum(1)),      # 4: acc = 1
            A.li(5, T.tag_fixnum(0)),      # 8: zero const
            # loop at 12:
            A.eq_tagged(3, 1, 5),           # 12: r3 = (n == 0)?
            A.br_t(3, 4),                   # 16: if true, jump to 16+4*4=32
            A.mul_fix(2, 2, 1),             # 20: acc *= n
            A.add_fix_imm(1, 1, -1 & 0xFFFF),  # 24: n -= 1
            A.br(-4),                       # 28: jump to 28+(-4)*4=12
            # done at 32:
            A.halt(),                       # 32
        )
        c = run_prog(prog)
        assert T.untag_fixnum(c.thread.regs[2]) == 120

    def test_sum_of_list(self):
        """Build list (10 20 30), sum it → 60."""
        prog = A.program(
            # Build (30)
            A.alloc_cons(10),                        # 0
            A.li(1, T.tag_fixnum(30)),               # 4
            A.st_car(10, 1),                         # 8
            A.li(2, T.NIL),                          # 12
            A.st_cdr(10, 2),                         # 16
            # Build (20 30)
            A.alloc_cons(11),                        # 20
            A.li(1, T.tag_fixnum(20)),               # 24
            A.st_car(11, 1),                         # 28
            A.st_cdr(11, 10),                        # 32
            # Build (10 20 30)
            A.alloc_cons(12),                        # 36
            A.li(1, T.tag_fixnum(10)),               # 40
            A.st_car(12, 1),                         # 44
            A.st_cdr(12, 11),                        # 48
            # Sum loop: r12=list, r20=acc
            A.li(20, T.tag_fixnum(0)),               # 52: acc = 0
            # loop at 56:
            A.tst(21, 12, 4),                        # 56: r21 = (nil? r12)
            A.br_t(21, 5),                           # 60: if nil, jump to 60+5*4=80
            A.ld_car(22, 12),                        # 64: r22 = car
            A.add_fix(20, 20, 22),                   # 68: acc += car
            A.ld_cdr(12, 12),                        # 72: list = cdr
            A.br(-5),                                # 76: jump to 76+(-5)*4=56
            # done at 80:
            A.halt(),                                # 80
        )
        c = make_core(prog)
        c.init_nursery()
        c.run(max_steps=500)
        assert T.untag_fixnum(c.thread.regs[20]) == 60


# ═════════════════════════════════════════════════════════════════════
#  10. C ACCELERATOR
# ═════════════════════════════════════════════════════════════════════

class TestLM1Accel:
    @pytest.fixture(autouse=True)
    def setup_accel(self):
        """Try to load the C accelerator; skip if not built."""
        mem = bytearray(4096)
        c = LM1Core(mem)
        if not c.load_accel():
            pytest.skip("LM-1 C accelerator not built (run `make accel`)")
        self._accel_available = True

    def test_accel_add(self):
        c = make_core(A.program(
            A.li(1, 10), A.li(2, 20),
            A.add(3, 1, 2), A.halt(),
        ))
        c.load_accel()
        c.run_accel(10_000)
        assert c.thread.regs[3] == 30

    def test_accel_loop_sum(self):
        """Sum 1..4 using C accel path (avoids raw 5==NIL collision)."""
        prog = A.program(
            A.li(1, 4),           # 0: counter
            A.li(2, 0),           # 4: acc
            # loop at 8:
            A.add(2, 2, 1),       # 8
            A.li(3, 1),           # 12
            A.sub(1, 1, 3),       # 16
            A.br_t(1, -3),        # 20: if truthy → 20+(-3)*4=8
            A.halt(),             # 24
        )
        c = make_core(prog)
        c.load_accel()
        c.run_accel(10_000)
        assert c.thread.regs[2] == 10  # 4+3+2+1

    def test_accel_fallback_to_python(self):
        """ALLOC falls back to Python from C."""
        prog = A.program(
            A.li(1, T.tag_fixnum(42)),
            A.alloc_cons(5),
            A.st_car(5, 1),
            A.ld_car(2, 5),
            A.halt(),
        )
        c = make_core(prog)
        c.init_nursery()
        c.load_accel()
        c.run_accel(10_000)
        assert T.untag_fixnum(c.thread.regs[2]) == 42

    def test_accel_push_pop(self):
        c = make_core(A.program(
            A.li(1, 0x1234),
            A.push(1),
            A.li(1, 0),
            A.pop(2),
            A.halt(),
        ))
        c.load_accel()
        c.run_accel(10_000)
        assert c.thread.regs[2] == 0x1234

    def test_accel_bitwise(self):
        c = make_core(A.program(
            A.li(1, 0xFF), A.li(2, 0x0F),
            A.and_(3, 1, 2), A.or_(4, 1, 2),
            A.xor(5, 1, 2), A.halt(),
        ))
        c.load_accel()
        c.run_accel(10_000)
        assert c.thread.regs[3] == 0x0F
        assert c.thread.regs[4] == 0xFF
        assert c.thread.regs[5] == 0xF0

    def test_accel_ldr_str(self):
        c = make_core(A.program(
            A.li(1, 42),
            A.li(2, 0x1000),
            A.str_(2, 1, 0),
            A.ldr(3, 2, 0),
            A.halt(),
        ))
        c.load_accel()
        c.run_accel(10_000)
        assert c.thread.regs[3] == 42
