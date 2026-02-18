"""True Random Number Generator (TRNG) peripheral.

MMIO offset: +0x08C0, size: 64 bytes

Register map (byte offsets from device base):
    +0x00      CMD       (W)  — 0x01 GENERATE (fill output register with fresh random)
    +0x01      STATUS    (R)  — bit0: busy, bit1: entropy ready, bit7: present
    +0x02      reserved
    +0x03      reserved
    +0x04..0B  OUTPUT    (R)  — 64-bit random value (LE)
    +0x0C..13  OUTPUT2   (R)  — second 64-bit random value (LE)
    +0x14..1B  OUTPUT3   (R)  — third 64-bit random value (LE)
    +0x1C..23  OUTPUT4   (R)  — fourth 64-bit random value (LE)
"""
from __future__ import annotations
import os
import struct

MASK64 = 0xFFFF_FFFF_FFFF_FFFF


class TRNG:
    """True Random Number Generator (backed by os.urandom)."""

    def __init__(self):
        self.status: int = 0x82    # bit7=present, bit1=entropy ready
        self.output = bytearray(32)  # 4 × 64-bit = 256 bits
        self.words_generated: int = 0
        self._generate()

    def _generate(self):
        """Fill output registers with fresh randomness."""
        self.output[:] = os.urandom(32)
        self.words_generated += 4

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x01:
            return self.status
        if 0x04 <= off < 0x24:
            return self.output[off - 0x04]
        return 0

    def write8(self, off: int, val: int):
        if off == 0x00 and (val & 0xFF) == 0x01:
            self._generate()
