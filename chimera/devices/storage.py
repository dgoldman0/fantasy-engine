"""Storage — Sector-based block storage for Chimera-1.

MegaPad-style CMD/STATUS register interface with host-file backing.

MMIO layout (16 bytes):
    +0x00   CMD         W   0x01=READ 0x02=WRITE 0x03=STATUS 0xFF=FLUSH
    +0x01   STATUS      R   bit0:busy bit1:error bit7:present
    +0x02   SECTOR      RW  32-bit LE sector number (4 bytes)
    +0x06   DMA_ADDR    RW  64-bit LE DMA address (8 bytes)
    +0x0E   SEC_COUNT   RW  number of sectors (1–255)
    +0x0F   DATA        RW  byte-at-a-time data port
"""
from __future__ import annotations

import os
from typing import Callable, Optional

SECTOR_SIZE = 512
DEFAULT_SECTORS = 2048  # 1 MiB


class Storage:
    """Sector-based block storage with DMA and host-file backing."""

    SIZE = 0x10  # 16 bytes

    # Commands
    CMD_READ   = 0x01
    CMD_WRITE  = 0x02
    CMD_STATUS = 0x03
    CMD_FLUSH  = 0xFF

    def __init__(self, image_path: Optional[str] = None,
                 total_sectors: int = DEFAULT_SECTORS):
        self.total_sectors = total_sectors
        self._image_path = image_path
        self._image: bytearray = bytearray(total_sectors * SECTOR_SIZE)

        self.sector_num: int = 0
        self.dma_addr: int = 0
        self.sec_count: int = 1
        self.busy: bool = False
        self.error: bool = False

        self._data_buf = bytearray(SECTOR_SIZE)
        self._data_pos = 0

        # DMA callbacks — set by SoC wiring
        self._mem_read: Optional[Callable[[int], int]] = None
        self._mem_write: Optional[Callable[[int, int], None]] = None

        if image_path:
            self.load_image(image_path)

    # -- Image I/O --------------------------------------------------------
    def load_image(self, path: str):
        """Load disk image from host file."""
        self._image_path = path
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            self._image = bytearray(data)
            # Pad to full size if needed
            if len(self._image) < self.total_sectors * SECTOR_SIZE:
                self._image.extend(
                    b"\x00" * (self.total_sectors * SECTOR_SIZE - len(self._image))
                )
        else:
            self._image = bytearray(self.total_sectors * SECTOR_SIZE)

    def save_image(self) -> bool:
        """Save disk image to host file."""
        if not self._image_path:
            return False
        with open(self._image_path, "wb") as f:
            f.write(self._image)
        return True

    # -- Sector access ----------------------------------------------------
    def read_sectors(self, start: int, count: int) -> bytes:
        """Read raw bytes from disk image."""
        off = start * SECTOR_SIZE
        nbytes = count * SECTOR_SIZE
        return bytes(self._image[off:off + nbytes])

    def write_sectors(self, start: int, count: int, data: bytes | bytearray):
        """Write raw bytes into disk image."""
        off = start * SECTOR_SIZE
        nbytes = count * SECTOR_SIZE
        self._image[off:off + nbytes] = data[:nbytes]

    # -- Command dispatch -------------------------------------------------
    def _execute_cmd(self, cmd: int):
        self.error = False
        self.busy = True
        try:
            if cmd == self.CMD_READ:
                if self.sector_num + self.sec_count > self.total_sectors:
                    self.error = True
                    return
                data = self.read_sectors(self.sector_num, self.sec_count)
                if self._mem_write and self.dma_addr:
                    for i, b in enumerate(data):
                        self._mem_write(self.dma_addr + i, b)
                self._data_buf = bytearray(data[:SECTOR_SIZE])
                self._data_pos = 0

            elif cmd == self.CMD_WRITE:
                if self.sector_num + self.sec_count > self.total_sectors:
                    self.error = True
                    return
                nbytes = self.sec_count * SECTOR_SIZE
                if self._mem_read and self.dma_addr:
                    data = bytearray()
                    for i in range(nbytes):
                        data.append(self._mem_read(self.dma_addr + i))
                    self.write_sectors(self.sector_num, self.sec_count, data)
                else:
                    # Write from data port buffer (single sector)
                    self.write_sectors(self.sector_num, 1, self._data_buf)

            elif cmd == self.CMD_FLUSH:
                self.save_image()

        finally:
            self.busy = False

    # -- MMIO interface ---------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x00:
            return 0  # CMD write-only
        if off == 0x01:
            st = 0x80  # present
            if self.busy:
                st |= 0x01
            if self.error:
                st |= 0x02
            return st
        if 0x02 <= off < 0x06:
            return (self.sector_num >> ((off - 0x02) * 8)) & 0xFF
        if 0x06 <= off < 0x0E:
            return (self.dma_addr >> ((off - 0x06) * 8)) & 0xFF
        if off == 0x0E:
            return self.sec_count
        if off == 0x0F:
            if self._data_pos < len(self._data_buf):
                b = self._data_buf[self._data_pos]
                self._data_pos += 1
                return b
            return 0
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:
            self._execute_cmd(val)
        elif 0x02 <= off < 0x06:
            shift = (off - 0x02) * 8
            mask = 0xFF << shift
            self.sector_num = (self.sector_num & ~mask) | (val << shift)
        elif 0x06 <= off < 0x0E:
            shift = (off - 0x06) * 8
            mask = 0xFF << shift
            self.dma_addr = (self.dma_addr & ~mask) | (val << shift)
        elif off == 0x0E:
            self.sec_count = val if val > 0 else 1
        elif off == 0x0F:
            if self._data_pos < len(self._data_buf):
                self._data_buf[self._data_pos] = val
                self._data_pos += 1
