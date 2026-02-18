"""Framebuffer — VDI display engine for Chimera-1.

Stub implementation: stores width/height/mode and framebuffer base address.
Pixel data lives in main memory (pointed to by FB_BASE), not in the device.

MMIO layout (64 bytes):
    +0x00   CMD         W   0x01=CLEAR 0x02=FLIP 0x03=SYNC 0xFF=RESET
    +0x01   STATUS      R   bit0:vsync bit7:present
    +0x02   WIDTH       RW  16-bit LE
    +0x04   HEIGHT      RW  16-bit LE
    +0x06   MODE        RW  0=RGB565 1=RGB888 2=RGBA8888
    +0x07   BPP         R   bytes per pixel (auto from mode)
    +0x08   FB_BASE     RW  64-bit LE framebuffer base address in memory
    +0x10   FB_SIZE     R   64-bit LE framebuffer size in bytes (w×h×bpp)
    +0x18   FRAME_NO    R   64-bit LE frame counter
"""
from __future__ import annotations
from typing import Callable, Optional


class Framebuffer:
    """Stub VDI display engine."""

    SIZE = 0x40  # 64 bytes

    _BPP = {0: 2, 1: 3, 2: 4}  # mode → bytes per pixel

    def __init__(self, width: int = 320, height: int = 240, mode: int = 0):
        self.width = width
        self.height = height
        self.mode = mode
        self.fb_base: int = 0
        self.frame_count: int = 0
        self.vsync: bool = False

    @property
    def bpp(self) -> int:
        return self._BPP.get(self.mode, 2)

    @property
    def fb_size(self) -> int:
        return self.width * self.height * self.bpp

    def _execute_cmd(self, cmd: int):
        if cmd == 0x01:  # CLEAR
            pass  # would zero FB memory — no-op in stub
        elif cmd == 0x02:  # FLIP
            self.frame_count += 1
            self.vsync = True
        elif cmd == 0x03:  # SYNC
            self.vsync = False
        elif cmd == 0xFF:  # RESET
            self.frame_count = 0
            self.vsync = False

    # -- MMIO interface ---------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x00:
            return 0  # CMD write-only
        if off == 0x01:
            st = 0x80  # present
            if self.vsync:
                st |= 0x01
            return st
        if off == 0x02: return self.width & 0xFF
        if off == 0x03: return (self.width >> 8) & 0xFF
        if off == 0x04: return self.height & 0xFF
        if off == 0x05: return (self.height >> 8) & 0xFF
        if off == 0x06: return self.mode
        if off == 0x07: return self.bpp
        if 0x08 <= off < 0x10:
            return (self.fb_base >> ((off - 0x08) * 8)) & 0xFF
        if 0x10 <= off < 0x18:
            return (self.fb_size >> ((off - 0x10) * 8)) & 0xFF
        if 0x18 <= off < 0x20:
            return (self.frame_count >> ((off - 0x18) * 8)) & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:
            self._execute_cmd(val)
        elif off == 0x02:
            self.width = (self.width & 0xFF00) | val
        elif off == 0x03:
            self.width = (self.width & 0x00FF) | (val << 8)
        elif off == 0x04:
            self.height = (self.height & 0xFF00) | val
        elif off == 0x05:
            self.height = (self.height & 0x00FF) | (val << 8)
        elif off == 0x06:
            self.mode = val
        elif 0x08 <= off < 0x10:
            shift = (off - 0x08) * 8
            mask = 0xFF << shift
            self.fb_base = (self.fb_base & ~mask) | (val << shift)
