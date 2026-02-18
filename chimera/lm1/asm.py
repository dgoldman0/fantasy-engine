"""LM-1 instruction encoding helpers.

All instructions are 32-bit wide, 6-bit opcode in bits 31:26.
"""
from __future__ import annotations

# ── Opcodes ──────────────────────────────────────────────────────────
OP_TST           = 0
OP_TST_SHAPE     = 1
OP_ARITH_FIX     = 2
OP_ADD_FIX_IMM   = 3
OP_CMP_TAGGED    = 4
OP_ALLOC         = 8
OP_ALLOC_CONS    = 9
OP_ALLOCV        = 10
OP_ALLOC_CLOSURE = 11
OP_LD            = 16
OP_LD_CAR_CDR    = 17
OP_ST            = 18
OP_ST_WB         = 19
OP_ST_CAR_CDR    = 20
OP_CALL_IC       = 24
OP_IC_INSTALL    = 25
OP_CALL_DIRECT   = 26
OP_CALL_CLOSURE  = 27
OP_RET           = 28
OP_TAILCALL_IC   = 29
OP_TAILCALL_DIRECT = 30
OP_ARITH_RAW     = 48
OP_BITWISE       = 49
OP_LDR           = 50
OP_STR           = 51
OP_BR            = 52
OP_BR_COND       = 53
OP_PUSH_POP      = 54
OP_LI            = 55
OP_LUI           = 56
OP_PUSH_MULTI    = 57
OP_POP_MULTI     = 58
OP_LI32          = 59
OP_TRAP          = 60
OP_ERET          = 61
OP_SYS_INFO      = 62
OP_HALT_NOP      = 63

# ── Encoding formats ─────────────────────────────────────────────────
def encode_r(op: int, rd: int, rs1: int, rs2: int, func: int = 0) -> int:
    return (op << 26) | (rd << 21) | (rs1 << 16) | (rs2 << 11) | (func << 6)

def encode_i(op: int, rd: int, rs1: int, imm16: int) -> int:
    return (op << 26) | (rd << 21) | (rs1 << 16) | (imm16 & 0xFFFF)

def encode_s(op: int, rs: int, rt: int, field: int, imm11: int = 0) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (field << 11) | (imm11 & 0x7FF)

def encode_b(op: int, rs1: int, rs2: int, off16: int) -> int:
    return (op << 26) | (rs1 << 21) | (rs2 << 16) | (off16 & 0xFFFF)

def encode_x(op: int, payload: int) -> int:
    return (op << 26) | (payload & 0x03FF_FFFF)

# ── Convenience instruction builders ─────────────────────────────────

# Scalar arithmetic (ARITH_RAW)
def add(rd, rs1, rs2): return encode_r(OP_ARITH_RAW, rd, rs1, rs2, 0)
def sub(rd, rs1, rs2): return encode_r(OP_ARITH_RAW, rd, rs1, rs2, 1)
def mul(rd, rs1, rs2): return encode_r(OP_ARITH_RAW, rd, rs1, rs2, 2)
def div(rd, rs1, rs2): return encode_r(OP_ARITH_RAW, rd, rs1, rs2, 3)
def mod(rd, rs1, rs2): return encode_r(OP_ARITH_RAW, rd, rs1, rs2, 4)

# Bitwise
def and_(rd, rs1, rs2): return encode_r(OP_BITWISE, rd, rs1, rs2, 0)
def or_(rd, rs1, rs2):  return encode_r(OP_BITWISE, rd, rs1, rs2, 1)
def xor(rd, rs1, rs2):  return encode_r(OP_BITWISE, rd, rs1, rs2, 2)
def shl(rd, rs1, rs2):  return encode_r(OP_BITWISE, rd, rs1, rs2, 3)
def shr(rd, rs1, rs2):  return encode_r(OP_BITWISE, rd, rs1, rs2, 4)
def asr(rd, rs1, rs2):  return encode_r(OP_BITWISE, rd, rs1, rs2, 5)
def not_(rd, rs1):       return encode_r(OP_BITWISE, rd, rs1, 0, 6)

# Memory
def ldr(rd, rs1, imm16=0): return encode_i(OP_LDR, rd, rs1, imm16)
def str_(rs, rt, imm16=0): return encode_i(OP_STR, rs, rt, imm16)

# Branches
def br(off16):             return encode_b(OP_BR, 0, 0, off16)
def br_t(rs1, off16):      return encode_b(OP_BR_COND, rs1, 0, off16)
def br_nil(rs1, off16):    return encode_b(OP_BR_COND, rs1, 1, off16)
def br_fix_lt(rs1, off16): return encode_b(OP_BR_COND, rs1, 2, off16)
def br_fix_eq(rs1, off16): return encode_b(OP_BR_COND, rs1, 3, off16)
def br_fix_gt(rs1, off16): return encode_b(OP_BR_COND, rs1, 4, off16)
def br_eq(rs1, off16):     return encode_b(OP_BR_COND, rs1, 5, off16)

# Load immediate
def li(rd, imm16):   return encode_i(OP_LI, rd, 0, imm16)
def lui(rd, imm16):  return encode_i(OP_LUI, rd, 0, imm16)

# Push/Pop
def push(rs): return encode_r(OP_PUSH_POP, 0, rs, 0, 0)
def pop(rd):  return encode_r(OP_PUSH_POP, rd, 0, 0, 1)

# Tagged arithmetic
def add_fix(rd, rs1, rs2): return encode_r(OP_ARITH_FIX, rd, rs1, rs2, 0)
def sub_fix(rd, rs1, rs2): return encode_r(OP_ARITH_FIX, rd, rs1, rs2, 1)
def mul_fix(rd, rs1, rs2): return encode_r(OP_ARITH_FIX, rd, rs1, rs2, 2)
def div_fix(rd, rs1, rs2): return encode_r(OP_ARITH_FIX, rd, rs1, rs2, 3)
def add_fix_imm(rd, rs1, imm16): return encode_i(OP_ADD_FIX_IMM, rd, rs1, imm16)

# Tagged comparison
def cmp_tagged(rd, rs1, rs2): return encode_r(OP_CMP_TAGGED, rd, rs1, rs2, 0)
def eq_tagged(rd, rs1, rs2):  return encode_r(OP_CMP_TAGGED, rd, rs1, rs2, 1)

# Type test
def tst(rd, rs, tag): return encode_i(OP_TST, rd, rs, tag)

# Allocation
def alloc(rd, words, template=0):
    return encode_x(OP_ALLOC, (rd << 21) | (words << 11) | template)

def alloc_cons(rd):
    return encode_x(OP_ALLOC_CONS, rd << 21)

# Field loads/stores
def ld_field(rd, rs, field): return encode_i(OP_LD, rd, rs, field)
def ld_car(rd, rs):          return encode_i(OP_LD_CAR_CDR, rd, rs, 0)
def ld_cdr(rd, rs):          return encode_i(OP_LD_CAR_CDR, rd, rs, 1)
def st_field(rs, rt, field): return encode_s(OP_ST, rs, rt, field)
def st_wb(rs, rt, field):    return encode_s(OP_ST_WB, rs, rt, field)
def st_car(rs, rt):          return encode_s(OP_ST_CAR_CDR, rs, rt, 0)
def st_cdr(rs, rt):          return encode_s(OP_ST_CAR_CDR, rs, rt, 1)

# Call/Return
def call_direct(rs): return encode_x(OP_CALL_DIRECT, rs << 21)
def ret():           return encode_x(OP_RET, 0)
def tailcall_direct(rs): return encode_x(OP_TAILCALL_DIRECT, rs << 21)

# System
def trap(code):    return encode_x(OP_TRAP, code)
def eret():        return encode_x(OP_ERET, 0)
def sys_info(rd, sub): return encode_x(OP_SYS_INFO, (rd << 21) | sub)
def halt():        return encode_x(OP_HALT_NOP, 0)
def nop():         return encode_x(OP_HALT_NOP, 1)

# ── Program builder ──────────────────────────────────────────────────
def program(*insns: int) -> list[int]:
    """Return a list of 32-bit instruction words."""
    return list(insns)
