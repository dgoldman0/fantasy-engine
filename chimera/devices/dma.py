"""DMA Engine — Descriptor-ring DMA for Chimera-1.

The DMA engine is accessed via MP64 CSRs 0x50–0x55.  This module provides
a standalone ``DMAEngine`` class that can also be used by the SoC as a
shared DMA block with MMIO device interface.

MMIO layout (64 bytes):
    +0x00   RING_BASE   RW  64-bit LE descriptor ring base address
    +0x08   RING_SIZE   RW  64-bit LE ring size (power of 2, in entries)
    +0x10   HEAD        RW  64-bit LE head pointer
    +0x18   TAIL        RW  64-bit LE tail pointer
    +0x20   STATUS      R   64-bit LE (0=idle, 1=busy, 2=error, 3=done)
    +0x28   CTRL        RW  64-bit LE (bit0=enable, bit1=start, bit2=reset)
    +0x30   XFER_COUNT  R   64-bit LE completed transfer count
    +0x38   ERR_COUNT   R   64-bit LE error count

DMA Descriptor (32 bytes, in memory at ring_base + idx*32):
    +0x00   SRC_ADDR    64-bit LE source address
    +0x08   DST_ADDR    64-bit LE destination address
    +0x10   LENGTH      32-bit LE transfer length in bytes
    +0x14   FLAGS       32-bit LE (bit0=valid, bit1=irq_on_done)
    +0x18   STATUS      32-bit LE (0=pending, 1=done, 2=error)
    +0x1C   RESERVED    32-bit
"""
from __future__ import annotations
from typing import Callable, Optional


class DMAEngine:
    """Descriptor-ring DMA engine."""

    SIZE = 0x40  # 64 bytes MMIO

    def __init__(self):
        self.ring_base: int = 0
        self.ring_size: int = 0  # entries (power of 2)
        self.head: int = 0
        self.tail: int = 0
        self.status: int = 0  # 0=idle 1=busy 2=error 3=done
        self.ctrl: int = 0
        self.xfer_count: int = 0
        self.err_count: int = 0

        # DMA callbacks — set by SoC wiring
        self._mem_read: Optional[Callable[[int], int]] = None
        self._mem_write: Optional[Callable[[int, int], None]] = None

    def _mem_read64(self, addr: int) -> int:
        if not self._mem_read:
            return 0
        val = 0
        for i in range(8):
            val |= self._mem_read(addr + i) << (i * 8)
        return val

    def _mem_write64(self, addr: int, val: int):
        if not self._mem_write:
            return
        for i in range(8):
            self._mem_write(addr + i, (val >> (i * 8)) & 0xFF)

    def _mem_read32(self, addr: int) -> int:
        if not self._mem_read:
            return 0
        val = 0
        for i in range(4):
            val |= self._mem_read(addr + i) << (i * 8)
        return val

    def _mem_write32(self, addr: int, val: int):
        if not self._mem_write:
            return
        for i in range(4):
            self._mem_write(addr + i, (val >> (i * 8)) & 0xFF)

    def process(self, max_descs: int = 64):
        """Process pending DMA descriptors.  Called by SoC tick."""
        if not (self.ctrl & 0x01):  # not enabled
            return
        if self.ring_size == 0 or not self._mem_read:
            return

        processed = 0
        while self.head != self.tail and processed < max_descs:
            desc_addr = self.ring_base + (self.head % self.ring_size) * 32
            src = self._mem_read64(desc_addr + 0x00)
            dst = self._mem_read64(desc_addr + 0x08)
            length = self._mem_read32(desc_addr + 0x10)
            flags = self._mem_read32(desc_addr + 0x14)

            if not (flags & 0x01):  # not valid
                self.head = (self.head + 1) % self.ring_size
                continue

            self.status = 1  # busy
            try:
                for i in range(length):
                    b = self._mem_read(src + i)
                    self._mem_write(dst + i, b)
                self._mem_write32(desc_addr + 0x18, 1)  # done
                self.xfer_count += 1
            except Exception:
                self._mem_write32(desc_addr + 0x18, 2)  # error
                self.err_count += 1

            self.head = (self.head + 1) % self.ring_size
            processed += 1

        self.status = 0 if self.head == self.tail else 3  # idle or done

    def _execute_ctrl(self, val: int):
        """Handle control register writes."""
        self.ctrl = val
        if val & 0x04:  # reset
            self.head = 0
            self.tail = 0
            self.status = 0
            self.xfer_count = 0
            self.err_count = 0
            self.ctrl = 0
        elif val & 0x02:  # start
            self.process()

    # -- MMIO interface ---------------------------------------------------
    def read8(self, off: int) -> int:
        if 0x00 <= off < 0x08:
            return (self.ring_base >> ((off) * 8)) & 0xFF
        if 0x08 <= off < 0x10:
            return (self.ring_size >> ((off - 0x08) * 8)) & 0xFF
        if 0x10 <= off < 0x18:
            return (self.head >> ((off - 0x10) * 8)) & 0xFF
        if 0x18 <= off < 0x20:
            return (self.tail >> ((off - 0x18) * 8)) & 0xFF
        if 0x20 <= off < 0x28:
            return (self.status >> ((off - 0x20) * 8)) & 0xFF
        if 0x28 <= off < 0x30:
            return (self.ctrl >> ((off - 0x28) * 8)) & 0xFF
        if 0x30 <= off < 0x38:
            return (self.xfer_count >> ((off - 0x30) * 8)) & 0xFF
        if 0x38 <= off < 0x40:
            return (self.err_count >> ((off - 0x38) * 8)) & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if 0x00 <= off < 0x08:
            shift = off * 8
            mask = 0xFF << shift
            self.ring_base = (self.ring_base & ~mask) | (val << shift)
        elif 0x08 <= off < 0x10:
            shift = (off - 0x08) * 8
            mask = 0xFF << shift
            self.ring_size = (self.ring_size & ~mask) | (val << shift)
        elif 0x10 <= off < 0x18:
            shift = (off - 0x10) * 8
            mask = 0xFF << shift
            self.head = (self.head & ~mask) | (val << shift)
        elif 0x18 <= off < 0x20:
            shift = (off - 0x18) * 8
            mask = 0xFF << shift
            self.tail = (self.tail & ~mask) | (val << shift)
        elif 0x28 <= off < 0x30:
            shift = (off - 0x28) * 8
            mask = 0xFF << shift
            new_ctrl = (self.ctrl & ~mask) | (val << shift)
            if off == 0x28:  # trigger on first byte write
                self._execute_ctrl(new_ctrl)
            else:
                self.ctrl = new_ctrl
