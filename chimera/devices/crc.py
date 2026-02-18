"""CRC-32/64 accelerator peripheral.

MMIO offset: +0x07C0, size: 32 bytes

Register map (byte offsets from device base):
    +0x00..07  POLY      (RW) — 64-bit polynomial (LE)
    +0x08..0F  INIT      (RW) — 64-bit initial value (LE)
    +0x10..17  DIN       (W)  — 64-bit data-in (LE); triggers CRC update
    +0x18..1F  RESULT    (R)  — 64-bit CRC result (LE)
"""
from __future__ import annotations

MASK64 = 0xFFFF_FFFF_FFFF_FFFF
MASK32 = 0xFFFF_FFFF

# Pre-built CRC-32 (IEEE 802.3) table
_CRC32_POLY = 0xEDB88320
_CRC32_TABLE: list[int] = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_CRC32_POLY ^ (_c >> 1)) if (_c & 1) else (_c >> 1)
    _CRC32_TABLE.append(_c & MASK32)


class CRC:
    """CRC accelerator — supports CRC-32 and CRC-64 via programmable polynomial."""

    def __init__(self):
        self.poly: int = _CRC32_POLY   # default: CRC-32 IEEE
        self.init: int = MASK32         # default: 0xFFFFFFFF
        self.crc: int = MASK32          # running CRC
        self._din_buf = bytearray(8)    # accumulate LE bytes
        self._din_idx = 0
        self.bytes_processed: int = 0

    def reset(self):
        self.crc = self.init
        self.bytes_processed = 0

    def _update_byte(self, b: int):
        """Update CRC with one byte using table lookup (CRC-32 fast path)."""
        if self.poly == _CRC32_POLY:
            self.crc = _CRC32_TABLE[(self.crc ^ b) & 0xFF] ^ (self.crc >> 8)
        else:
            # Generic bit-by-bit for arbitrary polynomials
            for bit in range(8):
                if (self.crc ^ b) & 1:
                    self.crc = (self.crc >> 1) ^ self.poly
                else:
                    self.crc >>= 1
                b >>= 1
        self.crc &= MASK64
        self.bytes_processed += 1

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if 0x00 <= off < 0x08:
            return (self.poly >> (8 * off)) & 0xFF
        if 0x08 <= off < 0x10:
            return (self.init >> (8 * (off - 0x08))) & 0xFF
        if 0x18 <= off < 0x20:
            return (self.crc >> (8 * (off - 0x18))) & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if 0x00 <= off < 0x08:
            sh = 8 * off
            self.poly = (self.poly & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x08 <= off < 0x10:
            sh = 8 * (off - 0x08)
            self.init = (self.init & ~(0xFF << sh) & MASK64) | (val << sh)
            self.crc = self.init  # writing INIT resets the running CRC
        elif 0x10 <= off < 0x18:
            # DIN: accumulate LE bytes, update CRC byte-by-byte
            self._update_byte(val)
