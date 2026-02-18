"""Timer peripheral — 32-bit countdown with auto-reload.

Register map (byte offsets):
    +0..3   COUNT   (RW) — 32-bit countdown (LE)
    +4..7   RELOAD  (RW) — 32-bit reload value (LE)
    +8      CTRL    (RW) — bit 0: enable, bit 1: auto-reload,
                           bit 2: IRQ pending (write-1-to-clear)
"""

from __future__ import annotations

MASK32 = 0xFFFF_FFFF


class Timer:
    def __init__(self):
        self.count: int = 0
        self.reload: int = 0
        self.ctrl: int = 0  # bits: [irq_pend:2 | auto:1 | enable:0]

    # -- device interface --------------------------------------------------
    def read8(self, off: int) -> int:
        if off < 4:
            return (self.count >> (8 * off)) & 0xFF
        if off < 8:
            return (self.reload >> (8 * (off - 4))) & 0xFF
        if off == 8:
            return self.ctrl & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off < 4:
            sh = 8 * off
            self.count = (self.count & ~(0xFF << sh) & MASK32) | (val << sh)
        elif off < 8:
            sh = 8 * (off - 4)
            self.reload = (self.reload & ~(0xFF << sh) & MASK32) | (val << sh)
        elif off == 8:
            if val & 4:        # write-1-to-clear IRQ pending
                self.ctrl &= ~4
            self.ctrl = (self.ctrl & 4) | (val & 3)

    # -- simulation --------------------------------------------------------
    def tick(self, cycles: int = 1) -> bool:
        """Advance the timer.  Returns True if it fired."""
        if not (self.ctrl & 1):
            return False
        self.count = (self.count - cycles) & MASK32
        if self.count == 0 or self.count > 0x8000_0000:
            self.ctrl |= 4  # IRQ pending
            if self.ctrl & 2:
                self.count = self.reload
            else:
                self.ctrl &= ~1
                self.count = 0
            return True
        return False
