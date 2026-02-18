"""FieldALU — multi-precision modular arithmetic accelerator.

MMIO offset: +0x0840 + 0x80 = dependent on final map (allocated near X25519)
For the emulator we place it at +0x0980 (after KEM).

Register map (byte offsets from device base):
    +0x00      CMD       (W)  — 0x01 MOD_ADD, 0x02 MOD_SUB, 0x03 MOD_MUL,
                                0x04 MOD_EXP, 0x05 MOD_INV, 0xFF RESET
    +0x01      STATUS    (R)  — bit0: busy, bit7: present
    +0x02      OPSIZE    (RW) — operand size in bytes (max 64 = 512-bit)
    +0x03      reserved
    +0x04..0B  DMA_A     (RW) — 64-bit address of operand A (LE)
    +0x0C..13  DMA_B     (RW) — 64-bit address of operand B (LE)
    +0x14..1B  DMA_MOD   (RW) — 64-bit address of modulus (LE)
    +0x1C..23  DMA_OUT   (RW) — 64-bit address of result (LE)
"""
from __future__ import annotations

MASK64 = 0xFFFF_FFFF_FFFF_FFFF


class FieldALU:
    """Multi-precision modular arithmetic unit (stub model).

    Real operations use DMA to read operands and write results.
    Without DMA wiring, the device tracks registers and counts ops.
    """

    def __init__(self):
        self.status: int = 0x80  # bit7 = present
        self.opsize: int = 32    # default 256-bit (32 bytes)
        self.dma_a: int = 0
        self.dma_b: int = 0
        self.dma_mod: int = 0
        self.dma_out: int = 0
        self.ops_done: int = 0
        self._mem_read = None
        self._mem_write = None

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x01: return self.status
        if off == 0x02: return self.opsize
        if 0x04 <= off < 0x0C:
            return (self.dma_a >> (8 * (off - 0x04))) & 0xFF
        if 0x0C <= off < 0x14:
            return (self.dma_b >> (8 * (off - 0x0C))) & 0xFF
        if 0x14 <= off < 0x1C:
            return (self.dma_mod >> (8 * (off - 0x14))) & 0xFF
        if 0x1C <= off < 0x24:
            return (self.dma_out >> (8 * (off - 0x1C))) & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:
            if val == 0xFF:
                self.__init__()
            else:
                self.ops_done += 1
        elif off == 0x02:
            self.opsize = val
        elif 0x04 <= off < 0x0C:
            sh = 8 * (off - 0x04)
            self.dma_a = (self.dma_a & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x0C <= off < 0x14:
            sh = 8 * (off - 0x0C)
            self.dma_b = (self.dma_b & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x14 <= off < 0x1C:
            sh = 8 * (off - 0x14)
            self.dma_mod = (self.dma_mod & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x1C <= off < 0x24:
            sh = 8 * (off - 0x1C)
            self.dma_out = (self.dma_out & ~(0xFF << sh) & MASK64) | (val << sh)
