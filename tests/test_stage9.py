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
        assert soc.bus.read(base + MMIO_TRNG + 0x01) & 0x80
        # NTT STATUS at offset 0x01
        assert soc.bus.read(base + MMIO_NTT + 0x01) & 0x80
        # KEM STATUS at offset 0x01
        assert soc.bus.read(base + MMIO_KEM + 0x01) & 0x80


# ═════════════════════════════════════════════════════════════════════
#  STAGE B — Interrupt Plumbing
# ═════════════════════════════════════════════════════════════════════

class TestTimerIRQ:
    """Timer fires and delivers IVEC_TIMER trap to MP64 core."""

    def test_timer_fires_on_step(self):
        """Timer countdown reaches 0 and fires IRQ pending."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        soc.timer.reload = 5
        soc.timer.count = 5
        soc.timer.ctrl = 0x03  # enable + auto-reload
        for _ in range(5):
            soc.timer.tick()
        assert soc.timer.ctrl & 0x04  # IRQ pending

    def test_timer_irq_delivered_to_core(self):
        """When timer fires and IE=1, core takes IVEC_TIMER trap."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        core = soc.mp64.cores[0]

        # Build an IVT — vector 7 (TIMER) points to handler at 0x1000
        handler_addr = 0x1000
        struct.pack_into("<Q", mem, 7 * 8, handler_addr)

        # Handler: just HALT
        mem[handler_addr] = 0x02  # HALT

        # Main program at 0x0200: set IVT, set SP, enable interrupts, loop
        code_base = 0x0200
        prog = b""
        prog += asm.ldi64(2, 0xFFF0)      # SP = 0xFFF0
        prog += asm.sep(0)                 # P=R0 (already is, but explicit)
        prog += asm.ldi64(5, 0x0000)       # R5 = IVT base (address 0)
        prog += asm.csrw(5, 0x04)          # CSR[0x04] = IVT_BASE = R5
        prog += asm.ei()                   # enable interrupts
        # Busy loop: NOP forever (timer will interrupt)
        loop_start = len(prog)
        prog += asm.nop()
        prog += asm.br(asm.AL, 0xFF - 1)   # branch back (offset -2 from end)
        mem[code_base:code_base + len(prog)] = prog

        # Set timer to fire soon
        soc.timer.reload = 3
        soc.timer.count = 3
        soc.timer.ctrl = 0x03  # enable + auto-reload

        # Point PC to code
        core.regs[0] = code_base

        # Run — timer fires, core traps to handler, HALT
        soc.run(200)
        assert core.halted
        # Core should have ended at the handler
        assert core.ivec_id == IVEC_TIMER

    def test_timer_irq_not_delivered_when_di(self):
        """Timer fires but IE=0 — core does NOT trap."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        core = soc.mp64.cores[0]

        # Don't enable interrupts, just run a short program then halt
        prog = b""
        prog += asm.nop()
        prog += asm.nop()
        prog += asm.nop()
        prog += asm.halt()
        mem[:len(prog)] = prog

        soc.timer.count = 1
        soc.timer.ctrl = 0x03
        soc.run(100)
        assert core.halted
        assert core.ivec_id == 0  # no trap was delivered


# ═════════════════════════════════════════════════════════════════════
#  STAGE C — Boot Protocol
# ═════════════════════════════════════════════════════════════════════

class TestBootProtocol:
    """Core 0 boots from reset vector, runs boot ROM code."""

    def test_core0_starts_at_reset_vector(self):
        """After SoC creation, Core 0 PC = 0 (reset vector)."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        assert soc.mp64.cores[0].pc == 0

    def test_boot_rom_halt(self):
        """Simplest boot ROM: HALT at address 0."""
        mem = bytearray(1 << 16)
        mem[0] = 0x02  # HALT
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        soc.run(10)
        assert soc.mp64.cores[0].halted

    def test_boot_rom_uart_banner(self):
        """Boot ROM writes a string to UART, then halts."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        core = soc.mp64.cores[0]
        base = core.mmio_start

        banner = "OK\n"
        # Build boot code at address 0
        prog = b""
        prog += asm.ldi64(3, base + MMIO_UART)  # R3 = UART TX addr
        for ch in banner:
            prog += asm.ldi(4, ord(ch))
            prog += asm.st_b(3, 4)
        prog += asm.halt()
        mem[:len(prog)] = prog

        soc.run(200)
        assert core.halted
        assert soc.uart_output() == banner

    def test_boot_sets_ivt_and_sp(self):
        """Boot ROM sets IVT base and stack pointer."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        core = soc.mp64.cores[0]

        ivt_addr = 0x2000
        sp_val = 0xFF00

        prog = b""
        prog += asm.ldi64(2, sp_val)       # R2 = SP
        prog += asm.ldi64(5, ivt_addr)     # R5 = IVT base
        prog += asm.csrw(5, 0x04)          # CSR[0x04] = IVT_BASE
        prog += asm.halt()
        mem[:len(prog)] = prog

        soc.run(100)
        assert core.halted
        assert core.sp == sp_val
        assert core.ivt_base == ivt_addr

    def test_boot_reads_sysinfo(self):
        """Boot ROM reads BOARD_ID from SysInfo device."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        core = soc.mp64.cores[0]
        base = core.mmio_start

        # Read BOARD_ID low 16-bits (at SysInfo+0x00) into R6
        prog = b""
        prog += asm.ldi64(3, base + MMIO_SYSINFO)
        prog += asm.ld_h(6, 3)    # R6 = 16-bit load from [R3]
        prog += asm.halt()
        mem[:len(prog)] = prog

        soc.run(100)
        assert core.halted
        # BOARD_ID low 16 bits: "CH" in LE = 0x4843
        expected_lo16 = soc.sysinfo._regs[0x00] & 0xFFFF
        assert core.regs[6] == expected_lo16

    def test_boot_loads_from_storage(self):
        """Boot ROM reads sector 0 from storage into RAM via DMA."""
        mem = bytearray(1 << 16)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
        core = soc.mp64.cores[0]
        base = core.mmio_start

        # Pre-populate storage sector 0 with a known pattern
        from chimera.devices.storage import SECTOR_SIZE
        payload = bytes(range(256)) * (SECTOR_SIZE // 256)
        soc.storage.write_sectors(0, 1, payload)

        # DMA target address in RAM
        dma_target = 0x4000

        # Boot code: set sector=0, DMA addr=dma_target, CMD=READ
        prog = b""
        prog += asm.ldi64(3, base + MMIO_STORAGE)

        # Sector number = 0 (32-bit at offset 0x02..0x05)
        prog += asm.ldi(4, 0)
        prog += asm.ldi64(5, base + MMIO_STORAGE + 0x02)
        prog += asm.st_b(5, 4)

        # DMA address (64-bit at offset 0x06..0x0D)
        prog += asm.ldi64(5, base + MMIO_STORAGE + 0x06)
        prog += asm.ldi64(6, dma_target)
        # Store 64-bit dma addr byte-by-byte (simpler with st_b loop)
        for i in range(8):
            prog += asm.ldi64(7, base + MMIO_STORAGE + 0x06 + i)
            byte_val = (dma_target >> (i * 8)) & 0xFF
            prog += asm.ldi(4, byte_val)
            prog += asm.st_b(7, 4)

        # CMD = 0x01 (READ) at offset 0x00
        prog += asm.ldi64(5, base + MMIO_STORAGE + 0x00)
        prog += asm.ldi(4, 0x01)
        prog += asm.st_b(5, 4)

        prog += asm.halt()
        mem[:len(prog)] = prog

        soc.run(1000)
        assert core.halted
        # Verify data landed at dma_target
        for i in range(256):
            assert mem[dma_target + i] == i, f"byte {i} mismatch"


# ═════════════════════════════════════════════════════════════════════
#  STAGE D — Assembly BIOS
# ═════════════════════════════════════════════════════════════════════
