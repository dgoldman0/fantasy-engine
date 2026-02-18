"""Mailbox peripheral — inter-core message passing.

Register map (byte offsets):
    +0..7   DATA    (RW) — 64-bit message data (LE)
    +8      SEND    (W)  — write non-zero to send DATA
    +9      STATUS  (R)  — bit 0: message pending
    +0xA    ACK     (W)  — write non-zero to acknowledge / clear
"""

from __future__ import annotations
from collections import deque

MASK64 = 0xFFFF_FFFF_FFFF_FFFF


class Mailbox:
    def __init__(self, depth: int = 16):
        self.data: int = 0          # staging register
        self.inbox: deque[int] = deque(maxlen=depth)

    # -- device interface --------------------------------------------------
    def read8(self, off: int) -> int:
        if off < 8:
            # reading DATA returns head of inbox, or staging reg if empty
            val = self.inbox[0] if self.inbox else self.data
            return (val >> (8 * off)) & 0xFF
        if off == 9:
            return 1 if self.inbox else 0
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off < 8:
            sh = 8 * off
            self.data = (self.data & ~(0xFF << sh) & MASK64) | (val << sh)
        elif off == 8 and val:  # SEND
            self.inbox.append(self.data)
        elif off == 0xA and val:  # ACK
            if self.inbox:
                self.inbox.popleft()

    # -- host helpers ------------------------------------------------------
    def post(self, msg: int):
        """Deliver a message from another core."""
        self.inbox.append(msg & MASK64)

    def pending(self) -> bool:
        return bool(self.inbox)
