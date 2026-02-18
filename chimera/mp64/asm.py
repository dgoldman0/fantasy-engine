"""MP64 bytecode encoding helpers.

Each function returns a ``bytes`` object containing the encoded instruction.
These are intended for writing tests and small programs, not as a full
assembler (labels, macros, etc. are not supported here).
"""
from __future__ import annotations

# -----------------------------------------------------------------------
#  Condition codes (re-exported for convenience)
# -----------------------------------------------------------------------
AL = 0; EQ = 1; NE = 2; CS = 3; CC = 4
MI = 5; PL = 6; VS = 7; VC = 8
GT = 9; LE = 10; BQ = 11; BNQ = 12
SAT = 13; EF = 14; NV = 15

# -----------------------------------------------------------------------
#  Family 0 — SYS
# -----------------------------------------------------------------------
def idl()        -> bytes: return b"\x00"
def nop()        -> bytes: return b"\x01"
def halt()       -> bytes: return b"\x02"
def reset()      -> bytes: return b"\x03"
def rti()        -> bytes: return b"\x04"
def ret_1802()   -> bytes: return b"\x05"
def dis()        -> bytes: return b"\x06"
def mark()       -> bytes: return b"\x07"
def sav()        -> bytes: return b"\x08"
def seq()        -> bytes: return b"\x09"
def req()        -> bytes: return b"\x0a"
def ei()         -> bytes: return b"\x0b"
def di_()        -> bytes: return b"\x0c"  # trailing _ to avoid shadowing
def call_l(rn: int) -> bytes: return bytes([0x0d, rn & 0xf])
def ret_l()      -> bytes: return b"\x0e"
def trap()       -> bytes: return b"\x0f"

# -----------------------------------------------------------------------
#  Family 1/2 — INC / DEC
# -----------------------------------------------------------------------
def inc(r: int)  -> bytes: return bytes([0x10 | (r & 0xf)])
def dec(r: int)  -> bytes: return bytes([0x20 | (r & 0xf)])

# -----------------------------------------------------------------------
#  Family 3 — BR (short branch, signed 8-bit offset from end of insn)
# -----------------------------------------------------------------------
def br(cc: int, off: int) -> bytes:
    return bytes([0x30 | (cc & 0xf), off & 0xff])

# -----------------------------------------------------------------------
#  Family 4 — LBR (long branch, signed 16-bit offset, big-endian)
# -----------------------------------------------------------------------
def lbr(cc: int, off: int) -> bytes:
    o = off & 0xffff
    return bytes([0x40 | (cc & 0xf), (o >> 8) & 0xff, o & 0xff])

# -----------------------------------------------------------------------
#  Family 5 — MEM (scalar load/store)
# -----------------------------------------------------------------------
def _mem2(sub: int, rd: int, rs: int) -> bytes:
    return bytes([0x50 | (sub & 0xf), ((rd & 0xf) << 4) | (rs & 0xf)])

def ldn(rd: int, rs: int)  -> bytes: return _mem2(0, rd, rs)
def lda(rd: int, rs: int)  -> bytes: return _mem2(1, rd, rs)
def ldx(rd: int)            -> bytes: return _mem2(2, rd, 0)
def ldxa(rd: int)           -> bytes: return _mem2(3, rd, 0)
def str_(rd: int, rs: int) -> bytes: return _mem2(4, rd, rs)
def stxd(rd: int, rs: int) -> bytes: return _mem2(5, rd, rs)
def ld_b(rd: int, rs: int) -> bytes: return _mem2(6, rd, rs)
def st_b(rd: int, rs: int) -> bytes: return _mem2(7, rd, rs)
def ld_h(rd: int, rs: int) -> bytes: return _mem2(8, rd, rs)
def st_h(rd: int, rs: int) -> bytes: return _mem2(9, rd, rs)
def ld_w(rd: int, rs: int) -> bytes: return _mem2(0xA, rd, rs)
def st_w(rd: int, rs: int) -> bytes: return _mem2(0xB, rd, rs)
def ld_sb(rd: int, rs: int) -> bytes: return _mem2(0xC, rd, rs)
def ld_sh(rd: int, rs: int) -> bytes: return _mem2(0xD, rd, rs)
def ld_sw(rd: int, rs: int) -> bytes: return _mem2(0xE, rd, rs)

def ld_d(rd: int, rs: int, off: int) -> bytes:
    return bytes([0x5F, ((rd & 0xf) << 4) | (rs & 0xf), off & 0xff])

# -----------------------------------------------------------------------
#  Family 6 — IMM
# -----------------------------------------------------------------------
def ldi(rn: int, imm8: int) -> bytes:
    return bytes([0x60, rn & 0xf, imm8 & 0xff])

def ldi64(rn: int, imm64: int) -> bytes:
    """EXT.IMM64 + LDI — loads a full 64-bit immediate."""
    data = bytearray([0xF0, 0x60, rn & 0xf])
    data += (imm64 & 0xFFFF_FFFF_FFFF_FFFF).to_bytes(8, "little")
    return bytes(data)

def lhi(rn: int, imm16: int) -> bytes:
    o = imm16 & 0xffff
    return bytes([0x61, rn & 0xf, (o >> 8) & 0xff, o & 0xff])

def addi(rn: int, simm8: int) -> bytes:
    return bytes([0x62, rn & 0xf, simm8 & 0xff])

def andi(rn: int, imm8: int) -> bytes:
    return bytes([0x63, rn & 0xf, imm8 & 0xff])

def ori(rn: int, imm8: int) -> bytes:
    return bytes([0x64, rn & 0xf, imm8 & 0xff])

def xori(rn: int, imm8: int) -> bytes:
    return bytes([0x65, rn & 0xf, imm8 & 0xff])

def cmpi(rn: int, simm8: int) -> bytes:
    return bytes([0x66, rn & 0xf, simm8 & 0xff])

def subi(rn: int, simm8: int) -> bytes:
    return bytes([0x67, rn & 0xf, simm8 & 0xff])

def lsli(rn: int, imm4: int) -> bytes:
    return bytes([0x68, ((rn & 0xf) << 4) | (imm4 & 0xf)])

def lsri(rn: int, imm4: int) -> bytes:
    return bytes([0x69, ((rn & 0xf) << 4) | (imm4 & 0xf)])

def asri(rn: int, imm4: int) -> bytes:
    return bytes([0x6A, ((rn & 0xf) << 4) | (imm4 & 0xf)])

def roli(rn: int, imm4: int) -> bytes:
    return bytes([0x6B, ((rn & 0xf) << 4) | (imm4 & 0xf)])

def glo(rn: int) -> bytes: return bytes([0x6C, rn & 0xf])
def ghi(rn: int) -> bytes: return bytes([0x6D, rn & 0xf])
def plo(rn: int) -> bytes: return bytes([0x6E, rn & 0xf])
def phi(rn: int) -> bytes: return bytes([0x6F, rn & 0xf])

# -----------------------------------------------------------------------
#  Family 7 — ALU (register-register)
# -----------------------------------------------------------------------
def _alu(sub: int, rd: int, rs: int) -> bytes:
    return bytes([0x70 | (sub & 0xf), ((rd & 0xf) << 4) | (rs & 0xf)])

def add(rd: int, rs: int) -> bytes: return _alu(0, rd, rs)
def adc(rd: int, rs: int) -> bytes: return _alu(1, rd, rs)
def sub(rd: int, rs: int) -> bytes: return _alu(2, rd, rs)
def sbb(rd: int, rs: int) -> bytes: return _alu(3, rd, rs)
def and_(rd: int, rs: int) -> bytes: return _alu(4, rd, rs)
def or_(rd: int, rs: int) -> bytes: return _alu(5, rd, rs)
def xor(rd: int, rs: int) -> bytes: return _alu(6, rd, rs)
def cmp(rd: int, rs: int) -> bytes: return _alu(7, rd, rs)
def mov(rd: int, rs: int) -> bytes: return _alu(8, rd, rs)
def not_(rd: int, rs: int) -> bytes: return _alu(9, rd, rs)
def neg(rd: int, rs: int) -> bytes: return _alu(0xA, rd, rs)
def shl(rd: int, rs: int) -> bytes: return _alu(0xB, rd, rs)
def shr(rd: int, rs: int) -> bytes: return _alu(0xC, rd, rs)
def sar(rd: int, rs: int) -> bytes: return _alu(0xD, rd, rs)
def rol(rd: int, rs: int) -> bytes: return _alu(0xE, rd, rs)
def ror(rd: int, rs: int) -> bytes: return _alu(0xF, rd, rs)

# -----------------------------------------------------------------------
#  Family 8 — MEMALU (1802-compatible, 1 byte)
# -----------------------------------------------------------------------
def ldx_d()  -> bytes: return b"\x80"
def or_x()   -> bytes: return b"\x81"
def and_x()  -> bytes: return b"\x82"
def xor_x()  -> bytes: return b"\x83"
def add_x()  -> bytes: return b"\x84"
def sd_x()   -> bytes: return b"\x85"
def shr_d()  -> bytes: return b"\x86"
def sm_x()   -> bytes: return b"\x87"
def adc_x()  -> bytes: return b"\x88"
def sdb_x()  -> bytes: return b"\x89"
def shrc_d() -> bytes: return b"\x8A"
def smb_x()  -> bytes: return b"\x8B"
def shl_d()  -> bytes: return b"\x8C"
def shlc_d() -> bytes: return b"\x8D"
def irx()    -> bytes: return b"\x8E"
def ldxa_d()  -> bytes: return b"\x8F"

# -----------------------------------------------------------------------
#  Family 9 — I/O
# -----------------------------------------------------------------------
def out(port: int) -> bytes: return bytes([0x90 | (port & 0x7)])
def inp(port: int) -> bytes: return bytes([0x98 | (port & 0x7)])

# -----------------------------------------------------------------------
#  Family A/B — SEP / SEX
# -----------------------------------------------------------------------
def sep(r: int) -> bytes: return bytes([0xA0 | (r & 0xf)])
def sex(r: int) -> bytes: return bytes([0xB0 | (r & 0xf)])

# -----------------------------------------------------------------------
#  Family C — MULDIV
# -----------------------------------------------------------------------
def _md(sub: int, rd: int, rs: int) -> bytes:
    return bytes([0xC0 | (sub & 0xf), ((rd & 0xf) << 4) | (rs & 0xf)])

def mul(rd: int, rs: int)   -> bytes: return _md(0, rd, rs)
def mulh(rd: int, rs: int)  -> bytes: return _md(1, rd, rs)
def umul(rd: int, rs: int)  -> bytes: return _md(2, rd, rs)
def umulh(rd: int, rs: int) -> bytes: return _md(3, rd, rs)
def div(rd: int, rs: int)   -> bytes: return _md(4, rd, rs)
def udiv(rd: int, rs: int)  -> bytes: return _md(5, rd, rs)
def mod(rd: int, rs: int)   -> bytes: return _md(6, rd, rs)
def umod(rd: int, rs: int)  -> bytes: return _md(7, rd, rs)

# -----------------------------------------------------------------------
#  Family D — CSR
# -----------------------------------------------------------------------
def csrr(rd: int, addr: int) -> bytes:
    """CSR read: Rd = CSR[addr].  rd must be 0–7."""
    return bytes([0xD0 | (rd & 0x7), addr & 0xff])

def csrw(rs: int, addr: int) -> bytes:
    """CSR write: CSR[addr] = R[rs].  rs must be 0–7."""
    return bytes([0xD8 | (rs & 0x7), addr & 0xff])

# -----------------------------------------------------------------------
#  Family F — EXT prefix
# -----------------------------------------------------------------------
def ext(modifier: int) -> bytes:
    return bytes([0xF0 | (modifier & 0xf)])

# -----------------------------------------------------------------------
#  Program builder helper
# -----------------------------------------------------------------------
def program(*insns: bytes) -> bytearray:
    """Concatenate instruction bytes into a program bytearray."""
    buf = bytearray()
    for i in insns:
        buf += i
    return buf
