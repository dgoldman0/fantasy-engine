"""MMIO device bus — maps offset ranges to device emulators.

The bus is attached to an ``MP64Core`` via its ``mmio_read`` / ``mmio_write``
callback attributes.  Offsets are relative to ``mmio_start``.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .uart import UART  # noqa

MASK8 = 0xFF


class DeviceBus:
    """Simple flat device bus.

    Usage::

        bus = DeviceBus()
        bus.register(0x0000, 0x100, uart)
        bus.register(0x0100, 0x100, timer)

        core.mmio_read  = bus.read
        core.mmio_write = bus.write
    """

    def __init__(self, base: int = 0xFFFF_FF00_0000_0000):
        self.base = base
        self._devs: list[tuple[int, int, object]] = []

    def register(self, offset: int, size: int, dev: object):
        self._devs.append((offset, offset + size, dev))

    # -- byte-level access (called from core._r8 / _w8) ------------------
    def read(self, addr: int) -> int:
        off = addr - self.base
        for lo, hi, dev in self._devs:
            if lo <= off < hi:
                return dev.read8(off - lo) & MASK8
        return 0

    def write(self, addr: int, val: int):
        off = addr - self.base
        for lo, hi, dev in self._devs:
            if lo <= off < hi:
                dev.write8(off - lo, val & MASK8)
                return
