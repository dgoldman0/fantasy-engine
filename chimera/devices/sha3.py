"""SHA-3 / SHAKE accelerator peripheral.

MMIO offset: +0x0880, size: 64 bytes

Register map (byte offsets from device base):
    +0x00      CMD       (W)  — 0x01 INIT, 0x02 UPDATE, 0x03 FINALIZE,
                                0x04 SQUEEZE (SHAKE mode)
    +0x01      STATUS    (R)  — bit0: busy, bit7: present
    +0x02      MODE      (RW) — 0=SHA3-256, 1=SHA3-512, 2=SHAKE128, 3=SHAKE256
    +0x03      reserved
    +0x04..07  MSG_LEN   (RW) — 32-bit message length in bytes (LE), for UPDATE
    +0x08..0F  reserved
    +0x10..1F  DIN       (W)  — 16-byte data-in window
    +0x20..3F  HASH      (R)  — 32-byte digest output (or first 32 bytes of XOF)
"""
from __future__ import annotations
import hashlib

_MODE_NAMES = {
    0: 'sha3_256',
    1: 'sha3_512',
    2: 'shake_128',
    3: 'shake_256',
}


class SHA3:
    """SHA-3 / SHAKE accelerator (functional model using hashlib)."""

    def __init__(self):
        self.mode: int = 0         # SHA3-256 default
        self.status: int = 0x80    # bit7 = present
        self.msg_len: int = 0
        self._hasher = hashlib.sha3_256()
        self.din = bytearray(16)
        self.hash_out = bytearray(32)
        self.bytes_hashed: int = 0

    def _new_hasher(self):
        name = _MODE_NAMES.get(self.mode, 'sha3_256')
        return hashlib.new(name)

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x01:
            return self.status
        if off == 0x02:
            return self.mode
        if 0x04 <= off < 0x08:
            return (self.msg_len >> (8 * (off - 0x04))) & 0xFF
        if 0x20 <= off < 0x40:
            idx = off - 0x20
            return self.hash_out[idx] if idx < len(self.hash_out) else 0
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:  # CMD
            if val == 0x01:    # INIT
                self._hasher = self._new_hasher()
                self.hash_out = bytearray(32)
                self.bytes_hashed = 0
            elif val == 0x02:  # UPDATE
                nbytes = min(self.msg_len, 16)
                self._hasher.update(bytes(self.din[:nbytes]))
                self.bytes_hashed += nbytes
            elif val == 0x03:  # FINALIZE
                dig = self._hasher.digest()
                self.hash_out = bytearray(dig[:32]).ljust(32, b'\x00')
            elif val == 0x04:  # SQUEEZE (SHAKE only)
                if self.mode in (2, 3):
                    dig = self._hasher.digest(32)
                    self.hash_out = bytearray(dig[:32]).ljust(32, b'\x00')
        elif off == 0x02:
            self.mode = val & 0x03
        elif 0x04 <= off < 0x08:
            sh = 8 * (off - 0x04)
            self.msg_len = (self.msg_len & ~(0xFF << sh)) | (val << sh)
            self.msg_len &= 0xFFFF_FFFF
        elif 0x10 <= off < 0x20:
            self.din[off - 0x10] = val
