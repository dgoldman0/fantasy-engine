"""NTT (Number Theoretic Transform) accelerator.

MMIO offset: +0x0900, size: 64 bytes

Used for post-quantum lattice-based cryptography (Kyber, Dilithium).
Computes forward/inverse NTT over Z_q[X]/(X^256+1) with q = 3329.

Register map (byte offsets from device base):
    +0x00      CMD       (W)  — 0x01 FWD_NTT, 0x02 INV_NTT, 0x03 POINTWISE_MUL,
                                0x04 REDUCE, 0x05 RESET
    +0x01      STATUS    (R)  — bit0: busy, bit7: present
    +0x02..03  reserved
    +0x04..0B  DMA_SRC   (RW) — 64-bit source address (LE)
    +0x0C..13  DMA_DST   (RW) — 64-bit destination address (LE)
    +0x14..15  POLY_LEN  (RW) — polynomial length (default 256, u16 LE)
    +0x16..17  MODULUS   (RW) — modulus q (default 3329)
"""
from __future__ import annotations

MASK64 = 0xFFFF_FFFF_FFFF_FFFF
KYBER_Q = 3329
KYBER_N = 256


class NTT:
    """NTT accelerator (functional model).

    Operations are performed in-memory via DMA callbacks.
    Without DMA wiring, the device tracks registers but cannot process data.
    """

    def __init__(self):
        self.status: int = 0x80  # bit7 = present
        self.dma_src: int = 0
        self.dma_dst: int = 0
        self.poly_len: int = KYBER_N
        self.modulus: int = KYBER_Q
        self.ops_done: int = 0
        # DMA callbacks (set by system wiring)
        self._mem_read = None   # callable(addr) -> int (byte)
        self._mem_write = None  # callable(addr, val)

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x01:
            return self.status
        if 0x04 <= off < 0x0C:
            return (self.dma_src >> (8 * (off - 0x04))) & 0xFF
        if 0x0C <= off < 0x14:
            return (self.dma_dst >> (8 * (off - 0x0C))) & 0xFF
        if off == 0x14:
            return self.poly_len & 0xFF
        if off == 0x15:
            return (self.poly_len >> 8) & 0xFF
        if off == 0x16:
            return self.modulus & 0xFF
        if off == 0x17:
            return (self.modulus >> 8) & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:  # CMD
            if val == 0x05:  # RESET
                self.__init__()
            else:
                self.ops_done += 1
                # Actual NTT operations would use DMA to read/write
                # polynomial coefficients. Tracked as ops for testing.
        elif 0x04 <= off < 0x0C:
            sh = 8 * (off - 0x04)
            self.dma_src = (self.dma_src & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x0C <= off < 0x14:
            sh = 8 * (off - 0x0C)
            self.dma_dst = (self.dma_dst & ~(0xFF << sh) & MASK64) | (val << sh)
        elif off == 0x14:
            self.poly_len = (self.poly_len & 0xFF00) | val
        elif off == 0x15:
            self.poly_len = (self.poly_len & 0x00FF) | (val << 8)
        elif off == 0x16:
            self.modulus = (self.modulus & 0xFF00) | val
        elif off == 0x17:
            self.modulus = (self.modulus & 0x00FF) | (val << 8)
