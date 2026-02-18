"""Tests for MEX tile engine and MMIO devices."""

import struct
import pytest
from chimera.mp64.core import MP64Core, MASK64
from chimera.mp64 import asm
from chimera.devices import DeviceBus, UART, Timer, Mailbox

# -----------------------------------------------------------------------
#  Helpers
# -----------------------------------------------------------------------

def make_core(prog: bytes | bytearray, mem_size: int = 0x10000) -> MP64Core:
    mem = bytearray(mem_size)
    mem[:len(prog)] = prog
    c = MP64Core(mem)
    c.regs[2] = mem_size - 8
    return c


def run(prog, max_steps=300, **kw):
    c = make_core(prog, **kw)
    c.run(max_steps)
    return c


def write_tile_8(core, addr, values):
    """Write up to 64 bytes into memory at *addr*."""
    for i, v in enumerate(values):
        core.mem[(addr + i) % core.mem_size] = v & 0xFF


def read_tile_8(core, addr, n=64):
    return [core.mem[(addr + i) % core.mem_size] for i in range(n)]


def write_tile_32(core, addr, values):
    for i, v in enumerate(values):
        struct.pack_into("<I", core.mem, (addr + i * 4) % core.mem_size, v & 0xFFFFFFFF)


def read_tile_32(core, addr, n=16):
    return [struct.unpack_from("<I", core.mem, (addr + i * 4) % core.mem_size)[0]
            for i in range(n)]


# =======================================================================
#  MEX — Tile Engine tests
# =======================================================================

class TestMEX:
    def _setup_tile_csrs(self, core, src0=0x1000, src1=0x1100, dst=0x1200):
        """Set tile CSRs via direct field access (faster for tests)."""
        core.tsrc0 = src0
        core.tsrc1 = src1
        core.tdst = dst

    def test_talu_add_8bit(self):
        prog = asm.program(asm.talu_add(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [10, 20, 30, 40] + [0] * 60)
        write_tile_8(c, 0x1100, [1, 2, 3, 4] + [0] * 60)
        c.run(10)
        result = read_tile_8(c, 0x1200)
        assert result[:4] == [11, 22, 33, 44]

    def test_talu_sub_8bit(self):
        prog = asm.program(asm.talu_sub(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [50, 100, 200, 255])
        write_tile_8(c, 0x1100, [10, 50, 100, 200])
        c.run(10)
        result = read_tile_8(c, 0x1200)
        assert result[:4] == [40, 50, 100, 55]  # 255-200=55

    def test_talu_mul_32bit(self):
        prog = asm.program(asm.talu_mul(asm.SZ32), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_32(c, 0x1000, [3, 7, 100, 0] + [0] * 12)
        write_tile_32(c, 0x1100, [4, 6, 200, 0] + [0] * 12)
        c.run(10)
        result = read_tile_32(c, 0x1200)
        assert result[:4] == [12, 42, 20000, 0]

    def test_talu_min_max(self):
        prog = asm.program(asm.talu_min(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [10, 50, 30])
        write_tile_8(c, 0x1100, [20, 40, 30])
        c.run(10)
        r = read_tile_8(c, 0x1200)
        assert r[:3] == [10, 40, 30]

        prog = asm.program(asm.talu_max(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [10, 50, 30])
        write_tile_8(c, 0x1100, [20, 40, 30])
        c.run(10)
        r = read_tile_8(c, 0x1200)
        assert r[:3] == [20, 50, 30]

    def test_tmul_dot_32bit(self):
        prog = asm.program(asm.tmul_dot(asm.SZ32), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        # [1,2,3,4, ...0] · [5,6,7,8, ...0] = 1*5+2*6+3*7+4*8 = 5+12+21+32=70
        write_tile_32(c, 0x1000, [1, 2, 3, 4] + [0] * 12)
        write_tile_32(c, 0x1100, [5, 6, 7, 8] + [0] * 12)
        c.run(10)
        assert c.acc[0] == 70

    def test_tmul_mac_8bit(self):
        prog = asm.program(asm.tmul_mac(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [2, 3, 4])
        write_tile_8(c, 0x1100, [5, 6, 7])
        write_tile_8(c, 0x1200, [10, 20, 30])  # pre-existing dst
        c.run(10)
        result = read_tile_8(c, 0x1200)
        assert result[:3] == [(10 + 2 * 5) & 0xFF,
                              (20 + 3 * 6) & 0xFF,
                              (30 + 4 * 7) & 0xFF]

    def test_tmul_dotacc(self):
        prog = asm.program(asm.tmul_dotacc(asm.SZ32), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        c.acc[0] = 100  # pre-existing accumulator
        write_tile_32(c, 0x1000, [1, 2, 3] + [0] * 13)
        write_tile_32(c, 0x1100, [4, 5, 6] + [0] * 13)
        c.run(10)
        # 100 + 1*4+2*5+3*6 = 100+4+10+18 = 132
        assert c.acc[0] == 132

    def test_tred_sum(self):
        prog = asm.program(asm.tred_sum(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, list(range(1, 65)))  # 1+2+...+64 = 2080
        c.run(10)
        assert c.acc[0] == 2080

    def test_tred_minmax(self):
        prog = asm.program(asm.tred_rmin(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [5, 3, 8, 1, 9] + [255] * 59)
        c.run(10)
        assert c.acc[0] == 1

        prog = asm.program(asm.tred_rmax(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [5, 3, 8, 1, 9] + [0] * 59)
        c.run(10)
        assert c.acc[0] == 9

    def test_tsys_zero(self):
        prog = asm.program(asm.tsys_zero(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1200, [0xFF] * 64)
        c.run(10)
        assert read_tile_8(c, 0x1200) == [0] * 64

    def test_tsys_movbank(self):
        prog = asm.program(asm.tsys_movbank(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        data = list(range(64))
        write_tile_8(c, 0x1000, data)
        c.run(10)
        assert read_tile_8(c, 0x1200) == data

    def test_tsys_loadc(self):
        prog = asm.program(asm.tsys_loadc(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        c.acc[0] = 42
        c.run(10)
        assert read_tile_8(c, 0x1200) == [42] * 64

    def test_tsys_shuffle(self):
        prog = asm.program(asm.tsys_shuffle(asm.SZ8), asm.halt())
        c = make_core(prog)
        self._setup_tile_csrs(c)
        write_tile_8(c, 0x1000, [10, 20, 30, 40] + [0] * 60)
        write_tile_8(c, 0x1100, [3, 2, 1, 0] + [0] * 60)
        c.run(10)
        result = read_tile_8(c, 0x1200)
        assert result[:4] == [40, 30, 20, 10]

    def test_mex_via_csr_setup(self):
        """Test MEX with tile CSRs set via instructions (not direct field)."""
        prog = asm.program(
            # Set TSRC0 = 0x1000
            asm.ldi64(4, 0x1000),
            asm.csrw(4, 0x16),
            # Set TSRC1 = 0x1100
            asm.ldi64(4, 0x1100),
            asm.csrw(4, 0x17),
            # Set TDST = 0x1200
            asm.ldi64(4, 0x1200),
            asm.csrw(4, 0x18),
            # Execute TALU ADD 8-bit
            asm.talu_add(asm.SZ8),
            asm.halt(),
        )
        c = make_core(prog)
        write_tile_8(c, 0x1000, [10, 20, 30])
        write_tile_8(c, 0x1100, [1, 2, 3])
        c.run(50)
        result = read_tile_8(c, 0x1200)
        assert result[:3] == [11, 22, 33]

    def test_perf_counter(self):
        prog = asm.program(
            asm.ldi(4, 3),
            asm.csrw(4, 0x6C),    # enable perf counters (bit 0 + reset bit 1)
            asm.talu_add(asm.SZ8),
            asm.talu_sub(asm.SZ8),
            asm.csrr(3, 0x6A),    # read PERF_TILEOPS
            asm.halt(),
        )
        c = make_core(prog)
        c.tsrc0 = 0x1000; c.tsrc1 = 0x1100; c.tdst = 0x1200
        c.run(20)
        assert c.regs[3] == 2


# =======================================================================
#  MMIO — Device bus + peripherals
# =======================================================================

class TestMMIO:
    def _make_system(self, prog):
        """Create a core with a device bus attached."""
        c = make_core(prog)
        bus = DeviceBus()
        uart = UART()
        timer = Timer()
        mbox = Mailbox()
        bus.register(0x0000, 0x100, uart)
        bus.register(0x0100, 0x100, timer)
        bus.register(0x0500, 0x100, mbox)
        c.mmio_read = bus.read
        c.mmio_write = bus.write
        return c, uart, timer, mbox


class TestUART(TestMMIO):
    def test_tx(self):
        # Write byte 'A' (0x41) to UART TX at MMIO+0
        mmio = 0xFFFF_FF00_0000_0000
        prog = asm.program(
            asm.ldi(3, 0x41),
            asm.ldi64(4, mmio),
            asm.st_b(4, 3),     # M[mmio+0] = 0x41 → UART TX
            asm.halt(),
        )
        c, uart, _, _ = self._make_system(prog)
        c.run(50)
        assert uart.drain_tx() == b"A"

    def test_rx(self):
        mmio = 0xFFFF_FF00_0000_0000
        prog = asm.program(
            asm.ldi64(4, mmio + 1),  # RX register
            asm.ld_b(3, 4),          # R3 = UART RX
            asm.halt(),
        )
        c, uart, _, _ = self._make_system(prog)
        uart.push_rx(b"X")
        c.run(50)
        assert c.regs[3] == ord("X")

    def test_status(self):
        mmio = 0xFFFF_FF00_0000_0000
        prog = asm.program(
            asm.ldi64(4, mmio + 2),
            asm.ld_b(3, 4),          # read STATUS
            asm.halt(),
        )
        c, uart, _, _ = self._make_system(prog)
        uart.push_rx(b"Y")
        c.run(50)
        assert c.regs[3] & 1  # TX ready
        assert c.regs[3] & 2  # RX available


class TestTimer(TestMMIO):
    def test_basic_tick(self):
        timer = Timer()
        timer.count = 5
        timer.ctrl = 1  # enable
        assert not timer.tick(3)
        assert timer.tick(3)  # count underflows → fires
        assert timer.ctrl & 4  # IRQ pending

    def test_auto_reload(self):
        timer = Timer()
        timer.count = 3
        timer.reload = 10
        timer.ctrl = 3  # enable + auto-reload
        assert timer.tick(3)
        assert timer.count == 10  # reloaded

    def test_write_read(self):
        timer = Timer()
        timer.write8(0, 0x10)  # count low byte
        timer.write8(1, 0x20)  # count next byte
        assert timer.count == 0x2010
        assert timer.read8(0) == 0x10
        assert timer.read8(1) == 0x20


class TestMailbox(TestMMIO):
    def test_send_receive(self):
        mbox = Mailbox()
        # Write data
        mbox.write8(0, 42)       # DATA[0] = 42
        mbox.write8(8, 1)        # SEND
        assert mbox.pending()
        assert mbox.read8(9) == 1  # STATUS: pending
        # Read data back
        assert mbox.read8(0) == 42
        # ACK
        mbox.write8(0xA, 1)
        assert not mbox.pending()

    def test_post_from_host(self):
        mbox = Mailbox()
        mbox.post(0xDEAD)
        assert mbox.pending()
        assert mbox.read8(0) == 0xAD  # low byte
        assert mbox.read8(1) == 0xDE  # next byte
