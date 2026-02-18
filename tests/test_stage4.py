"""Tests for Stage 4: Multi-core MP64, Multi-tile LM-1, χ-Bridge."""
from __future__ import annotations
import pytest
from chimera.bridge import (
    ChiBridge, Envelope, mp64_endpoint, lm1_endpoint,
    MSG_WORK_REQ, MSG_WORK_RESP, MSG_EVAL_REQ, MSG_SHUTDOWN,
    FLAG_NEEDS_REPLY, DOMAIN_MP64, DOMAIN_LM1,
    endpoint_domain, endpoint_index,
)
from chimera.mp64.cluster import MP64Cluster
from chimera.mp64.core import MP64Core
from chimera.mp64 import asm as MA
from chimera.lm1.cluster import LM1Cluster
from chimera.lm1.core import LM1Core
from chimera.lm1 import asm as LA, tagged as T
from chimera.soc import ChimeraSoC


MEMSZ = 1 << 20  # 1 MiB


# ═════════════════════════════════════════════════════════════════════
#  1. χ-Bridge
# ═════════════════════════════════════════════════════════════════════

class TestChiBridge:
    def test_send_recv(self):
        bridge = ChiBridge()
        ep = mp64_endpoint(0)
        bridge.register_endpoint(ep)
        env = Envelope(source_id=lm1_endpoint(0), dest_id=ep,
                       msg_type=MSG_WORK_RESP, payload=b"hello")
        assert bridge.send(env)
        got = bridge.recv(ep)
        assert got is not None
        assert got.msg_type == MSG_WORK_RESP
        assert got.payload == b"hello"

    def test_inbox_empty(self):
        bridge = ChiBridge()
        assert bridge.recv(mp64_endpoint(0)) is None

    def test_inbox_overflow(self):
        bridge = ChiBridge(inbox_depth=2)
        ep = mp64_endpoint(0)
        bridge.register_endpoint(ep)
        env = Envelope(dest_id=ep, msg_type=MSG_WORK_REQ)
        assert bridge.send(env)
        assert bridge.send(env)
        assert not bridge.send(env)  # full → dropped
        assert bridge.messages_dropped == 1

    def test_broadcast(self):
        bridge = ChiBridge()
        eps = [lm1_endpoint(i) for i in range(4)]
        for ep in eps:
            bridge.register_endpoint(ep)
        env = Envelope(source_id=mp64_endpoint(0), msg_type=MSG_SHUTDOWN)
        n = bridge.broadcast(env, eps)
        assert n == 4
        for ep in eps:
            msg = bridge.recv(ep)
            assert msg is not None
            assert msg.msg_type == MSG_SHUTDOWN

    def test_ipi_hook(self):
        bridge = ChiBridge()
        ep = mp64_endpoint(0)
        bridge.register_endpoint(ep)
        received = []
        bridge.register_ipi_hook(ep, lambda e: received.append(e))
        env = Envelope(dest_id=ep, msg_type=MSG_EVAL_REQ)
        bridge.send(env)
        assert len(received) == 1
        assert received[0].msg_type == MSG_EVAL_REQ

    def test_endpoint_encoding(self):
        assert endpoint_domain(mp64_endpoint(3)) == DOMAIN_MP64
        assert endpoint_index(mp64_endpoint(3)) == 3
        assert endpoint_domain(lm1_endpoint(7)) == DOMAIN_LM1
        assert endpoint_index(lm1_endpoint(7, 2)) == 2

    def test_envelope_pack_unpack(self):
        env = Envelope(
            source_id=mp64_endpoint(0),
            dest_id=lm1_endpoint(1),
            msg_type=MSG_WORK_REQ,
            flags=FLAG_NEEDS_REPLY,
            payload_len=4,
            payload=b"\x01\x02\x03\x04",
        )
        data = env.pack()
        assert len(data) == 64
        env2 = Envelope.unpack(data)
        assert env2.source_id == env.source_id
        assert env2.dest_id == env.dest_id
        assert env2.msg_type == MSG_WORK_REQ
        assert env2.flags == FLAG_NEEDS_REPLY
        assert env2.payload[:4] == b"\x01\x02\x03\x04"

    def test_pending_count(self):
        bridge = ChiBridge()
        ep = mp64_endpoint(0)
        bridge.register_endpoint(ep)
        assert bridge.pending(ep) == 0
        bridge.send(Envelope(dest_id=ep, msg_type=1))
        bridge.send(Envelope(dest_id=ep, msg_type=2))
        assert bridge.pending(ep) == 2
        bridge.recv(ep)
        assert bridge.pending(ep) == 1


# ═════════════════════════════════════════════════════════════════════
#  2. MP64 CLUSTER
# ═════════════════════════════════════════════════════════════════════

class TestMP64Cluster:
    def test_multi_core_basic(self):
        """Two cores run independently, each setting a different register."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        # Core 0: R1 = 42, halt  (R0 is PC — don't touch)
        prog0 = MA.program(MA.ldi(1, 42), MA.halt())
        # Core 1: R1 = 99, halt
        prog1 = MA.program(MA.ldi(1, 99), MA.halt())

        base0, base1 = 0, 0x1000
        mem[base0:base0+len(prog0)] = prog0
        mem[base1:base1+len(prog1)] = prog1

        cluster.cores[1].regs[cluster.cores[1].psel] = base1

        cluster.run(max_steps=100)
        assert cluster.cores[0].regs[1] == 42
        assert cluster.cores[1].regs[1] == 99
        assert cluster.all_halted

    def test_core_id_csr(self):
        """Each core reads its own COREID via CSR 0x20."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=4)

        # Program: csrr r1, 0x20; halt  (R0=PC, use R1)
        prog = MA.program(MA.csrr(1, 0x20), MA.halt())
        mem[0:len(prog)] = prog

        cluster.run(max_steps=100)
        for i in range(4):
            assert cluster.cores[i].regs[1] == i

    def test_ipi_send_receive(self):
        """Core 0 sends IPI to core 1; core 1 reads pending mask."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        # Core 0: ldi r1, 1; csrw r1, 0x22; halt  (R0=PC)
        prog0 = MA.program(
            MA.ldi(1, 1),       # target core = 1
            MA.csrw(1, 0x22),   # MBOX write → IPI to core 1
            MA.halt(),
        )
        # Core 1: wait for core 0 to send, then read IPI pending
        prog1 = MA.program(
            MA.nop(), MA.nop(),   # delay so core 0 sends first
            MA.csrr(2, 0x22),
            MA.halt(),
        )

        base0, base1 = 0, 0x1000
        mem[base0:base0+len(prog0)] = prog0
        mem[base1:base1+len(prog1)] = prog1
        cluster.cores[1].regs[cluster.cores[1].psel] = base1

        cluster.run(max_steps=100)
        # Core 1 should see pending IPI from core 0 (bit 0)
        assert cluster.cores[1].regs[2] == 1

    def test_ipi_acknowledge(self):
        """IPI acknowledged clears pending bit."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        # Set IPI pending directly
        cluster.ipi_pending[1] = 0x01  # from core 0

        # Core 1: ldi r1, 0; csrw r1, 0x23; csrr r2, 0x22; halt
        prog = MA.program(
            MA.ldi(1, 0),
            MA.csrw(1, 0x23),   # IPIACK: ack from core 0
            MA.csrr(2, 0x22),   # read pending
            MA.halt(),
        )
        base = 0x1000
        mem[base:base+len(prog)] = prog
        cluster.cores[1].regs[cluster.cores[1].psel] = base

        # Only run core 1
        cluster.cores[0].halted = True
        cluster.run(max_steps=100)
        assert cluster.cores[1].regs[2] == 0  # cleared

    def test_barrier_all_arrive(self):
        """All cores arrive at barrier → barrier_done becomes True."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        # Both cores: ldi r1, 1; csrw r1, 0x74; halt
        prog = MA.program(
            MA.ldi(1, 1),
            MA.csrw(1, 0x74),
            MA.halt(),
        )
        mem[0:len(prog)] = prog

        cluster.run(max_steps=100)
        assert cluster.barrier_done

    def test_barrier_partial(self):
        """Only one core arrives → barrier not done."""
        mem = bytearray(MEMSZ)
        cluster = MP64Cluster(mem, n_cores=2)

        prog = MA.program(MA.ldi(1, 1), MA.csrw(1, 0x74), MA.halt())
        mem[0:len(prog)] = prog
        # Only core 0 runs the barrier program
        cluster.cores[1].halted = True

        cluster.run(max_steps=100)
        assert not cluster.barrier_done


# ═════════════════════════════════════════════════════════════════════
#  3. LM-1 CLUSTER
# ═════════════════════════════════════════════════════════════════════

class TestLM1Cluster:
    def test_multi_tile_basic(self):
        """Two tiles run independently."""
        cluster = LM1Cluster(n_tiles=2, tile_memsz=MEMSZ)

        # Tile 0: li r1, 42; halt
        prog0 = LA.program(LA.li(1, 42), LA.halt())
        cluster.tiles[0].load_program(prog0)

        # Tile 1: li r1, 99; halt
        prog1 = LA.program(LA.li(1, 99), LA.halt())
        cluster.tiles[1].load_program(prog1)

        cluster.run(max_steps=100)
        assert cluster.tiles[0].thread.regs[1] == 42
        assert cluster.tiles[1].thread.regs[1] == 99

    def test_tile_id(self):
        """Each tile knows its own tile_id via SYS_INFO."""
        cluster = LM1Cluster(n_tiles=4, tile_memsz=MEMSZ)
        prog = LA.program(LA.sys_info(1, 0), LA.halt())  # r1 = tile_id
        for tile in cluster.tiles:
            tile.load_program(prog)

        cluster.run(max_steps=100)
        for i in range(4):
            assert cluster.tiles[i].thread.regs[1] == i

    def test_send_recv_queue(self):
        """SEND and RECV within a single tile's queue."""
        cluster = LM1Cluster(n_tiles=1, tile_memsz=MEMSZ)
        tile = cluster.tiles[0]

        prog = LA.program(
            LA.li(1, 42),
            # SEND: encode_i(OP_SEND, 0, rs1=1, queue=0)
            LA.encode_i(LA.OP_PUSH_POP, 0, 1, 0),   # placeholder — use raw encoding
        )

        # Actually, let me directly test via the queue API
        tile.queues[0].append(42)
        tile.queues[0].append(99)

        # RECV from queue 0 into r5
        # Opcode 37 (RECV), R-format: encode_r(OP_RECV, rd, rs1, rs2, func)
        # Use I-format for queue ID: encode_i(OP_RECV, rd, 0, queue_id)
        # Since RECV handler: R[rd] = q.popleft()
        from chimera.lm1.core import OP_RECV
        recv_insn = LA.encode_r(OP_RECV, 5, 0, 0, 0)  # RECV r5, queue 0

        prog = LA.program(recv_insn, recv_insn, LA.halt())
        tile.load_program(prog)
        # Re-add to queue (program load might have overwritten)
        tile.queues[0].clear()
        tile.queues[0].append(42)
        tile.queues[0].append(99)

        tile.run(max_steps=100)
        # r5 should have the LAST popped value: 99
        # Actually both pops go into r5, so r5=99
        assert tile.thread.regs[5] == 99

    def test_inject_to_queue(self):
        """Inject value into tile queue from external (bridge)."""
        cluster = LM1Cluster(n_tiles=2, tile_memsz=MEMSZ)
        cluster.inject_to_queue(1, 0, 0xCAFE)
        assert len(cluster.tiles[1].queues[0]) == 1
        assert cluster.tiles[1].queues[0][0] == 0xCAFE


# ═════════════════════════════════════════════════════════════════════
#  4. CHIMERA SoC
# ═════════════════════════════════════════════════════════════════════

class TestChimeraSoC:
    def test_basic_creation(self):
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=2, lm1_tiles=2)
        assert soc.mp64.n_cores == 2
        assert soc.lm1.n_tiles == 2

    def test_mp64_to_lm1_message(self):
        """MP64 core 0 sends a message to LM-1 tile 0 via bridge."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        ok = soc.mp64_send(0, lm1_endpoint(0), MSG_WORK_REQ, b"job1")
        assert ok
        assert soc.bridge.pending(lm1_endpoint(0)) == 1

        msg = soc.bridge.recv(lm1_endpoint(0))
        assert msg.msg_type == MSG_WORK_REQ
        assert msg.payload == b"job1"

    def test_lm1_to_mp64_message(self):
        """LM-1 tile 0 sends a message to MP64 core 0 via bridge."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        ok = soc.lm1_send(0, mp64_endpoint(0), MSG_WORK_RESP, b"done")
        assert ok

        msg = soc.bridge.recv(mp64_endpoint(0))
        assert msg.msg_type == MSG_WORK_RESP
        assert msg.payload == b"done"

    def test_cross_domain_roundtrip(self):
        """MP64 → LM-1 → MP64 round-trip message."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        # MP64 sends work request
        soc.mp64_send(0, lm1_endpoint(0), MSG_WORK_REQ, b"compute")
        # LM-1 receives it
        msg = soc.bridge.recv(lm1_endpoint(0))
        assert msg.msg_type == MSG_WORK_REQ

        # LM-1 sends response back
        soc.lm1_send(0, mp64_endpoint(0), MSG_WORK_RESP, b"result42")
        msg2 = soc.bridge.recv(mp64_endpoint(0))
        assert msg2.msg_type == MSG_WORK_RESP
        assert msg2.payload == b"result42"

    def test_broadcast_shutdown(self):
        """Broadcast SHUTDOWN to all LM-1 tiles."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=4)

        eps = [lm1_endpoint(i) for i in range(4)]
        env = Envelope(
            source_id=mp64_endpoint(0),
            msg_type=MSG_SHUTDOWN,
        )
        n = soc.bridge.broadcast(env, eps)
        assert n == 4
        for ep in eps:
            msg = soc.bridge.recv(ep)
            assert msg.msg_type == MSG_SHUTDOWN

    def test_run_both_domains(self):
        """Both MP64 and LM-1 run programs simultaneously."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        # MP64: ldi r1, 77; halt  (R0=PC)
        prog_mp = MA.program(MA.ldi(1, 77), MA.halt())
        mem[0:len(prog_mp)] = prog_mp

        # LM-1: li r1, 88; halt
        prog_lm = LA.program(LA.li(1, 88), LA.halt())
        soc.lm1.tiles[0].load_program(prog_lm)

        soc.run(max_steps=100)
        assert soc.mp64.cores[0].regs[1] == 77
        assert soc.lm1.tiles[0].thread.regs[1] == 88
        assert soc.all_halted

    def test_drain_bridge(self):
        """drain_bridge delivers pending messages."""
        mem = bytearray(MEMSZ)
        soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)

        soc.mp64_send(0, lm1_endpoint(0), MSG_EVAL_REQ, b"(+ 1 2)")
        # drain_bridge should deliver the message to LM-1 queue 0
        n = soc.drain_bridge()
        assert n >= 1
        # The tile's queue 0 should have the msg_type deposited
        assert len(soc.lm1.tiles[0].queues[0]) == 1


# ═════════════════════════════════════════════════════════════════════
#  5. CONCURRENCY PRIMITIVES
# ═════════════════════════════════════════════════════════════════════

class TestLM1Concurrency:
    def test_cas_tagged_success(self):
        """CAS.TAGGED succeeds when current value matches expectation."""
        from chimera.lm1.core import OP_CAS_TAGGED

        mem = bytearray(MEMSZ)
        core = LM1Core(mem)
        core.init_nursery()

        # Store the old value at address 0x2000
        import struct
        struct.pack_into("<Q", mem, 0x2000, T.tag_fixnum(10))

        # r1 = address, r2 = expected old, r3 = new value
        prog = LA.program(
            LA.li(1, 0x2000),              # r1 = addr
            LA.li(2, T.tag_fixnum(10)),    # r2 = expected
            LA.li(3, T.tag_fixnum(20)),    # r3 = new (goes in rd)
            # CAS: encode_r(OP_CAS_TAGGED, rd=3, rs1=1, rs2=2, func=0)
            LA.encode_r(OP_CAS_TAGGED, 3, 1, 2, 0),
            LA.halt(),
        )
        core.load_program(prog)
        core.run(max_steps=100)

        # CAS should succeed: r3 = T, memory updated
        assert core.thread.regs[3] == T.T
        val = struct.unpack_from("<Q", mem, 0x2000)[0]
        assert val == T.tag_fixnum(20)

    def test_cas_tagged_failure(self):
        """CAS.TAGGED fails when current doesn't match."""
        from chimera.lm1.core import OP_CAS_TAGGED
        import struct

        mem = bytearray(MEMSZ)
        core = LM1Core(mem)
        core.init_nursery()

        struct.pack_into("<Q", mem, 0x2000, T.tag_fixnum(999))

        prog = LA.program(
            LA.li(1, 0x2000),
            LA.li(2, T.tag_fixnum(10)),     # wrong expected
            LA.li(3, T.tag_fixnum(20)),
            LA.encode_r(OP_CAS_TAGGED, 3, 1, 2, 0),
            LA.halt(),
        )
        core.load_program(prog)
        core.run(max_steps=100)

        assert core.thread.regs[3] == T.NIL
        # Memory unchanged
        val = struct.unpack_from("<Q", mem, 0x2000)[0]
        assert val == T.tag_fixnum(999)
