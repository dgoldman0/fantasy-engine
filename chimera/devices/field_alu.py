"""FieldALU — Multi-Prime Field Arithmetic + X25519 Coprocessor.

Supersedes the standalone X25519 device.  Mode 0 is backward-compatible
X25519 scalar multiplication (RFC 7748).  Modes 1-7 expose field
primitives and a raw 256x256->512-bit multiplier.

MMIO offset: +0x0840, size: 72 bytes (0x48)

Register map (byte offsets from device base):
  Write:
    0x00..0x1F  OPERAND_A  — 256-bit operand A / scalar (little-endian)
    0x20..0x3F  OPERAND_B  — 256-bit operand B / point  (little-endian)
    0x40        CMD        — bits [4:1] = mode, bit [0] = go
                             bits [7:6] = prime_sel
                             mode 0 = X25519 (legacy scalar multiply)
                             mode 1 = FADD  (a+b) mod p
                             mode 2 = FSUB  (a-b) mod p
                             mode 3 = FMUL  (a*b) mod p
                             mode 4 = FSQR  (a^2) mod p
                             mode 5 = FINV  a^(p-2) mod p
                             mode 6 = FPOW  a^b mod p
                             mode 7 = MUL_RAW  256x256->512-bit product
  Read:
    0x00        STATUS     — bit 0 = busy, bit 1 = done, bit 7 = present
    0x08..0x27  RESULT_LO  — 256-bit result (or low half for MUL_RAW)
    0x28..0x47  RESULT_HI  — 256-bit high half (MUL_RAW only, else 0)
"""
from __future__ import annotations

# Prime constant
_P_25519 = (1 << 255) - 19
_A24 = 121665  # (486662 - 2) / 4, per RFC 7748 section 5

# Mode constants (match MegaPad RTL mp64_field_alu.v)
MODE_X25519  = 0
MODE_FADD    = 1
MODE_FSUB    = 2
MODE_FMUL    = 3
MODE_FSQR    = 4
MODE_FINV    = 5
MODE_FPOW    = 6
MODE_MUL_RAW = 7


class FieldALU:
    """Multi-prime field ALU + X25519 scalar multiplier.

    Matches MegaPad FieldALUDevice (devices.py) and RTL (mp64_field_alu.v).
    X25519 (mode 0) always uses Curve25519 regardless of prime_sel.
    """

    def __init__(self):
        self.status: int = 0x80  # bit7 = present
        self._operand_a = bytearray(32)
        self._operand_b = bytearray(32)
        self._result_lo = bytearray(32)
        self._result_hi = bytearray(32)
        self._busy = False
        self._done = False
        self._prime_sel = 0  # 0=Curve25519 (only supported prime)
        self.ops_done: int = 0

    # -- helpers -----------------------------------------------------------

    def _get_a(self) -> int:
        return int.from_bytes(bytes(self._operand_a), 'little')

    def _get_b(self) -> int:
        return int.from_bytes(bytes(self._operand_b), 'little')

    def _set_result(self, lo: int, hi: int = 0):
        self._result_lo = bytearray(lo.to_bytes(32, 'little'))
        self._result_hi = bytearray(hi.to_bytes(32, 'little'))
        self._busy = False
        self._done = True

    # -- RFC 7748 X25519 (mode 0) -----------------------------------------

    @staticmethod
    def _clamp(k_bytes: bytearray) -> int:
        k = list(k_bytes)
        k[0] &= 248
        k[31] &= 127
        k[31] |= 64
        return int.from_bytes(bytes(k), 'little')

    @staticmethod
    def _decode_u(u_bytes: bytearray) -> int:
        return int.from_bytes(bytes(u_bytes), 'little') & ((1 << 255) - 1)

    @classmethod
    def _x25519(cls, k_int: int, u_int: int) -> int:
        p = _P_25519
        a24 = _A24
        x_1 = u_int
        x_2, z_2 = 1, 0
        x_3, z_3 = u_int, 1
        swap = 0
        for t in range(254, -1, -1):
            k_t = (k_int >> t) & 1
            swap ^= k_t
            if swap:
                x_2, x_3 = x_3, x_2
                z_2, z_3 = z_3, z_2
            swap = k_t
            A  = (x_2 + z_2) % p
            AA = (A * A) % p
            B  = (x_2 - z_2) % p
            BB = (B * B) % p
            E  = (AA - BB) % p
            C  = (x_3 + z_3) % p
            D  = (x_3 - z_3) % p
            DA = (D * A) % p
            CB = (C * B) % p
            x_3 = pow(DA + CB, 2, p)
            z_3 = (x_1 * pow(DA - CB, 2, p)) % p
            x_2 = (AA * BB) % p
            z_2 = (E * (AA + a24 * E)) % p
        if swap:
            x_2, x_3 = x_3, x_2
            z_2, z_3 = z_3, z_2
        return (x_2 * pow(z_2, p - 2, p)) % p

    # -- dispatch ----------------------------------------------------------

    def _execute(self, mode: int):
        p = _P_25519
        a = self._get_a()
        b = self._get_b()

        if mode == MODE_X25519:
            k = self._clamp(self._operand_a)
            u = self._decode_u(self._operand_b)
            r = self._x25519(k, u)
            self._set_result(r)
        elif mode == MODE_FADD:
            self._set_result((a + b) % p)
        elif mode == MODE_FSUB:
            self._set_result((a - b) % p)
        elif mode == MODE_FMUL:
            self._set_result((a * b) % p)
        elif mode == MODE_FSQR:
            self._set_result((a * a) % p)
        elif mode == MODE_FINV:
            self._set_result(pow(a, p - 2, p))
        elif mode == MODE_FPOW:
            self._set_result(pow(a, b, p))
        elif mode == MODE_MUL_RAW:
            wide = a * b
            lo = wide & ((1 << 256) - 1)
            hi = wide >> 256
            self._set_result(lo, hi)
        else:
            self._set_result(0)

        self.ops_done += 1

    # -- MMIO interface ----------------------------------------------------

    def read8(self, off: int) -> int:
        if off == 0x00:  # STATUS
            s = (int(self._done) << 1) | int(self._busy)
            s |= 0x80  # bit 7 = present
            return s
        if off == 0x01:  # STATUS alias (backward compat)
            return self.status
        if 0x08 <= off < 0x28:  # RESULT_LO (32 bytes)
            return self._result_lo[off - 0x08]
        if 0x28 <= off < 0x48:  # RESULT_HI (32 bytes)
            return self._result_hi[off - 0x28]
        return 0

    def write8(self, off: int, val: int):
        val &= 0xFF
        if 0x00 <= off < 0x20:  # OPERAND_A
            self._operand_a[off] = val
        elif 0x20 <= off < 0x40:  # OPERAND_B
            self._operand_b[off - 0x20] = val
        elif off == 0x40:  # CMD
            if (val & 1) and not self._busy:
                mode = (val >> 1) & 0xF
                self._busy = True
                self._done = False
                self._execute(mode)
            else:
                # No go bit — latch prime_sel from bits [7:6]
                self._prime_sel = (val >> 6) & 0x3
