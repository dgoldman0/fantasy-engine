"""Tagged-value helpers for the LM-1 Lisp Machine.

Every 64-bit word is self-describing via its low bits:
  - Fixnum:  bit 0 == 0  → value = word >> 1 (63-bit signed)
  - Ref:     bits 1:0 == 01
  - Cons:    bits 2:0 == 011
  - Special: bits 2:0 == 101
  - Header:  bits 2:0 == 111  (memory only)
"""
from __future__ import annotations

MASK64 = 0xFFFF_FFFF_FFFF_FFFF

# ── Special constants ────────────────────────────────────────────────
NIL       = 0x05
T         = 0x0D
UNBOUND   = 0x15
EOF       = 0x1D
VOID      = 0x25
UNDEFINED = 0x2D

# ── Tag predicates ───────────────────────────────────────────────────
def is_fixnum(w: int) -> bool: return (w & 1) == 0
def is_ref(w: int) -> bool:    return (w & 3) == 1
def is_cons(w: int) -> bool:   return (w & 7) == 3
def is_special(w: int) -> bool: return (w & 7) == 5
def is_header(w: int) -> bool: return (w & 7) == 7

def is_truthy(w: int) -> bool:
    return w != NIL and w != 0  # 0 is fixnum(0)

# ── Fixnum ───────────────────────────────────────────────────────────
def tag_fixnum(n: int) -> int:
    return (n << 1) & MASK64

def untag_fixnum(w: int) -> int:
    """Arithmetic right-shift by 1 (preserves sign)."""
    w &= MASK64
    v = w >> 1
    if w & (1 << 63):
        v |= (1 << 63)
    # Convert from uint64 to Python signed
    if v >= (1 << 63):
        v -= (1 << 64)
    return v

# ── References ───────────────────────────────────────────────────────
ADDR_MASK = 0x0007_FFFF_FFFF_FFF8

def tag_ref(addr: int) -> int:
    return (addr & ADDR_MASK) | 1

def untag_ref(w: int) -> int:
    return w & ADDR_MASK

def tag_cons(addr: int) -> int:
    return (addr & ADDR_MASK) | 3

def untag_cons(w: int) -> int:
    return w & ADDR_MASK

# ── Object headers ───────────────────────────────────────────────────
# Header layout:
#   bits 63:56 = GC bits
#   bits 55:24 = shape ID
#   bits 23:8  = size (in words, excluding header)
#   bits 7:3   = header subtype
#   bits 2:0   = 111

HDR_INSTANCE = 0;  HDR_CONS = 1;  HDR_VECTOR = 2;  HDR_STRING = 3
HDR_CLOSURE  = 4;  HDR_SYMBOL = 5

def make_header(htype: int, size: int, shape: int = 0, gc: int = 0) -> int:
    return ((gc & 0xFF) << 56 | (shape & 0xFFFF_FFFF) << 24 |
            (size & 0xFFFF) << 8 | (htype & 0x1F) << 3 | 7)

def header_size(h: int) -> int:  return (h >> 8) & 0xFFFF
def header_type(h: int) -> int:  return (h >> 3) & 0x1F
def header_shape(h: int) -> int: return (h >> 24) & 0xFFFF_FFFF

# ── TST tag codes ────────────────────────────────────────────────────
TST_FIXNUM  = 0
TST_REF     = 1
TST_CONS    = 2
TST_SPECIAL = 3
TST_NIL     = 4
TST_CHAR    = 5
TST_SFLOAT  = 6
TST_HEADER  = 7
