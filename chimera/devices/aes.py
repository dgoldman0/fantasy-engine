"""AES-256-GCM accelerator peripheral.

MMIO offset: +0x0800, size: 128 bytes

Register map (byte offsets from device base):
    +0x00..1F  KEY       (W)  — 256-bit key (32 bytes, LE)
    +0x20..2B  IV        (RW) — 96-bit IV / nonce (12 bytes, LE)
    +0x2C      CMD       (W)  — 0x01 ENCRYPT, 0x02 DECRYPT, 0x03 RESET,
                                0x04 AAD (additional authenticated data)
    +0x2D      STATUS    (R)  — bit0: busy, bit7: present
    +0x2E..2F  reserved
    +0x30..3F  DIN       (W)  — 16-byte plaintext / ciphertext input block
    +0x40..4F  DOUT      (R)  — 16-byte output block
    +0x50..5F  TAG       (R)  — 16-byte GCM authentication tag
    +0x60..67  LEN_A     (RW) — 64-bit AAD length in bits (LE)
    +0x68..6F  LEN_C     (RW) — 64-bit ciphertext length in bits (LE)
"""
from __future__ import annotations
import hashlib
import struct

MASK64 = 0xFFFF_FFFF_FFFF_FFFF

# Try to use PyCryptodome for real AES, fall back to stub
try:
    from Crypto.Cipher import AES as _AES
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


class AES:
    """AES-256-GCM accelerator (functional model).

    If PyCryptodome is available, uses real AES-256-GCM.
    Otherwise, uses a simple XOR-based stub for functional testing.
    """

    def __init__(self):
        self.key = bytearray(32)
        self.iv = bytearray(12)
        self.din = bytearray(16)
        self.dout = bytearray(16)
        self.tag = bytearray(16)
        self.len_a: int = 0
        self.len_c: int = 0
        self.status: int = 0x80  # bit7 = present
        self.blocks_processed: int = 0
        # Internal state for stream cipher mode
        self._keystream_ctr: int = 0

    def _process_block(self, encrypt: bool):
        """Process one 16-byte block."""
        if _HAS_CRYPTO:
            try:
                nonce = bytes(self.iv)
                cipher = _AES.new(bytes(self.key), _AES.MODE_GCM, nonce=nonce)
                if encrypt:
                    ct, tag = cipher.encrypt_and_digest(bytes(self.din))
                    self.dout[:] = ct[:16]
                    self.tag[:] = tag[:16]
                else:
                    pt = cipher.decrypt(bytes(self.din))
                    self.dout[:] = pt[:16]
            except Exception:
                self.status |= 0x40  # error flag
                self.dout[:] = b'\x00' * 16
        else:
            # Stub: XOR with SHA-256 of key+iv+counter for deterministic output
            h = hashlib.sha256(bytes(self.key) + bytes(self.iv) +
                               self._keystream_ctr.to_bytes(8, 'little')).digest()
            for i in range(16):
                self.dout[i] = self.din[i] ^ h[i]
            # Stub tag: SHA-256 of key + iv + block
            th = hashlib.sha256(bytes(self.key) + bytes(self.iv) +
                                bytes(self.dout)).digest()
            self.tag[:] = th[:16]
        self._keystream_ctr += 1
        self.blocks_processed += 1

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if 0x20 <= off < 0x2C:
            return self.iv[off - 0x20]
        if off == 0x2D:
            return self.status
        if 0x40 <= off < 0x50:
            return self.dout[off - 0x40]
        if 0x50 <= off < 0x60:
            return self.tag[off - 0x50]
        if 0x60 <= off < 0x68:
            return (self.len_a >> (8 * (off - 0x60))) & 0xFF
        if 0x68 <= off < 0x70:
            return (self.len_c >> (8 * (off - 0x68))) & 0xFF
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if 0x00 <= off < 0x20:
            self.key[off] = val
        elif 0x20 <= off < 0x2C:
            self.iv[off - 0x20] = val
        elif off == 0x2C:  # CMD
            if val == 0x01:    # ENCRYPT
                self._process_block(encrypt=True)
            elif val == 0x02:  # DECRYPT
                self._process_block(encrypt=False)
            elif val == 0x03:  # RESET
                self.__init__()
        elif 0x30 <= off < 0x40:
            self.din[off - 0x30] = val
        elif 0x60 <= off < 0x68:
            sh = 8 * (off - 0x60)
            self.len_a = (self.len_a & ~(0xFF << sh) & MASK64) | (val << sh)
        elif 0x68 <= off < 0x70:
            sh = 8 * (off - 0x68)
            self.len_c = (self.len_c & ~(0xFF << sh) & MASK64) | (val << sh)
