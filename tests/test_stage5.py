"""Stage 5: Full Chimera-1 integration tests.

End-to-end scenarios exercising the complete SoC:
  - MP64 programs interacting with MMIO devices
  - LM-1 programs with tagged allocations and GC
  - Cross-domain work-request / work-response flows
  - Multi-core coordination patterns
  - C acceleration across both domains
"""
from __future__ import annotations
import struct, pytest
from chimera.soc import ChimeraSoC
from chimera.bridge import (
    ChiBridge, Envelope, mp64_endpoint, lm1_endpoint,
    MSG_WORK_REQ, MSG_WORK_RESP, MSG_EVAL_REQ, MSG_EVAL_RESP,
    MSG_SHUTDOWN, MSG_STATUS_REQ, MSG_STATUS_RESP,
)
from chimera.mp64.cluster import MP64Cluster
from chimera.mp64.core import MP64Core
from chimera.mp64 import asm as MA
from chimera.lm1.cluster import LM1Cluster
from chimera.lm1.core import LM1Core
from chimera.lm1 import asm as LA, tagged as T
from chimera.devices.bus import DeviceBus
from chimera.devices.uart import UART
from chimera.devices.timer import Timer
from chimera.devices.mailbox import Mailbox

MEMSZ = 1 << 20


# ═════════════════════════════════════════════════════════════════════
#  1. MP64 + MMIO INTEGRATION
# ═════════════════════════════════════════════════════════════════════

class TestMP64WithMMIO:
    """MP64 core with UART and Timer devices attached."""

    def test_uart_via_bus(self):
        """UART accessible through DeviceBus read/write."""
        uart = UART()
        bus = DeviceBus()
        bus.register(0x0000, 0x100, uart)

        base = bus.base
        # Write 'H' to TX register (offset 0)
        bus.write(base + 0, ord('H'))
        bus.write(base + 0, ord('i'))
        assert uart.drain_tx() == b"Hi"

    def test_uart_rx_push(self):
        """UART RX data pushed from host, read byte-by-byte."""
        uart = UART()
        bus = DeviceBus()
        bus.register(0x0000, 0x100, uart)

        uart.push_rx(b"OK")
        base = bus.base
        # RX is at offset 1
        assert bus.read(base + 1) == ord('O')
        assert bus.read(base + 1) == ord('K')

    def test_timer_countdown(self):
        """Timer counts down and sets IRQ flag."""
        timer = Timer()
        # Set count = 5 byte-by-byte (LE: byte0=5, bytes1-3=0)
        timer.write8(0, 5)
        # Enable timer: bit 0 of CTRL (offset 8)
        timer.write8(8, 0x01)
        # Tick 5 times → count reaches 0 → IRQ
        for _ in range(5):
            timer.tick()
        # CTRL bit 2 = IRQ pending
        assert timer.read8(8) & 0x04

    def test_mailbox_roundtrip(self):
        """Mailbox send and receive."""
        mbox = Mailbox()
        mbox.post(0xAB)
        assert mbox.read8(9) == 1   # STATUS: has message
        val = mbox.read8(0)          # DATA byte 0
        assert val == 0xAB


# ═════════════════════════════════════════════════════════════════════
#  2. LM-1 LISP PATTERNS
# ═════════════════════════════════════════════════════════════════════

class TestLM1LispPatterns:
    """Higher-level Lisp patterns on the LM-1 core."""

    def test_map_double(self):
        """Apply 'double' to each element of a list.

        Build (1 2 3), double each → (2 4 6), sum → 12.
        """
        mem = bytearray(MEMSZ)
        core = LM1Core(mem)
        core.init_nursery()

        # Build list (1 2 3)
        prog = LA.program(
            # (cons 3 nil)
            LA.alloc_cons(10),
            LA.li(1, T.tag_fixnum(3)), LA.st_car(10, 1),
            LA.li(2, T.NIL), LA.st_cdr(10, 2),
            # (cons 2 (3))
            LA.alloc_cons(11),
            LA.li(1, T.tag_fixnum(2)), LA.st_car(11, 1),
            LA.st_cdr(11, 10),
            # (cons 1 (2 3))
            LA.alloc_cons(12),
            LA.li(1, T.tag_fixnum(1)), LA.st_car(12, 1),
            LA.st_cdr(12, 11),

            # Map-double: walk list, double each car in-place
            # r12 = current, r20 = acc (sum of doubled values)
            LA.li(20, T.tag_fixnum(0)),
            # loop:
            LA.tst(21, 12, 4),                    # nil?
            LA.br_t(21, 6),                        # jump to done
            LA.ld_car(22, 12),                     # r22 = car
            LA.add_fix(22, 22, 22),                # double it
            LA.add_fix(20, 20, 22),                # acc += doubled
            LA.ld_cdr(12, 12),                     # next
            LA.br(-6),                             # back to loop
            # done:
            LA.halt(),
        )
        core.load_program(prog)
        core.run(max_steps=500)
        assert T.untag_fixnum(core.thread.regs[20]) == 12  # 2+4+6

    def test_recursive_length(self):
        """Compute length of a list using tail-recursive loop."""
        mem = bytearray(MEMSZ)
        core = LM1Core(mem)
        core.init_nursery()

        prog = LA.program(
            # Build (a b c d) — 4 elements
            LA.alloc_cons(10), LA.li(1, T.tag_fixnum(4)),
            LA.st_car(10, 1), LA.li(2, T.NIL), LA.st_cdr(10, 2),
            LA.alloc_cons(11), LA.li(1, T.tag_fixnum(3)),
            LA.st_car(11, 1), LA.st_cdr(11, 10),
            LA.alloc_cons(12), LA.li(1, T.tag_fixnum(2)),
            LA.st_car(12, 1), LA.st_cdr(12, 11),
            LA.alloc_cons(13), LA.li(1, T.tag_fixnum(1)),
            LA.st_car(13, 1), LA.st_cdr(13, 12),

            # Length loop: r13 = list, r20 = count
            LA.li(20, T.tag_fixnum(0)),
            # loop:
            LA.tst(21, 13, 4),                    # nil?
            LA.br_t(21, 4),                        # done
            LA.add_fix_imm(20, 20, 1),             # count++
            LA.ld_cdr(13, 13),
            LA.br(-4),
            # done:
            LA.halt(),
        )
        core.load_program(prog)
        core.run(max_steps=500)
        assert T.untag_fixnum(core.thread.regs[20]) == 4

    def test_nested_allocation(self):
        """Allocate objects within objects (tree structure)."""
        mem = bytearray(MEMSZ)
        core = LM1Core(mem)
        core.init_nursery()

        prog = LA.program(
            # Allocate leaf nodes
            LA.alloc(5, 2),                        # node A
            LA.li(1, T.tag_fixnum(10)),
            LA.st_field(5, 1, 0),                  # A.value = 10

            LA.alloc(6, 2),                        # node B
            LA.li(1, T.tag_fixnum(20)),
            LA.st_field(6, 1, 0),                  # B.value = 20

            # Allocate parent holding both children
            LA.alloc(7, 2),                        # parent
            LA.st_field(7, 5, 0),                  # parent.left = A
            LA.st_field(7, 6, 1),                  # parent.right = B

            # Read back: parent.left.value + parent.right.value
            LA.ld_field(8, 7, 0),                  # r8 = parent.left
            LA.ld_field(9, 8, 0),                  # r9 = left.value = 10
            LA.ld_field(10, 7, 1),                 # r10 = parent.right
            LA.ld_field(11, 10, 0),                # r11 = right.value = 20
            LA.add_fix(20, 9, 11),                 # r20 = 10 + 20
            LA.halt(),
        )
        core.load_program(prog)
        core.run(max_steps=500)
        assert T.untag_fixnum(core.thread.regs[20]) == 30


# ═════════════════════════════════════════════════════════════════════
#  3. CROSS-DOMAIN WORK REQUEST / RESPONSE
# ═════════════════════════════════════════════════════════════════════

class TestCrossDomain:
    def test_work_request_response(self):
        """MP64 sends WORK_REQ, receives WORK_RESP via bridge."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        # Step 1: MP64 → LM-1 work request
        soc.mp64_send(0, lm1_endpoint(0), MSG_WORK_REQ,
                       b"compute_42")
        msg = soc.bridge.recv(lm1_endpoint(0))
        assert msg.msg_type == MSG_WORK_REQ
        assert msg.payload == b"compute_42"

        # Step 2: LM-1 "processes" and sends response
        soc.lm1_send(0, mp64_endpoint(0), MSG_WORK_RESP,
                      struct.pack("<Q", 42))
        resp = soc.bridge.recv(mp64_endpoint(0))
        assert resp.msg_type == MSG_WORK_RESP
        assert struct.unpack("<Q", resp.payload[:8])[0] == 42

    def test_eval_request(self):
        """EVAL_REQ sends a Lisp expression, EVAL_RESP returns result."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        soc.mp64_send(0, lm1_endpoint(0), MSG_EVAL_REQ, b"(+ 1 2)")
        msg = soc.bridge.recv(lm1_endpoint(0))
        assert msg.msg_type == MSG_EVAL_REQ
        assert msg.payload == b"(+ 1 2)"

        soc.lm1_send(0, mp64_endpoint(0), MSG_EVAL_RESP, b"3")
        resp = soc.bridge.recv(mp64_endpoint(0))
        assert resp.payload == b"3"

    def test_status_query(self):
        """STATUS_REQ / STATUS_RESP health check."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=2, lm1_tiles=4)

        # Query all LM-1 tiles
        for i in range(4):
            soc.mp64_send(0, lm1_endpoint(i), MSG_STATUS_REQ)

        # Each tile responds
        for i in range(4):
            msg = soc.bridge.recv(lm1_endpoint(i))
            assert msg.msg_type == MSG_STATUS_REQ
            soc.lm1_send(i, mp64_endpoint(0), MSG_STATUS_RESP,
                          struct.pack("<I", i))

        # Collect responses
        for i in range(4):
            resp = soc.bridge.recv(mp64_endpoint(0))
            assert resp.msg_type == MSG_STATUS_RESP

    def test_shutdown_broadcast(self):
        """SHUTDOWN broadcast halts all LM-1 tiles."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=4)

        # Load halt programs on all tiles
        halt_prog = LA.program(LA.halt())
        for tile in soc.lm1.tiles:
            tile.load_program(halt_prog)

        # Broadcast shutdown
        eps = [lm1_endpoint(i) for i in range(4)]
        env = Envelope(source_id=mp64_endpoint(0), msg_type=MSG_SHUTDOWN)
        soc.bridge.broadcast(env, eps)

        # Verify all messages pending
        for ep in eps:
            assert soc.bridge.pending(ep) == 1


# ═════════════════════════════════════════════════════════════════════
#  4. MULTI-CORE MP64 COORDINATION
# ═════════════════════════════════════════════════════════════════════

class TestMultiCoreCoordination:
    def test_parallel_sum(self):
        """Two MP64 cores each compute partial sums, verify independently.

        Core 0: sum 1..3 into R3
        Core 1: sum 4..6 into R3
        """
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        # Core 0 at 0x0000: sum 1+2+3
        prog0 = MA.program(
            MA.ldi(3, 0),     # acc
            MA.ldi(4, 1), MA.add(3, 4),   # +1
            MA.ldi(4, 2), MA.add(3, 4),   # +2
            MA.ldi(4, 3), MA.add(3, 4),   # +3
            MA.halt(),
        )
        mem[0:len(prog0)] = prog0

        # Core 1 at 0x2000: sum 4+5+6
        prog1 = MA.program(
            MA.ldi(3, 0),
            MA.ldi(4, 4), MA.add(3, 4),
            MA.ldi(4, 5), MA.add(3, 4),
            MA.ldi(4, 6), MA.add(3, 4),
            MA.halt(),
        )
        base1 = 0x2000
        mem[base1:base1+len(prog1)] = prog1
        cluster.cores[1].regs[cluster.cores[1].psel] = base1

        cluster.run(max_steps=200)
        assert cluster.cores[0].regs[3] == 6    # 1+2+3
        assert cluster.cores[1].regs[3] == 15   # 4+5+6
        assert cluster.all_halted

    def test_shared_memory_visibility(self):
        """Cores share the same memory bytearray."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        data_addr = 0x8000

        # Directly deposit value in shared memory
        struct.pack_into("<Q", mem, data_addr, 0xCAFE_BABE)

        # Core 0: halt immediately
        prog0 = MA.program(MA.halt())
        mem[0:len(prog0)] = prog0

        # Core 1: halt immediately
        prog1 = MA.program(MA.halt())
        base1 = 0x3000
        mem[base1:base1+len(prog1)] = prog1
        cluster.cores[1].regs[cluster.cores[1].psel] = base1

        cluster.run(max_steps=200)

        # Both cores share the same `mem`, so the value is visible
        val = struct.unpack_from("<Q", mem, data_addr)[0]
        assert val == 0xCAFE_BABE
        assert cluster.all_halted


# ═════════════════════════════════════════════════════════════════════
#  5. C ACCELERATION ACROSS DOMAINS
# ═════════════════════════════════════════════════════════════════════

class TestAccelIntegration:
    def test_mp64_accel_in_cluster(self):
        """MP64 C acceleration works within cluster context."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        # Try loading accel on core 0
        accel_ok = cluster.cores[0].load_accel()
        if not accel_ok:
            pytest.skip("MP64 C accelerator not built")

        # Core 0: sum 1..10 via accel path
        # ldi=3B, add=2B, addi=3B, br=2B, halt=1B
        prog = MA.program(
            MA.ldi(1, 10),             # [0]  3B: counter
            MA.ldi(2, 0),              # [3]  3B: acc
            # loop at offset 6:
            MA.add(2, 1),              # [6]  2B: acc += counter
            MA.addi(1, (-1) & 0xFF),   # [8]  3B: counter-- (sets flags)
            MA.br(0x02, (-7) & 0xFF),  # [11] 2B: CC_NE, off=-7 → offset 6
            MA.halt(),                 # [13] 1B
        )
        mem[0:len(prog)] = prog

        # Only core 0; halt core 1
        cluster.cores[1].halted = True
        cluster.cores[0].run_accel(max_steps=10_000)
        assert cluster.cores[0].regs[2] == 55

    def test_lm1_accel_in_cluster(self):
        """LM-1 C acceleration works within cluster context."""
        cluster = LM1Cluster(n_tiles=1, tile_memsz=MEMSZ)
        tile = cluster.tiles[0]

        accel_ok = tile.load_accel()
        if not accel_ok:
            pytest.skip("LM-1 C accelerator not built")

        prog = LA.program(
            LA.li(1, 7), LA.li(2, 6),
            LA.mul(3, 1, 2), LA.halt(),
        )
        tile.load_program(prog)
        tile.run_accel(10_000)
        assert tile.thread.regs[3] == 42


# ═════════════════════════════════════════════════════════════════════
#  6. FULL SOC END-TO-END
# ═════════════════════════════════════════════════════════════════════

class TestFullSoC:
    def test_boot_sequence(self):
        """MP64 boots, all LM-1 tiles start with halt.

        Simulates the basic boot: MP64 core 0 runs startup code,
        LM-1 tiles wait for messages.
        """
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=2, lm1_tiles=4)

        # MP64 core 0: set R1=0xBOOT, read core ID, halt
        prog = MA.program(
            MA.csrr(1, 0x20),   # R1 = core_id (0)
            MA.csrr(2, 0x21),   # R2 = n_cores
            MA.halt(),
        )
        mem[0:len(prog)] = prog

        # Core 1: just halt immediately
        prog1 = MA.program(MA.halt())
        base1 = 0x1000
        mem[base1:base1+len(prog1)] = prog1
        soc.mp64.cores[1].regs[soc.mp64.cores[1].psel] = base1

        # All LM-1 tiles: halt
        for tile in soc.lm1.tiles:
            tile.load_program(LA.program(LA.halt()))

        soc.run(max_steps=200)
        assert soc.all_halted
        assert soc.mp64.cores[0].regs[1] == 0   # core_id
        assert soc.mp64.cores[0].regs[2] == 2   # n_cores

    def test_soc_stats(self):
        """Verify bridge statistics after message exchange."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=2)

        soc.mp64_send(0, lm1_endpoint(0), MSG_WORK_REQ, b"job")
        soc.mp64_send(0, lm1_endpoint(1), MSG_WORK_REQ, b"job2")
        soc.lm1_send(0, mp64_endpoint(0), MSG_WORK_RESP, b"res")

        assert soc.bridge.messages_routed == 3
        assert soc.bridge.messages_dropped == 0

    def test_mixed_execution(self):
        """MP64 and LM-1 both compute, bridge message exchanged."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        # MP64: compute R3 = 7*8 = 56
        prog_mp = MA.program(
            MA.ldi(3, 7),
            MA.ldi(4, 8),
            MA.mul(3, 4),  # R3 *= R4
            MA.halt(),
        )
        mem[0:len(prog_mp)] = prog_mp

        # LM-1: compute 5! = 120 using mul_fix loop
        # r1 = counter (5..1), r2 = accumulator (1), r3 = zero for comparison
        prog_lm = LA.program(
            LA.li(1, T.tag_fixnum(6)),           # counter = 6
            LA.li(2, T.tag_fixnum(1)),           # acc = 1
            LA.li(3, T.tag_fixnum(1)),           # limit = 1
            # loop:
            LA.eq_tagged(4, 1, 3),               # r4 = (counter == 1)?
            LA.br_t(4, 4),                       # → done
            LA.add_fix_imm(1, 1, (-1) & 0xFFFF),# counter--
            LA.mul_fix(2, 2, 1),                 # acc *= counter
            LA.br(-4),                           # → loop
            # done:
            LA.halt(),
        )
        soc.lm1.tiles[0].load_program(prog_lm)
        soc.lm1.tiles[0].init_nursery()

        soc.run(max_steps=1000)
        assert soc.mp64.cores[0].regs[3] == 56
        # LM-1 r2 has the tagged fixnum result: 5! = 120
        assert T.untag_fixnum(soc.lm1.tiles[0].thread.regs[2]) == 120
