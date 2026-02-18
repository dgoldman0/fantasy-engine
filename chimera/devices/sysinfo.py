"""SysInfo — Read-only system information register block for Chimera-1.

MMIO layout (80 bytes = 0x50, 64-bit aligned):
    +0x00   BOARD_ID    R   "CHM1" + version 1.0  → 0x4348_4D31_0001_0000
    +0x08   RAM_SIZE    R   Main memory size in bytes
    +0x10   NUM_CORES   R   Total MP64 cores
    +0x18   CLUSTER_EN  RW  Per-cluster enable bitmask (only writable reg)
    +0x20   LM1_TILES   R   Number of LM-1 tiles
    +0x28   LM1_MEMSZ   R   Memory per LM-1 tile
    +0x30   MMIO_BASE   R   MMIO base address
    +0x38   MMIO_SIZE   R   MMIO region size
    +0x40   TOTAL_DEVS  R   Number of registered MMIO devices
    +0x48   RESERVED    R   0
"""
from __future__ import annotations


class SysInfo:
    """Read-only system information."""

    SIZE = 0x50  # 80 bytes

    def __init__(self, *,
                 ram_size: int = 0x100000,
                 num_cores: int = 4,
                 lm1_tiles: int = 8,
                 lm1_memsz: int = 1 << 20,
                 mmio_base: int = 0xFFFF_FF00_0000_0000,
                 mmio_size: int = 0x1000,
                 total_devs: int = 0):
        self._regs: dict[int, int] = {
            0x00: 0x0000_0001_314D_4843,  # LE: "CHM1" + version 1
            0x08: ram_size,
            0x10: num_cores,
            0x18: 0xFFFF_FFFF_FFFF_FFFF,  # all clusters enabled
            0x20: lm1_tiles,
            0x28: lm1_memsz,
            0x30: mmio_base,
            0x38: mmio_size,
            0x40: total_devs,
            0x48: 0,
        }
        self.cluster_en: int = 0xFFFF_FFFF_FFFF_FFFF

    def read8(self, off: int) -> int:
        reg_base = off & ~0x07  # align down to 8
        byte_idx = off & 0x07
        if reg_base == 0x18:
            val = self.cluster_en
        else:
            val = self._regs.get(reg_base, 0)
        return (val >> (byte_idx * 8)) & 0xFF

    def write8(self, off: int, val: int):
        val &= 0xFF
        # Only CLUSTER_EN (0x18..0x1F) is writable
        if 0x18 <= off < 0x20:
            byte_idx = off - 0x18
            mask = 0xFF << (byte_idx * 8)
            self.cluster_en = (self.cluster_en & ~mask) | (val << (byte_idx * 8))
