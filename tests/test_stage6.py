"""Stage 6: Crypto accelerator tests.

Tests for CRC, AES, SHA3, TRNG, NTT, KEM, FieldALU (incl. X25519 mode) devices.
"""
from __future__ import annotations
import struct, zlib, hashlib, os
import pytest

from chimera.devices.crc import CRC
from chimera.devices.aes import AES
from chimera.devices.sha3 import SHA3
from chimera.devices.trng import TRNG
from chimera.devices.ntt import NTT
from chimera.devices.kem import KEM
from chimera.devices.field_alu import FieldALU
from chimera.devices.bus import DeviceBus

# ═════════════════════════════════════════════════════════════════════
#  CRC
# ═════════════════════════════════════════════════════════════════════

class TestCRC:
    def test_crc32_known_vector(self):
        """CRC-32 of b'123456789' should match standard IEEE CRC-32."""
        crc = CRC()
        crc.reset()
        data = b"123456789"
        for b in data:
            crc.write8(0x10, b)
        # Final CRC (inverted for IEEE)
        result = crc.crc ^ 0xFFFF_FFFF
        expected = zlib.crc32(data) & 0xFFFF_FFFF
        assert result == expected

    def test_read_result(self):
        """Result readable byte-by-byte via MMIO."""
        crc = CRC()
        crc.crc = 0xDEADBEEF
        b0 = crc.read8(0x18)
        b1 = crc.read8(0x19)
        b2 = crc.read8(0x1A)
        b3 = crc.read8(0x1B)
        assert struct.pack("BBBB", b0, b1, b2, b3) == struct.pack("<I", 0xDEADBEEF)

    def test_poly_readback(self):
        """Polynomial writable and readable."""
        crc = CRC()
        # Write a custom polynomial byte-by-byte
        crc.write8(0x00, 0x07)
        crc.write8(0x01, 0x00)
        crc.write8(0x02, 0x00)
        crc.write8(0x03, 0x00)
        assert crc.poly == 0x07

    def test_init_resets_crc(self):
        """Writing INIT register resets running CRC."""
        crc = CRC()
        crc.write8(0x10, 0xAA)  # process a byte
        old = crc.crc
        # Write INIT = 0
        for i in range(8):
            crc.write8(0x08 + i, 0x00)
        assert crc.crc == 0  # reset to new INIT

    def test_on_bus(self):
        """CRC device accessible through DeviceBus."""
        crc = CRC()
        bus = DeviceBus()
        bus.register(0x07C0, 0x20, crc)
        base = bus.base + 0x07C0
        bus.write(base + 0x10, ord('A'))
        assert crc.bytes_processed == 1


# ═════════════════════════════════════════════════════════════════════
#  AES
# ═════════════════════════════════════════════════════════════════════

class TestAES:
    def test_present_bit(self):
        """STATUS bit7 = present."""
        aes = AES()
        assert aes.read8(0x2D) & 0x80

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt recovers plaintext."""
        aes = AES()
        # Set key (32 bytes)
        for i in range(32):
            aes.write8(i, i)
        # Set IV (12 bytes)
        for i in range(12):
            aes.write8(0x20 + i, 0x10 + i)
        # Set plaintext
        for i in range(16):
            aes.write8(0x30 + i, 0x41 + i)  # 'A', 'B', ...
        plaintext = bytes(aes.din)

        # Encrypt
        aes.write8(0x2C, 0x01)
        ciphertext = bytes(aes.dout)
        assert ciphertext != plaintext

        # Reset to same key/IV, load ciphertext, decrypt
        aes2 = AES()
        for i in range(32):
            aes2.write8(i, i)
        for i in range(12):
            aes2.write8(0x20 + i, 0x10 + i)
        for i in range(16):
            aes2.write8(0x30 + i, ciphertext[i])
        aes2.write8(0x2C, 0x02)  # DECRYPT
        recovered = bytes(aes2.dout)
        assert recovered == plaintext

    def test_tag_produced(self):
        """GCM tag is produced on encrypt."""
        aes = AES()
        for i in range(32):
            aes.write8(i, i)
        for i in range(12):
            aes.write8(0x20 + i, i)
        for i in range(16):
            aes.write8(0x30 + i, 0xCC)
        aes.write8(0x2C, 0x01)
        tag = bytes(aes.read8(0x50 + i) for i in range(16))
        assert tag != bytes(16)  # not all zeros

    def test_reset(self):
        """CMD=0x03 resets state."""
        aes = AES()
        aes.write8(0x00, 0xAA)  # key[0]
        aes.write8(0x2C, 0x03)  # RESET
        assert aes.key[0] == 0


# ═════════════════════════════════════════════════════════════════════
#  SHA3
# ═════════════════════════════════════════════════════════════════════

class TestSHA3:
    def test_sha3_256_empty(self):
        """SHA3-256 of empty message matches hashlib."""
        sha = SHA3()
        sha.write8(0x00, 0x01)  # INIT
        sha.write8(0x00, 0x03)  # FINALIZE
        result = bytes(sha.read8(0x20 + i) for i in range(32))
        expected = hashlib.sha3_256(b"").digest()
        assert result == expected

    def test_sha3_256_hello(self):
        """SHA3-256 of 'hello' matches hashlib."""
        sha = SHA3()
        sha.write8(0x00, 0x01)  # INIT
        # Load 'hello' into DIN
        for i, c in enumerate(b"hello"):
            sha.write8(0x10 + i, c)
        # Set MSG_LEN = 5
        sha.write8(0x04, 5)
        sha.write8(0x00, 0x02)  # UPDATE
        sha.write8(0x00, 0x03)  # FINALIZE
        result = bytes(sha.read8(0x20 + i) for i in range(32))
        expected = hashlib.sha3_256(b"hello").digest()
        assert result == expected

    def test_present_bit(self):
        sha = SHA3()
        assert sha.read8(0x01) & 0x80

    def test_mode_switch(self):
        """Mode register writable and readable."""
        sha = SHA3()
        sha.write8(0x02, 0x01)  # SHA3-512
        assert sha.read8(0x02) == 0x01


# ═════════════════════════════════════════════════════════════════════
#  TRNG
# ═════════════════════════════════════════════════════════════════════

class TestTRNG:
    def test_present_and_ready(self):
        """STATUS shows present and entropy ready."""
        trng = TRNG()
        st = trng.read8(0x01)
        assert st & 0x80  # present
        assert st & 0x02  # entropy ready

    def test_output_nonzero(self):
        """Output register should have random data (very unlikely all zero)."""
        trng = TRNG()
        out = bytes(trng.read8(0x04 + i) for i in range(32))
        assert out != bytes(32)

    def test_generate_changes_output(self):
        """CMD=GENERATE produces new random values."""
        trng = TRNG()
        out1 = bytes(trng.read8(0x04 + i) for i in range(32))
        trng.write8(0x00, 0x01)  # GENERATE
        out2 = bytes(trng.read8(0x04 + i) for i in range(32))
        # With 256 bits of randomness, collision probability ≈ 0
        assert out1 != out2

    def test_words_generated_counter(self):
        """Counter increments on GENERATE."""
        trng = TRNG()
        assert trng.words_generated == 4  # from __init__
        trng.write8(0x00, 0x01)
        assert trng.words_generated == 8


# ═════════════════════════════════════════════════════════════════════
#  FieldALU — X25519 mode (mode 0, backward-compatible)
# ═════════════════════════════════════════════════════════════════════

class TestFieldALU_X25519:
    """X25519 scalar multiplication via FieldALU mode 0."""

    def _write_scalar(self, fa, data: bytes):
        for i, b in enumerate(data):
            fa.write8(0x00 + i, b)  # OPERAND_A

    def _write_point(self, fa, data: bytes):
        for i, b in enumerate(data):
            fa.write8(0x20 + i, b)  # OPERAND_B

    def _go(self, fa, mode=0):
        cmd = ((mode & 0xF) << 1) | 1  # go bit
        fa.write8(0x40, cmd)

    def _read_result(self, fa) -> bytes:
        return bytes(fa.read8(0x08 + i) for i in range(32))

    def test_present_bit(self):
        fa = FieldALU()
        assert fa.read8(0x00) & 0x80  # present in STATUS

    def test_operand_a_writable(self):
        """Operand A (scalar) writable."""
        fa = FieldALU()
        for i in range(32):
            fa.write8(0x00 + i, i + 1)
        for i in range(32):
            assert fa._operand_a[i] == i + 1

    def test_x25519_produces_result(self):
        """Mode 0 (X25519) produces a non-zero result."""
        fa = FieldALU()
        self._write_scalar(fa, bytes([0xAA] * 32))
        self._write_point(fa, bytes([0xBB] * 32))
        self._go(fa, mode=0)
        result = self._read_result(fa)
        assert result != bytes(32)
        assert fa.ops_done == 1

    def test_x25519_deterministic(self):
        """Same inputs produce same output."""
        results = []
        for _ in range(2):
            fa = FieldALU()
            self._write_scalar(fa, bytes([0x42] * 32))
            self._write_point(fa, bytes([0x43] * 32))
            self._go(fa, mode=0)
            results.append(self._read_result(fa))
        assert results[0] == results[1]

    def test_x25519_rfc7748_basepoint(self):
        """X25519 with basepoint u=9 matches RFC 7748 test vector."""
        fa = FieldALU()
        # Scalar from RFC 7748 §6.1 (Alice's private key)
        scalar = bytes.fromhex(
            "77076d0a7318a57d3c16c17251b26645"
            "df4c2f87ebc0992ab177fba51db92c2a"
        )
        # Basepoint u = 9
        point = b'\x09' + b'\x00' * 31
        self._write_scalar(fa, scalar)
        self._write_point(fa, point)
        self._go(fa, mode=0)
        result = self._read_result(fa)
        expected = bytes.fromhex(
            "8520f0098930a754748b7ddcb43ef75a"
            "0dbf3a0d26381af4eba4a98eaa9b4e6a"
        )
        assert result == expected


# ═════════════════════════════════════════════════════════════════════
#  NTT
# ═════════════════════════════════════════════════════════════════════

class TestNTT:
    def test_present_bit(self):
        assert NTT().read8(0x01) & 0x80

    def test_default_params(self):
        """Default polynomial length and modulus match Kyber."""
        ntt = NTT()
        poly_len = ntt.read8(0x14) | (ntt.read8(0x15) << 8)
        modulus = ntt.read8(0x16) | (ntt.read8(0x17) << 8)
        assert poly_len == 256
        assert modulus == 3329

    def test_dma_addr_readback(self):
        """DMA addresses writable and readable."""
        ntt = NTT()
        for i in range(8):
            ntt.write8(0x04 + i, 0x10 + i)
        for i in range(8):
            assert ntt.read8(0x04 + i) == 0x10 + i

    def test_cmd_counts_ops(self):
        """Non-RESET commands increment ops counter."""
        ntt = NTT()
        ntt.write8(0x00, 0x01)  # FWD_NTT
        ntt.write8(0x00, 0x02)  # INV_NTT
        assert ntt.ops_done == 2


# ═════════════════════════════════════════════════════════════════════
#  KEM
# ═════════════════════════════════════════════════════════════════════

class TestKEM:
    def test_present_bit(self):
        assert KEM().read8(0x01) & 0x80

    def test_variant_readback(self):
        """Variant register writable."""
        kem = KEM()
        kem.write8(0x02, 0x02)  # Kyber1024
        assert kem.read8(0x02) == 0x02

    def test_cmd_counts_ops(self):
        kem = KEM()
        kem.write8(0x00, 0x01)  # KEYGEN
        kem.write8(0x00, 0x02)  # ENCAPS
        kem.write8(0x00, 0x03)  # DECAPS
        b0 = kem.read8(0x24)
        b1 = kem.read8(0x25)
        op_count = b0 | (b1 << 8)
        assert op_count == 3

    def test_reset(self):
        kem = KEM()
        kem.write8(0x00, 0x01)
        kem.write8(0x00, 0xFF)  # RESET
        assert kem.op_count == 0


# ═════════════════════════════════════════════════════════════════════
#  FieldALU — arithmetic modes
# ═════════════════════════════════════════════════════════════════════

class TestFieldALU:
    def _set_a(self, fa, val: int):
        bs = val.to_bytes(32, 'little')
        for i, b in enumerate(bs):
            fa.write8(0x00 + i, b)

    def _set_b(self, fa, val: int):
        bs = val.to_bytes(32, 'little')
        for i, b in enumerate(bs):
            fa.write8(0x20 + i, b)

    def _go(self, fa, mode: int):
        fa.write8(0x40, ((mode & 0xF) << 1) | 1)

    def _result_lo(self, fa) -> int:
        return int.from_bytes(bytes(fa.read8(0x08 + i) for i in range(32)), 'little')

    def _result_hi(self, fa) -> int:
        return int.from_bytes(bytes(fa.read8(0x28 + i) for i in range(32)), 'little')

    def test_present_bit(self):
        assert FieldALU().read8(0x00) & 0x80

    def test_fadd(self):
        """Mode 1: field addition mod p25519."""
        fa = FieldALU()
        p = (1 << 255) - 19
        self._set_a(fa, p - 5)
        self._set_b(fa, 10)
        self._go(fa, 1)  # FADD
        assert self._result_lo(fa) == 5  # (p-5+10) mod p == 5

    def test_fsub(self):
        """Mode 2: field subtraction mod p25519."""
        fa = FieldALU()
        self._set_a(fa, 100)
        self._set_b(fa, 30)
        self._go(fa, 2)  # FSUB
        assert self._result_lo(fa) == 70

    def test_fmul(self):
        """Mode 3: field multiplication mod p25519."""
        fa = FieldALU()
        self._set_a(fa, 7)
        self._set_b(fa, 13)
        self._go(fa, 3)  # FMUL
        assert self._result_lo(fa) == 91

    def test_mul_raw(self):
        """Mode 7: raw 256x256->512-bit multiply."""
        fa = FieldALU()
        a = (1 << 200)
        b = (1 << 200)
        self._set_a(fa, a)
        self._set_b(fa, b)
        self._go(fa, 7)  # MUL_RAW
        lo = self._result_lo(fa)
        hi = self._result_hi(fa)
        assert (hi << 256) | lo == a * b

    def test_status_done_bit(self):
        """STATUS done bit set after compute."""
        fa = FieldALU()
        self._set_a(fa, 1)
        self._set_b(fa, 1)
        self._go(fa, 1)  # FADD
        st = fa.read8(0x00)
        assert st & 0x02  # done
        assert not (st & 0x01)  # not busy

    def test_ops_counted(self):
        fa = FieldALU()
        self._set_a(fa, 1)
        self._set_b(fa, 2)
        self._go(fa, 1)
        self._go(fa, 2)
        assert fa.ops_done == 2


# ═════════════════════════════════════════════════════════════════════
#  BUS INTEGRATION
# ═════════════════════════════════════════════════════════════════════

class TestCryptoBusRegistration:
    def test_all_crypto_on_bus(self):
        """All 7 crypto devices registered at non-overlapping MMIO offsets."""
        bus = DeviceBus()
        # Layout: CRC(32B), AES(128B), SHA3(64B), TRNG(64B),
        #         FieldALU(72B, incl. X25519 mode), NTT(64B), KEM(64B)
        layout = [
            (0x07C0, 0x20,  CRC()),       # +0x07C0..0x07DF
            (0x0800, 0x80,  AES()),       # +0x0800..0x087F
            (0x0880, 0x40,  SHA3()),      # +0x0880..0x08BF
            (0x08C0, 0x40,  TRNG()),      # +0x08C0..0x08FF
            (0x0900, 0x48,  FieldALU()),  # +0x0900..0x0947
            (0x0980, 0x40,  NTT()),       # +0x0980..0x09BF
            (0x09C0, 0x40,  KEM()),       # +0x09C0..0x09FF
        ]
        for off, sz, dev in layout:
            bus.register(off, sz, dev)

        base = bus.base
        # Read STATUS (present bit) from devices that have one
        status_checks = [
            (0x0800, 0x2D),   # AES
            (0x0880, 0x01),   # SHA3
            (0x08C0, 0x01),   # TRNG
            (0x0900, 0x00),   # FieldALU (STATUS at offset 0x00)
            (0x0980, 0x01),   # NTT
            (0x09C0, 0x01),   # KEM
        ]
        for dev_off, status_off in status_checks:
            val = bus.read(base + dev_off + status_off)
            assert val & 0x80, f"Device at +0x{dev_off:04X} not present"
