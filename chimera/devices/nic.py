"""NIC — Network Interface Controller for Chimera-1.

MegaPad-style CMD/STATUS register interface with DMA TX/RX and
a pluggable backend architecture (Loopback, UDP, TAP).

MMIO layout (128 bytes):
    +0x00   CMD         W   0x01=SEND 0x02=RECV 0x03=STATUS 0x04=RESET
    +0x01   STATUS      R   bit0:tx_busy bit1:rx_avail bit2:link_up bit3:error bit7:present
    +0x02   DMA_ADDR    RW  64-bit LE DMA address (8 bytes)
    +0x0A   FRAME_LEN   RW  16-bit LE frame length
    +0x0C   IRQ_CTRL    RW  bit0:rx_irq_en bit1:tx_irq_en
    +0x0D   IRQ_STATUS  RW  W1C bit0:rx_pending bit1:tx_pending
    +0x0E   MAC_ADDR    R   6 bytes
    +0x14   TX_COUNT    R   16-bit LE
    +0x16   RX_COUNT    R   16-bit LE
    +0x20   DATA        RW  byte-at-a-time port (96 bytes, offset 0x20..0x7F)
"""
from __future__ import annotations

import abc
import struct
import collections
from typing import Callable, Optional


# ═════════════════════════════════════════════════════════════════════
#  Backend Architecture
# ═════════════════════════════════════════════════════════════════════

class NICBackend(abc.ABC):
    """Abstract NIC backend — pluggable transport."""

    def __init__(self):
        self.on_rx_frame: Optional[Callable[[bytes], None]] = None

    @abc.abstractmethod
    def send(self, frame: bytes) -> bool:
        """Transmit a frame.  Returns True on success."""

    @abc.abstractmethod
    def start(self) -> None: ...

    @abc.abstractmethod
    def stop(self) -> None: ...

    @property
    @abc.abstractmethod
    def link_up(self) -> bool: ...

    @property
    def name(self) -> str:
        return type(self).__name__


class LoopbackBackend(NICBackend):
    """Loopback backend — frames are silently accepted.  For unit tests."""

    def __init__(self, *, echo: bool = False):
        super().__init__()
        self._echo = echo

    def send(self, frame: bytes) -> bool:
        if self._echo and self.on_rx_frame:
            self.on_rx_frame(frame)
        return True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    @property
    def link_up(self) -> bool:
        return True


class UDPBackend(NICBackend):
    """UDP socket backend — for multi-instance networking.

    Sends datagrams to (peer_host, peer_port), receives on bind_port.
    Background RX thread requires explicit start()/stop().
    """

    def __init__(self, bind_port: int = 9000,
                 peer_host: str = "127.0.0.1", peer_port: int = 9001):
        super().__init__()
        self.bind_port = bind_port
        self.peer_host = peer_host
        self.peer_port = peer_port
        self._sock = None
        self._running = False
        self._rx_thread = None

    def send(self, frame: bytes) -> bool:
        if not self._sock:
            return False
        try:
            self._sock.sendto(frame, (self.peer_host, self.peer_port))
            return True
        except OSError:
            return False

    def start(self) -> None:
        import socket
        import threading
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", self.bind_port))
        self._sock.settimeout(0.1)
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
        if self._sock:
            self._sock.close()
            self._sock = None

    def _rx_loop(self):
        while self._running:
            try:
                data, _ = self._sock.recvfrom(2048)
                if data and self.on_rx_frame:
                    self.on_rx_frame(data)
            except OSError:
                pass

    @property
    def link_up(self) -> bool:
        return self._sock is not None and self._running


class TAPBackend(NICBackend):
    """Linux TAP backend — real L2 networking via /dev/net/tun.

    Requires root or CAP_NET_ADMIN.
    """

    def __init__(self, tap_name: str = "chimera0"):
        super().__init__()
        self.tap_name = tap_name
        self._fd = -1
        self._running = False
        self._rx_thread = None

    def send(self, frame: bytes) -> bool:
        if self._fd < 0:
            return False
        import os as _os
        try:
            _os.write(self._fd, frame)
            return True
        except OSError:
            return False

    def start(self) -> None:
        self._fd = self._open_tap()
        if self._fd < 0:
            return
        import threading
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
        if self._fd >= 0:
            import os as _os
            _os.close(self._fd)
            self._fd = -1

    def _open_tap(self) -> int:
        import os as _os
        import fcntl
        TUNSETIFF = 0x400454CA
        IFF_TAP = 0x0002
        IFF_NO_PI = 0x1000
        try:
            fd = _os.open("/dev/net/tun", _os.O_RDWR)
            ifr = struct.pack("16sH14s", self.tap_name.encode(),
                              IFF_TAP | IFF_NO_PI, b"\x00" * 14)
            fcntl.ioctl(fd, TUNSETIFF, ifr)
            return fd
        except OSError:
            return -1

    def _rx_loop(self):
        import os as _os
        import select
        while self._running:
            r, _, _ = select.select([self._fd], [], [], 0.1)
            if r:
                try:
                    data = _os.read(self._fd, 2048)
                    if data and self.on_rx_frame:
                        self.on_rx_frame(data)
                except OSError:
                    pass

    @property
    def link_up(self) -> bool:
        return self._fd >= 0 and self._running


# ═════════════════════════════════════════════════════════════════════
#  NIC Device
# ═════════════════════════════════════════════════════════════════════

class NIC:
    """Network Interface Controller with DMA and pluggable backend."""

    SIZE = 0x80  # 128 bytes
    MAX_FRAME = 1518

    # Commands
    CMD_SEND   = 0x01
    CMD_RECV   = 0x02
    CMD_STATUS = 0x03
    CMD_RESET  = 0x04

    def __init__(self, backend: Optional[NICBackend] = None,
                 mac: bytes = b"\x02\x43\x48\x31\x00\x01"):
        if len(mac) != 6:
            mac = b"\x02\x43\x48\x31\x00\x01"
        self.mac = bytearray(mac)
        self.dma_addr: int = 0
        self.frame_len: int = 0
        self.irq_ctrl: int = 0
        self.irq_status: int = 0
        self.tx_count: int = 0
        self.rx_count: int = 0
        self.error: bool = False

        self._data_buf = bytearray(96)
        self._data_pos = 0
        self.tx_queue: collections.deque[bytes] = collections.deque(maxlen=64)
        self.rx_queue: collections.deque[bytes] = collections.deque(maxlen=64)

        # DMA callbacks (set by SoC wiring)
        self._mem_read: Optional[Callable[[int], int]] = None
        self._mem_write: Optional[Callable[[int, int], None]] = None

        # Backend
        self._backend = backend or LoopbackBackend()
        self._backend.on_rx_frame = self._backend_rx
        self._backend.start()

    def shutdown(self):
        """Stop backend."""
        self._backend.stop()

    # -- backend callback -------------------------------------------------
    def _backend_rx(self, frame: bytes):
        """Called by backend when a frame arrives."""
        self.rx_queue.append(frame)
        if self.irq_ctrl & 0x01:  # RX IRQ enabled
            self.irq_status |= 0x01

    # -- command dispatch -------------------------------------------------
    def _execute_cmd(self, cmd: int):
        if cmd == self.CMD_SEND:
            frame = self._read_tx_frame()
            if frame:
                self.tx_queue.append(frame)
                self._backend.send(frame)
                self.tx_count = (self.tx_count + 1) & 0xFFFF
                if self.irq_ctrl & 0x02:
                    self.irq_status |= 0x02

        elif cmd == self.CMD_RECV:
            if self.rx_queue:
                frame = self.rx_queue.popleft()
                self.frame_len = len(frame)
                self._write_rx_frame(frame)
                self.rx_count = (self.rx_count + 1) & 0xFFFF
            else:
                self.frame_len = 0

        elif cmd == self.CMD_RESET:
            self.tx_queue.clear()
            self.rx_queue.clear()
            self.tx_count = 0
            self.rx_count = 0
            self.frame_len = 0
            self.irq_status = 0
            self.error = False
            self._data_buf = bytearray(96)
            self._data_pos = 0

    def _read_tx_frame(self) -> bytes | None:
        """Read frame from DMA or data buffer."""
        nbytes = self.frame_len
        if nbytes <= 0 or nbytes > self.MAX_FRAME:
            self.error = True
            return None
        if self._mem_read and self.dma_addr:
            data = bytearray()
            for i in range(nbytes):
                data.append(self._mem_read(self.dma_addr + i))
            return bytes(data)
        return bytes(self._data_buf[:nbytes])

    def _write_rx_frame(self, frame: bytes):
        """Write received frame to DMA and data buffer."""
        if self._mem_write and self.dma_addr:
            for i, b in enumerate(frame):
                self._mem_write(self.dma_addr + i, b)
        self._data_buf = bytearray(96)
        self._data_buf[:min(len(frame), 96)] = frame[:96]
        self._data_pos = 0

    # -- MMIO interface ---------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x00:
            return 0  # CMD is write-only
        if off == 0x01:
            st = 0x80  # present
            if self.rx_queue:
                st |= 0x02  # rx_avail
            if self._backend.link_up:
                st |= 0x04  # link_up
            if self.error:
                st |= 0x08
            return st
        if 0x02 <= off < 0x0A:
            return (self.dma_addr >> ((off - 0x02) * 8)) & 0xFF
        if off == 0x0A:
            return self.frame_len & 0xFF
        if off == 0x0B:
            return (self.frame_len >> 8) & 0xFF
        if off == 0x0C:
            return self.irq_ctrl
        if off == 0x0D:
            return self.irq_status
        if 0x0E <= off < 0x14:
            return self.mac[off - 0x0E]
        if off == 0x14:
            return self.tx_count & 0xFF
        if off == 0x15:
            return (self.tx_count >> 8) & 0xFF
        if off == 0x16:
            return self.rx_count & 0xFF
        if off == 0x17:
            return (self.rx_count >> 8) & 0xFF
        if 0x20 <= off < 0x80:
            idx = off - 0x20
            if idx < len(self._data_buf):
                return self._data_buf[idx]
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:
            self._execute_cmd(val)
        elif 0x02 <= off < 0x0A:
            shift = (off - 0x02) * 8
            mask = 0xFF << shift
            self.dma_addr = (self.dma_addr & ~mask) | (val << shift)
        elif off == 0x0A:
            self.frame_len = (self.frame_len & 0xFF00) | val
        elif off == 0x0B:
            self.frame_len = (self.frame_len & 0x00FF) | (val << 8)
        elif off == 0x0C:
            self.irq_ctrl = val
        elif off == 0x0D:
            self.irq_status &= ~val  # W1C
        elif 0x20 <= off < 0x80:
            idx = off - 0x20
            if idx < len(self._data_buf):
                self._data_buf[idx] = val
