"""X25519 Diffie-Hellman key exchange accelerator.

MMIO offset: +0x0840, size: 128 bytes

Register map (byte offsets from device base):
    +0x00      CMD       (W)  — 0x01 COMPUTE (scalar multiply), 0x03 RESET
    +0x01      STATUS    (R)  — bit0: busy, bit7: present
    +0x02..03  reserved
    +0x04..23  SCALAR    (RW) — 32-byte private scalar (LE)
    +0x24..43  POINT     (RW) — 32-byte public point (LE)
    +0x44..63  RESULT    (R)  — 32-byte shared secret (LE)
"""
from __future__ import annotations
import hashlib

MASK64 = 0xFFFF_FFFF_FFFF_FFFF

# Try X25519 from cryptography package, else use HMAC-based stub
try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey,
    )
    _HAS_X25519 = True
except ImportError:
    _HAS_X25519 = False


class X25519:
    """X25519 scalar multiplication accelerator."""

    def __init__(self):
        self.scalar = bytearray(32)
        self.point = bytearray(32)
        self.result = bytearray(32)
        self.status: int = 0x80  # bit7 = present
        self.ops_done: int = 0

    def _compute(self):
        """Perform X25519(scalar, point) → result."""
        if _HAS_X25519:
            try:
                priv = X25519PrivateKey.from_private_bytes(bytes(self.scalar))
                pub = X25519PublicKey.from_public_bytes(bytes(self.point))
                shared = priv.exchange(pub)
                self.result[:] = shared[:32]
            except Exception:
                # Invalid key material — produce deterministic fallback
                h = hashlib.sha256(bytes(self.scalar) + bytes(self.point)).digest()
                self.result[:] = h[:32]
        else:
            # Stub: SHA-256(scalar || point)
            h = hashlib.sha256(bytes(self.scalar) + bytes(self.point)).digest()
            self.result[:] = h[:32]
        self.ops_done += 1

    # -- MMIO interface ----------------------------------------------------
    def read8(self, off: int) -> int:
        if off == 0x01:
            return self.status
        if 0x44 <= off < 0x64:
            return self.result[off - 0x44]
        if 0x04 <= off < 0x24:
            return self.scalar[off - 0x04]
        if 0x24 <= off < 0x44:
            return self.point[off - 0x24]
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if off == 0x00:  # CMD
            if val == 0x01:
                self._compute()
            elif val == 0x03:
                self.__init__()
        elif 0x04 <= off < 0x24:
            self.scalar[off - 0x04] = val
        elif 0x24 <= off < 0x44:
            self.point[off - 0x24] = val
