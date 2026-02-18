"""Tests for the MP64 core emulator — all instruction families."""

import pytest
from chimera.mp64.core import MP64Core, MASK64
from chimera.mp64 import asm

# -----------------------------------------------------------------------
#  Helpers
# -----------------------------------------------------------------------

def make_core(prog: bytes | bytearray, mem_size: int = 0x10000) -> MP64Core:
    """Create an MP64Core with *prog* loaded at address 0."""
    mem = bytearray(mem_size)
    mem[:len(prog)] = prog
    c = MP64Core(mem)
    # R0 = PC starts at 0, R2 = SP at top of memory
    c.regs[2] = mem_size - 8
    return c


def run(prog: bytes | bytearray, max_steps: int = 200, **kw) -> MP64Core:
    c = make_core(prog, **kw)
    c.run(max_steps)
    return c


# =======================================================================
#  Family 0 — SYS
# =======================================================================

class TestSys:
    def test_nop(self):
        c = run(asm.program(asm.nop(), asm.halt()))
        assert c.halted

    def test_halt(self):
        c = run(asm.program(asm.halt()))
        assert c.halted
        assert c.pc == 1

    def test_seq_req(self):
        c = run(asm.program(asm.seq(), asm.halt()))
        assert c.q == 1
        c = run(asm.program(asm.seq(), asm.req(), asm.halt()))
        assert c.q == 0

    def test_ei_di(self):
        c = run(asm.program(asm.ei(), asm.halt()))
        assert c.flag_i == 1
        c = run(asm.program(asm.ei(), asm.di_(), asm.halt()))
        assert c.flag_i == 0

    def test_call_l_ret_l(self):
        # Put a function at address 0x100 that sets R3=42 and returns
        prog = asm.program(
            # Main: R1 = 0x100 (function addr)
            asm.ldi(1, 0),        # R1 = 0
            asm.addi(1, 0x10),    # R1 = 16 ... we need a computed address
        )
        # Simpler approach: put function right after main code
        main = asm.program(
            asm.ldi(3, 0),        # R3 = 0
            asm.ldi(1, 20),       # R1 = 20 (address of function, ~offset)
            asm.call_l(1),        # call R1
            asm.halt(),           # return here
        )
        func = asm.program(
            asm.ldi(3, 42),       # R3 = 42
            asm.ret_l(),          # return
        )
        # Compute function offset: main is loaded at 0
        # main instructions: ldi(3)=3 + ldi(1)=3 + call_l=2 + halt=1 = 9 bytes
        # So function is at address 9
        main = asm.program(
            asm.ldi(3, 0),        # 3 bytes
            asm.ldi(1, 9),        # 3 bytes → R1 = 9
            asm.call_l(1),        # 2 bytes
            asm.halt(),           # 1 byte  → total main = 9
        )
        prog = main + func
        c = run(prog)
        assert c.regs[3] == 42
        assert c.halted

    def test_trap(self):
        # Set up IVT with handler at 0x200
        handler_addr = 0x200
        prog = asm.program(
            # Set IVT base to 0x100
            asm.ldi(4, 0),
            asm.ldi64(4, 0x100),  # R4 = 0x100
            asm.csrw(4, 0x04),    # IVT_BASE = R4
            asm.trap(),           # SW_TRAP (vector 6)
            asm.halt(),           # shouldn't reach here if trap works
        )
        c = make_core(prog)
        # Write IVT entry for vector 6 at 0x100 + 6*8 = 0x130
        import struct
        struct.pack_into("<Q", c.mem, 0x100 + 6 * 8, handler_addr)
        # Write handler: set R5=99 then HALT
        handler = asm.program(asm.ldi(5, 99), asm.halt())
        c.mem[handler_addr:handler_addr + len(handler)] = handler
        c.run(50)
        assert c.regs[5] == 99
        assert c.halted

    def test_mark_sav(self):
        c = run(asm.program(
            asm.mark(),  # push T, T = (X<<4)|P
            asm.sav(),   # M(R(X)) = T
            asm.halt(),
        ))
        # Default xsel=0, psel=0 → T = (0<<4)|0 = 0
        # mark pushes old T, then sets T = 0
        assert c.t == 0

    def test_idl(self):
        c = run(asm.program(asm.idl()))
        assert c.idle


# =======================================================================
#  Family 1/2 — INC / DEC
# =======================================================================

class TestIncDec:
    def test_inc(self):
        c = run(asm.program(asm.ldi(5, 10), asm.inc(5), asm.halt()))
        assert c.regs[5] == 11

    def test_dec(self):
        c = run(asm.program(asm.ldi(5, 10), asm.dec(5), asm.halt()))
        assert c.regs[5] == 9

    def test_inc_wrap(self):
        prog = asm.program(asm.ldi64(5, MASK64), asm.inc(5), asm.halt())
        c = run(prog)
        assert c.regs[5] == 0

    def test_dec_wrap(self):
        prog = asm.program(asm.ldi(5, 0), asm.dec(5), asm.halt())
        c = run(prog)
        assert c.regs[5] == MASK64


# =======================================================================
#  Family 3/4 — BR / LBR
# =======================================================================

class TestBranch:
    def test_br_always(self):
        # Branch forward 2 bytes (skip next halt, land on nop+halt)
        prog = asm.program(
            asm.br(asm.AL, 1),   # branch +1 from end of insn → skip 1 byte
            asm.halt(),          # skipped
            asm.ldi(3, 77),      # landed here
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[3] == 77

    def test_br_eq_taken(self):
        prog = asm.program(
            asm.ldi(3, 0),
            asm.ldi(4, 0),
            asm.cmp(3, 4),       # R3 == R4 → Z=1
            asm.br(asm.EQ, 1),   # taken → skip halt
            asm.halt(),          # skipped
            asm.ldi(5, 88),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 88

    def test_br_eq_not_taken(self):
        prog = asm.program(
            asm.ldi(3, 1),
            asm.ldi(4, 2),
            asm.cmp(3, 4),       # R3 != R4 → Z=0
            asm.br(asm.EQ, 1),   # not taken
            asm.ldi(5, 99),      # reached
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 99

    def test_lbr_always(self):
        prog = asm.program(
            asm.lbr(asm.AL, 1),  # branch +1 from end of insn
            asm.halt(),          # skipped
            asm.ldi(3, 55),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[3] == 55

    def test_br_backward(self):
        # Loop R3 from 0 to 3 using INC and branch-back
        #   addr 0: LDI R3, 0       (3 bytes)
        #   addr 3: INC R3           (1 byte)
        #   addr 4: CMPI R3, 3      (3 bytes)
        #   addr 7: BR NE, -6       (2 bytes) → jumps to addr 3
        #   addr 9: HALT
        prog = asm.program(
            asm.ldi(3, 0),       # 3 bytes
            asm.inc(3),          # 1 byte  (addr 3)
            asm.cmpi(3, 3),      # 3 bytes (addr 4)
            asm.br(asm.NE, (-6) & 0xFF),  # 2 bytes → back to addr 3
            asm.halt(),
        )
        c = run(prog, max_steps=100)
        assert c.regs[3] == 3


# =======================================================================
#  Family 5 — MEM (scalar load/store)
# =======================================================================

class TestMem:
    def test_str_ldn(self):
        prog = asm.program(
            asm.ldi(3, 42),      # R3 = 42
            asm.ldi(4, 0),
            asm.ldi64(4, 0x500),  # R4 = 0x500 (store address)
            asm.str_(4, 3),      # M[R4] = R3
            asm.ldi(5, 0),       # clear R5
            asm.ldn(5, 4),       # R5 = M[R4]
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 42

    def test_ld_st_byte(self):
        prog = asm.program(
            asm.ldi64(4, 0x500),
            asm.ldi(3, 0xAB),
            asm.st_b(4, 3),
            asm.ldi(5, 0),
            asm.ld_b(5, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 0xAB

    def test_ld_st_half(self):
        prog = asm.program(
            asm.ldi64(4, 0x500),
            asm.ldi64(3, 0x1234),
            asm.st_h(4, 3),
            asm.ldi(5, 0),
            asm.ld_h(5, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 0x1234

    def test_ld_st_word(self):
        prog = asm.program(
            asm.ldi64(4, 0x500),
            asm.ldi64(3, 0xDEADBEEF),
            asm.st_w(4, 3),
            asm.ldi(5, 0),
            asm.ld_w(5, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 0xDEADBEEF

    def test_ld_signed_byte(self):
        prog = asm.program(
            asm.ldi64(4, 0x500),
            asm.ldi(3, 0x80),    # -128 as signed byte
            asm.st_b(4, 3),
            asm.ldi(5, 0),
            asm.ld_sb(5, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == MASK64 - 127  # sign-extended -128

    def test_lda(self):
        # LDA loads and auto-increments Rs by 8
        prog = asm.program(
            asm.ldi64(4, 0x500),
            asm.ldi64(3, 0x77),
            asm.str_(4, 3),      # M[0x500] = 0x77
            asm.ldi64(6, 0x500),
            asm.lda(5, 6),       # R5 = M[R6], R6 += 8
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 0x77
        assert c.regs[6] == 0x508

    def test_stxd(self):
        prog = asm.program(
            asm.ldi64(4, 0x510),
            asm.ldi(3, 99),
            asm.stxd(4, 3),      # M[R4] = R3, R4 -= 8
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[4] == 0x508

    def test_ld_d_offset(self):
        prog = asm.program(
            asm.ldi64(4, 0x500),
            asm.ldi64(3, 0xBEEF),
            asm.str_(4, 3),      # M[0x500] = 0xBEEF
            asm.ldi64(6, 0x4F8), # 0x500 - 8 = 0x4F8
            asm.ld_d(5, 6, 1),   # R5 = M[R6 + 1*8] = M[0x500]
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 0xBEEF


# =======================================================================
#  Family 6 — IMM
# =======================================================================

class TestImm:
    def test_ldi(self):
        c = run(asm.program(asm.ldi(3, 42), asm.halt()))
        assert c.regs[3] == 42

    def test_ldi64(self):
        c = run(asm.program(asm.ldi64(3, 0xDEAD_BEEF_CAFE_BABE), asm.halt()))
        assert c.regs[3] == 0xDEAD_BEEF_CAFE_BABE

    def test_addi(self):
        c = run(asm.program(asm.ldi(3, 10), asm.addi(3, 5), asm.halt()))
        assert c.regs[3] == 15
        assert c.flag_z == 0

    def test_addi_negative(self):
        c = run(asm.program(asm.ldi(3, 10), asm.addi(3, (-3) & 0xFF), asm.halt()))
        assert c.regs[3] == 7

    def test_subi(self):
        c = run(asm.program(asm.ldi(3, 10), asm.subi(3, 3), asm.halt()))
        assert c.regs[3] == 7

    def test_andi(self):
        c = run(asm.program(asm.ldi(3, 0xFF), asm.andi(3, 0x0F), asm.halt()))
        assert c.regs[3] == 0x0F

    def test_ori(self):
        c = run(asm.program(asm.ldi(3, 0xF0), asm.ori(3, 0x0F), asm.halt()))
        assert c.regs[3] == 0xFF

    def test_xori(self):
        c = run(asm.program(asm.ldi(3, 0xFF), asm.xori(3, 0x0F), asm.halt()))
        assert c.regs[3] == 0xF0

    def test_cmpi(self):
        c = run(asm.program(asm.ldi(3, 5), asm.cmpi(3, 5), asm.halt()))
        assert c.flag_z == 1
        assert c.flag_g == 0  # equal, not greater

    def test_cmpi_gt(self):
        c = run(asm.program(asm.ldi(3, 10), asm.cmpi(3, 5), asm.halt()))
        assert c.flag_z == 0
        assert c.flag_g == 1

    def test_lsli(self):
        c = run(asm.program(asm.ldi(3, 1), asm.lsli(3, 4), asm.halt()))
        assert c.regs[3] == 16

    def test_lsri(self):
        c = run(asm.program(asm.ldi(3, 16), asm.lsri(3, 4), asm.halt()))
        assert c.regs[3] == 1

    def test_asri(self):
        c = run(asm.program(asm.ldi64(3, MASK64), asm.asri(3, 4), asm.halt()))
        assert c.regs[3] == MASK64  # sign-extended

    def test_roli(self):
        c = run(asm.program(asm.ldi(3, 1), asm.roli(3, 4), asm.halt()))
        assert c.regs[3] == 16

    def test_lhi(self):
        c = run(asm.program(asm.ldi(3, 0), asm.lhi(3, 0xABCD), asm.halt()))
        assert c.regs[3] == 0xABCD_0000_0000_0000

    def test_glo_plo(self):
        c1 = run(asm.program(asm.ldi(3, 0xAB), asm.glo(3), asm.halt()))
        assert c1.d == 0xAB
        c2 = make_core(asm.program(asm.ldi(3, 0x00), asm.halt()))
        c2.d = 0x42
        prog = asm.program(asm.ldi(3, 0), asm.plo(3), asm.halt())
        c2 = run(prog)
        # plo puts D into R[n][7:0] — but D starts at 0 for fresh core
        # Let's do a proper round-trip test
        prog = asm.program(
            asm.ldi(3, 0x99),   # R3 = 0x99
            asm.glo(3),         # D = R3[7:0] = 0x99
            asm.ldi(4, 0),      # R4 = 0
            asm.plo(4),         # R4[7:0] = D = 0x99
            asm.halt(),
        )
        c = run(prog)
        assert c.d == 0x99
        assert c.regs[4] == 0x99

    def test_ghi_phi(self):
        prog = asm.program(
            asm.ldi64(3, 0xAB00),
            asm.ghi(3),         # D = R3[15:8] = 0xAB
            asm.ldi(4, 0),
            asm.phi(4),         # R4[15:8] = D = 0xAB
            asm.halt(),
        )
        c = run(prog)
        assert c.d == 0xAB
        assert c.regs[4] == 0xAB00


# =======================================================================
#  Family 7 — ALU
# =======================================================================

class TestALU:
    def test_add(self):
        prog = asm.program(asm.ldi(3, 10), asm.ldi(4, 20), asm.add(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 30

    def test_add_carry(self):
        # MAX + 1 → carry
        prog = asm.program(
            asm.ldi64(3, MASK64),
            asm.ldi(4, 1),
            asm.add(3, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[3] == 0
        assert c.flag_c == 1
        assert c.flag_z == 1

    def test_sub(self):
        prog = asm.program(asm.ldi(3, 20), asm.ldi(4, 10), asm.sub(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 10

    def test_sub_borrow(self):
        prog = asm.program(asm.ldi(3, 5), asm.ldi(4, 10), asm.sub(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == (5 - 10) & MASK64
        assert c.flag_c == 0  # borrow occurred

    def test_and(self):
        prog = asm.program(asm.ldi(3, 0xFF), asm.ldi(4, 0x0F), asm.and_(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 0x0F

    def test_or(self):
        prog = asm.program(asm.ldi(3, 0xF0), asm.ldi(4, 0x0F), asm.or_(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 0xFF

    def test_xor(self):
        prog = asm.program(asm.ldi(3, 0xFF), asm.ldi(4, 0x0F), asm.xor(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 0xF0

    def test_cmp_eq(self):
        prog = asm.program(asm.ldi(3, 42), asm.ldi(4, 42), asm.cmp(3, 4), asm.halt())
        c = run(prog)
        assert c.flag_z == 1
        assert c.flag_g == 0

    def test_cmp_gt(self):
        prog = asm.program(asm.ldi(3, 50), asm.ldi(4, 10), asm.cmp(3, 4), asm.halt())
        c = run(prog)
        assert c.flag_z == 0
        assert c.flag_g == 1

    def test_mov(self):
        prog = asm.program(asm.ldi(3, 42), asm.mov(4, 3), asm.halt())
        c = run(prog)
        assert c.regs[4] == 42

    def test_not(self):
        prog = asm.program(asm.ldi(3, 0), asm.not_(4, 3), asm.halt())
        c = run(prog)
        assert c.regs[4] == MASK64

    def test_neg(self):
        prog = asm.program(asm.ldi(3, 5), asm.neg(4, 3), asm.halt())
        c = run(prog)
        assert c.regs[4] == (-5) & MASK64

    def test_shl(self):
        prog = asm.program(asm.ldi(3, 1), asm.ldi(4, 8), asm.shl(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 256

    def test_shr(self):
        prog = asm.program(asm.ldi64(3, 256), asm.ldi(4, 8), asm.shr(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 1

    def test_sar(self):
        prog = asm.program(
            asm.ldi64(3, (-16) & MASK64),
            asm.ldi(4, 2),
            asm.sar(3, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[3] == (-4) & MASK64

    def test_rol(self):
        prog = asm.program(asm.ldi(3, 1), asm.ldi(4, 63), asm.rol(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == (1 << 63)

    def test_ror(self):
        prog = asm.program(
            asm.ldi64(3, 1 << 63),
            asm.ldi(4, 63),
            asm.ror(3, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[3] == 1

    def test_adc(self):
        # Set carry, then ADC
        prog = asm.program(
            asm.ldi64(3, MASK64), asm.ldi(4, 1), asm.add(3, 4),  # sets carry
            asm.ldi(5, 10), asm.ldi(6, 20), asm.adc(5, 6),       # 10+20+1
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 31

    def test_sbb(self):
        prog = asm.program(
            asm.ldi(3, 5), asm.ldi(4, 10), asm.sub(3, 4),  # sets borrow (C=0)
            asm.ldi(5, 20), asm.ldi(6, 10), asm.sbb(5, 6),  # 20 - 10 - 1 = 9
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[5] == 9


# =======================================================================
#  Family 8 — MEMALU
# =======================================================================

class TestMemALU:
    def test_ldx_d(self):
        prog = asm.program(asm.ldi64(3, 0x500), asm.halt())
        c = make_core(prog)
        c.mem[0x500] = 0xAB
        c.xsel = 3
        # Need to set xsel before running. Re-build program with SEX:
        prog = asm.program(
            asm.ldi64(3, 0x500),
            asm.sex(3),
            asm.ldx_d(),
            asm.halt(),
        )
        c = make_core(prog)
        c.mem[0x500] = 0xAB
        c.run(50)
        assert c.d == 0xAB

    def test_add_x(self):
        prog = asm.program(
            asm.ldi64(3, 0x500),
            asm.sex(3),
            asm.ldx_d(),         # D = M(R3) = 10
            asm.inc(3),          # R3++ (point to next byte)
            asm.add_x(),         # D += M(R3) = D + 20
            asm.halt(),
        )
        c = make_core(prog)
        c.mem[0x500] = 10
        c.mem[0x501] = 20
        c.run(50)
        assert c.d == 30

    def test_shl_shr_d(self):
        prog = asm.program(
            asm.ldi64(3, 0x500),
            asm.sex(3),
            asm.ldx_d(),         # D = 0b01
            asm.shl_d(),         # D <<= 1 → 0b10
            asm.halt(),
        )
        c = make_core(prog)
        c.mem[0x500] = 0x01
        c.run(50)
        assert c.d == 0x02

    def test_irx(self):
        prog = asm.program(
            asm.ldi64(3, 0x500),
            asm.sex(3),
            asm.irx(),           # R(X)++
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[3] == 0x501


# =======================================================================
#  Family A/B — SEP / SEX
# =======================================================================

class TestSepSex:
    def test_sex(self):
        c = run(asm.program(asm.sex(5), asm.halt()))
        assert c.xsel == 5

    def test_sep(self):
        # SEP 3 switches PC to R3.  Set R3 to point to a HALT.
        # Layout: ldi(3,4)=3 bytes @0, sep(3)=1 byte @3, halt=1 byte @4
        main = asm.program(
            asm.ldi(3, 4),   # R3 = 4 (address of the HALT after SEP)
            asm.sep(3),      # psel = 3, old R0 saves return addr
            asm.halt(),      # at addr 4: reached via R3
        )
        c = run(main)
        assert c.halted
        assert c.psel == 3


# =======================================================================
#  Family C — MULDIV
# =======================================================================

class TestMulDiv:
    def test_mul(self):
        prog = asm.program(asm.ldi(3, 7), asm.ldi(4, 6), asm.mul(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 42

    def test_umul(self):
        prog = asm.program(asm.ldi(3, 100), asm.ldi(4, 200), asm.umul(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 20000

    def test_div(self):
        prog = asm.program(asm.ldi(3, 42), asm.ldi(4, 6), asm.div(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 7

    def test_udiv(self):
        prog = asm.program(asm.ldi(3, 100), asm.ldi(4, 10), asm.udiv(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 10

    def test_mod(self):
        prog = asm.program(asm.ldi(3, 10), asm.ldi(4, 3), asm.mod(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 1

    def test_umod(self):
        prog = asm.program(asm.ldi(3, 10), asm.ldi(4, 3), asm.umod(3, 4), asm.halt())
        c = run(prog)
        assert c.regs[3] == 1

    def test_div_by_zero_traps(self):
        prog = asm.program(
            asm.ldi64(4, 0x100),
            asm.csrw(4, 0x04),   # IVT_BASE = 0x100
            asm.ldi(3, 10),
            asm.ldi(4, 0),
            asm.div(3, 4),       # divide by zero → trap
            asm.halt(),          # shouldn't reach
        )
        c = make_core(prog)
        # Write IVT entry for DIV_ZERO (vector 4) → handler at 0x200
        import struct
        struct.pack_into("<Q", c.mem, 0x100 + 4 * 8, 0x200)
        handler = asm.program(asm.ldi(5, 77), asm.halt())
        c.mem[0x200:0x200 + len(handler)] = handler
        c.run(50)
        assert c.regs[5] == 77

    def test_mulh(self):
        prog = asm.program(
            asm.ldi64(3, 0xFFFF_FFFF_FFFF_FFFF),
            asm.ldi(4, 2),
            asm.umulh(3, 4),
            asm.halt(),
        )
        c = run(prog)
        assert c.regs[3] == 1  # (2^64 - 1) * 2 >> 64 == 1


# =======================================================================
#  Family D — CSR
# =======================================================================

class TestCSR:
    def test_csrr_coreid(self):
        prog = asm.program(asm.csrr(3, 0x20), asm.halt())
        c = run(prog)
        assert c.regs[3] == 0  # default core_id

    def test_csrr_ncores(self):
        prog = asm.program(asm.csrr(3, 0x21), asm.halt())
        c = make_core(prog)
        c.n_cores = 4
        c.run(10)
        assert c.regs[3] == 4

    def test_csrw_flags(self):
        prog = asm.program(
            asm.ldi(3, 0xFF),    # all flags
            asm.csrw(3, 0x00),   # write FLAGS
            asm.halt(),
        )
        c = run(prog)
        assert c.flag_z == 1
        assert c.flag_c == 1
        assert c.flag_i == 1
        assert c.flag_s == 1

    def test_csrr_cpuid(self):
        prog = asm.program(asm.csrr(3, 0x31), asm.halt())
        c = run(prog)
        assert c.regs[3] == 0x4D503634  # "MP64"


# =======================================================================
#  EXT prefix
# =======================================================================

class TestEXT:
    def test_ext_imm64(self):
        c = run(asm.program(asm.ldi64(3, 0x1234_5678_9ABC_DEF0), asm.halt()))
        assert c.regs[3] == 0x1234_5678_9ABC_DEF0

    def test_ext_imm64_zero(self):
        c = run(asm.program(asm.ldi64(3, 0), asm.halt()))
        assert c.regs[3] == 0


# =======================================================================
#  Integration: small programs
# =======================================================================

class TestIntegration:
    def test_sum_1_to_10(self):
        """Sum 1+2+...+10 = 55."""
        # R3 = sum, R4 = counter (1..10)
        prog = asm.program(
            asm.ldi(3, 0),        # sum = 0            (3 bytes, addr 0)
            asm.ldi(4, 1),        # i = 1              (3 bytes, addr 3)
            # loop:                                     (addr 6)
            asm.add(3, 4),        # sum += i            (2 bytes, addr 6)
            asm.inc(4),           # i++                 (1 byte,  addr 8)
            asm.cmpi(4, 11),      # compare i, 11       (3 bytes, addr 9)
            asm.br(asm.NE, (-8) & 0xFF),  # if NE goto loop (addr 6) (2 bytes, addr 12)
            asm.halt(),           #                     (1 byte,  addr 14)
        )
        c = run(prog, max_steps=500)
        assert c.regs[3] == 55

    def test_fibonacci(self):
        """Compute fib(10) = 55."""
        # R3 = a (fib(n-2)), R4 = b (fib(n-1)), R5 = counter, R6 = temp
        prog = asm.program(
            asm.ldi(3, 0),        # a = 0
            asm.ldi(4, 1),        # b = 1
            asm.ldi(5, 2),        # i = 2
            # loop:                                     (addr 9)
            asm.mov(6, 4),        # temp = b            (2 bytes)
            asm.add(4, 3),        # b = a + b           (2 bytes)
            asm.mov(3, 6),        # a = temp            (2 bytes)
            asm.inc(5),           # i++                 (1 byte)
            asm.cmpi(5, 10),      # compare i, 10       (3 bytes)
            asm.br(asm.LE, (-12) & 0xFF),  # if LE goto loop (2 bytes)
            asm.halt(),
        )
        c = run(prog, max_steps=500)
        assert c.regs[4] == 55  # fib(10) = 55

    def test_memcpy_loop(self):
        """Copy 4 bytes from 0x500 to 0x600."""
        # Layout: ldi64=11 @0, ldi64=11 @11, ldi=3 @22
        # loop @25: ld_b=2, st_b=2, inc=1, inc=1, inc=1, cmpi=3, br=2 → 12 bytes
        # pc after br = 37, target = 25, offset = 25-37 = -12
        prog = asm.program(
            asm.ldi64(3, 0x500),   # src
            asm.ldi64(4, 0x600),   # dst
            asm.ldi(5, 0),         # i = 0
            # loop @25:
            asm.ld_b(6, 3),        # R6 = M[src]
            asm.st_b(4, 6),        # M[dst] = R6
            asm.inc(3),            # src++
            asm.inc(4),            # dst++
            asm.inc(5),            # i++
            asm.cmpi(5, 4),        # i < 4 ?
            asm.br(asm.NE, (-12) & 0xFF),
            asm.halt(),
        )
        c = make_core(prog)
        c.mem[0x500:0x504] = b"ABCD"
        c.run(500)
        assert bytes(c.mem[0x600:0x604]) == b"ABCD"


# =======================================================================
#  C Accelerator
# =======================================================================

class TestAccel:
    @pytest.fixture
    def accel_core(self):
        """Create a core with C accelerator loaded (skip if not built)."""
        mem = bytearray(0x10000)
        c = MP64Core(mem)
        c.regs[2] = len(mem) - 8
        if not c.load_accel():
            pytest.skip("C accelerator not built (run `make accel`)")
        return c

    def test_accel_add(self, accel_core):
        c = accel_core
        prog = asm.program(asm.ldi(3, 10), asm.ldi(4, 20), asm.add(3, 4), asm.halt())
        c.mem[:len(prog)] = prog
        c.run_accel(100)
        assert c.regs[3] == 30

    def test_accel_sum_1_to_10(self, accel_core):
        c = accel_core
        prog = asm.program(
            asm.ldi(3, 0),
            asm.ldi(4, 1),
            asm.add(3, 4),
            asm.inc(4),
            asm.cmpi(4, 11),
            asm.br(asm.NE, (-8) & 0xFF),
            asm.halt(),
        )
        c.mem[:len(prog)] = prog
        c.run_accel(500)
        assert c.regs[3] == 55

    def test_accel_fibonacci(self, accel_core):
        c = accel_core
        prog = asm.program(
            asm.ldi(3, 0),
            asm.ldi(4, 1),
            asm.ldi(5, 2),
            asm.mov(6, 4),
            asm.add(4, 3),
            asm.mov(3, 6),
            asm.inc(5),
            asm.cmpi(5, 10),
            asm.br(asm.LE, (-12) & 0xFF),
            asm.halt(),
        )
        c.mem[:len(prog)] = prog
        c.run_accel(500)
        assert c.regs[4] == 55

    def test_accel_fallback_csr(self, accel_core):
        """Test that CSR instructions fall back to Python correctly."""
        c = accel_core
        prog = asm.program(
            asm.csrr(3, 0x31),   # CPUID → falls back to Python
            asm.halt(),
        )
        c.mem[:len(prog)] = prog
        c.run_accel(100)
        assert c.regs[3] == 0x4D503634

    def test_accel_mul(self, accel_core):
        c = accel_core
        prog = asm.program(asm.ldi(3, 7), asm.ldi(4, 6), asm.mul(3, 4), asm.halt())
        c.mem[:len(prog)] = prog
        c.run_accel(100)
        assert c.regs[3] == 42
