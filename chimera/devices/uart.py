"""UART peripheral — simple TX/RX byte FIFO.

Register map (byte offsets):
    +0  TX   (W)  — write a byte to transmit
    +1  RX   (R)  — read next received byte (0 if empty)
    +2  STAT (R)  — bit 0: TX ready, bit 1: RX data available
"""

from __future__ import annotations


class UART:
    def __init__(self):
        self.tx_buf = bytearray()
        self.rx_buf = bytearray()

    # -- device interface --------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0:
            return 0  # TX is write-only
        if off == 1:
            return self.rx_buf.pop(0) if self.rx_buf else 0
        if off == 2:
            s = 1  # TX always ready
            if self.rx_buf:
                s |= 2
            return s
        return 0

    def write8(self, off: int, val: int):
        if off == 0:
            self.tx_buf.append(val & 0xFF)

    # -- host helpers ------------------------------------------------------
    def push_rx(self, data: bytes | bytearray | int):
        """Push bytes into the RX buffer for the core to read."""
        if isinstance(data, int):
            self.rx_buf.append(data & 0xFF)
        else:
            self.rx_buf.extend(data)

    def drain_tx(self) -> bytes:
        """Read and clear all transmitted bytes."""
        out = bytes(self.tx_buf)
        self.tx_buf.clear()
        return out
