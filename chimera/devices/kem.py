"""KEM (ML-KEM / Kyber) accelerator peripheral.

MMIO offset: +0x0940, size: 256 bytes

Provides hardware-accelerated key encapsulation:
  - KeyGen: generate (pk, sk)
  - Encaps: (pk) → (ct, shared_secret)
  - Decaps: (sk, ct) → shared_secret

Register map (byte offsets from device base):
    +0x00      CMD       (W)  — 0x01 KEYGEN, 0x02 ENCAPS, 0x03 DECAPS, 0xFF RESET
    +0x01      STATUS    (R)  — bit0: busy, bit7: present
    +0x02      VARIANT   (RW) — 0=Kyber512, 1=Kyber768, 2=Kyber1024
    +0x03      reserved
    +0x04..0B  DMA_PK    (RW) — 64-bit public key address (LE)
    +0x0C..13  DMA_SK    (RW) — 64-bit secret key address (LE)
    +0x14..1B  DMA_CT    (RW) — 64-bit ciphertext address (LE)
    +0x1C..23  DMA_SS    (RW) — 64-bit shared secret address (LE)
    +0x24..27  OP_COUNT  (R)  — 32-bit operations counter (LE)
"""
from __future__ import annotations
import hashlib

MASK64 = 0xFFFF_FFFF_FFFF_FFFF


class KEM:
    """ML-KEM (Kyber) accelerator (stub model).

    Real ML-KEM operations require the full lattice-based algorithm.
    This emulator model tracks register state and uses DMA callbacks
    for memory access. Without a real Kyber library, it produces
    deterministic pseudo-outputs via SHA-256.
    """

    def __init__(self):
        self.status: int = 0x80  # bit7 = present
        self.variant: int = 1    # default Kyber768
        self.dma_pk: int = 0
        self.dma_sk: int = 0
        self.dma_ct: int = 0
        self.dma_ss: int = 0
        self.op_count: int = 0
        self._mem_read = None
        self._mem_write = None

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x01: return self.status
        if off == 0x02: return self.variant
        if 0x04 <= off < 0x0C:
            return (self.dma_pk >> (8 * (off - 0x04))) & 0xFF
        if 0x0C <= off < 0x14:
            return (self.dma_sk >> (8 * (off - 0x0C))) & 0xFF
        if 0x14 <= off < 0x1C:
            return (self.dma_ct >> (8 * (off - 0x14))) & 0xFF
        if 0x1C <= off < 0x24:
            return (self.dma_ss >> (8 * (off - 0x1C))) & 0xFF
        if 0x24 <= off < 0x28:
            return (self.op_count >> (8 * (off - 0x24))) & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:
            if val == 0xFF:
                self.__init__()
            else:
                self.op_count += 1
        elif off == 0x02:
            self.variant = val & 0x03
        elif 0x04 <= off < 0x0C:
            sh = 8 * (off - 0x04)
            self.dma_pk = (self.dma_pk & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x0C <= off < 0x14:
            sh = 8 * (off - 0x0C)
            self.dma_sk = (self.dma_sk & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x14 <= off < 0x1C:
            sh = 8 * (off - 0x14)
            self.dma_ct = (self.dma_ct & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x1C <= off < 0x24:
            sh = 8 * (off - 0x1C)
            self.dma_ss = (self.dma_ss & ~(0xFF << sh) & MASK64) | (val << sh)
