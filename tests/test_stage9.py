"""Stage 9: SoC wiring, IRQ plumbing, boot protocol, and BIOS tests.

Stages A–D in the path to a bootable Chimera-1 system.
"""
from __future__ import annotations
import struct

import pytest

from chimera.soc import (
    ChimeraSoC,
    MMIO_UART, MMIO_TIMER, MMIO_STORAGE, MMIO_SYSINFO,
    MMIO_NIC, MMIO_MAILBOX, MMIO_DMA, MMIO_CRC,
    MMIO_AES, MMIO_SHA3, MMIO_TRNG, MMIO_FIELD_ALU,
    MMIO_NTT, MMIO_KEM, MMIO_FB,
)
from chimera.mp64.core import (
    MP64Core, IVEC_TIMER, IVEC_RESET,
)
from chimera.mp64 import asm
from chimera.devices.bus import DeviceBus


# ═════════════════════════════════════════════════════════════════════
#  STAGE A — SoC Device Wiring
# ═════════════════════════════════════════════════════════════════════

class TestSoCWiring:
    """Verify all devices are auto-wired and accessible from MP64 cores."""

    def _soc(self, memsz: int = 1 << 16) -> ChimeraSoC:
        return ChimeraSoC(bytearray(memsz), mp64_cores=1, lm1_tiles=1)

    def test_bus_created(self):
        soc = self._soc()
        assert isinstance(soc.bus, DeviceBus)

    def test_all_devices_instantiated(self):
        soc = self._soc()
        assert soc.uart is not None
        assert soc.timer is not None
        assert soc.storage is not None
        assert soc.sysinfo is not None
        assert soc.nic is not None
        assert soc.dma is not None
        assert soc.crc is not None
        assert soc.aes is not None
        assert soc.sha3 is not None
        assert soc.trng is not None
        assert soc.field_alu is not None
        assert soc.ntt is not None
        assert soc.kem is not None
        assert soc.fb is not None
        assert soc.mailbox is not None

    def test_mmio_reads_from_core(self):
        """Core 0 can read device status via MMIO."""
        soc = self._soc()
        core = soc.mp64.cores[0]
        base = core.mmio_start
        # SysInfo: SOC_ID at offset 0x00 should be non-zero
        b0 = core._r8(base + MMIO_SYSINFO + 0)
        b1 = core._r8(base + MMIO_SYSINFO + 1)
        soc_id = b0 | (b1 << 8)
        assert soc_id != 0

    def test_mmio_write_uart_tx(self):
        """Core 0 can write to UART TX via MMIO, host reads it."""
        soc = self._soc()
        core = soc.mp64.cores[0]
        base = core.mmio_start
        core._w8(base + MMIO_UART + 0, ord('X'))
        assert soc.uart_output() == 'X'

    def test_timer_accessible(self):
        """Timer reload value writable via MMIO."""
        soc = self._soc()
        core = soc.mp64.cores[0]
        base = core.mmio_start
        # Write reload = 100
        for i in range(4):
            core._w8(base + MMIO_TIMER + 4 + i, (100 >> (8 * i)) & 0xFF)
        assert soc.timer.reload == 100

    def test_storage_dma_wired(self):
        """Storage device has DMA callbacks connected to shared memory."""
        soc = self._soc()
        assert soc.storage._mem_read is not None
        assert soc.storage._mem_write is not None
        # Write a byte via the callback and verify it lands in mem
        soc.storage._mem_write(0x100, 0xAB)
        assert soc.mem[0x100] == 0xAB

    def test_dma_engine_wired(self):
        """DMA engine has memory callbacks."""
        soc = self._soc()
        assert soc.dma._mem_read is not None
        assert soc.dma._mem_write is not None

    def test_multi_core_all_see_bus(self):
        """All MP64 cores share the same bus."""
        soc = ChimeraSoC(bytearray(1 << 16), mp64_cores=4, lm1_tiles=1)
        for i, core in enumerate(soc.mp64.cores):
            assert core.mmio_read is not None, f"core {i} mmio_read not wired"
            assert core.mmio_write is not None, f"core {i} mmio_write not wired"
        # All cores reach the same UART — write from core 3, read from soc
        base = soc.mp64.cores[3].mmio_start
        soc.mp64.cores[3]._w8(base + MMIO_UART, ord('Z'))
        assert soc.uart_output() == 'Z'

    def test_uart_roundtrip_via_program(self):
        """MP64 program writes to UART TX, host reads output."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        core = soc.mp64.cores[0]
        base = core.mmio_start

        # Build a small program: load UART TX address, store 'H', halt
        prog = b""
        prog += asm.ldi64(3, base + MMIO_UART)  # R3 = UART TX addr
        prog += asm.ldi(4, ord('H'))             # R4 = 'H'
        prog += asm.st_b(3, 4)                   # mem[R3] = R4 (byte store)
        prog += asm.halt()
        mem[:len(prog)] = prog
        soc.run(100)
        assert soc.uart_output() == 'H'

    def test_crypto_devices_on_bus(self):
        """All crypto devices respond to STATUS reads via the bus."""
        soc = self._soc()
        base = soc.bus.base
        # FieldALU STATUS at offset 0x00
        assert soc.bus.read(base + MMIO_FIELD_ALU + 0x00) & 0x80
        # SHA3 STATUS at offset 0x01
        assert soc.bus.read(base + MMIO_SHA3 + 0x01) & 0x80
        # TRNG STATUS at offset 0x01
