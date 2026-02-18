"""Chimera-1 SoC: unified MP64 + LM-1 emulator with χ-Bridge.

Ties together MP64Cluster, LM1Cluster, ChiBridge, and the full MMIO
device bus into a single system that can be stepped or run as one unit.
"""
from __future__ import annotations
from chimera.bridge import (
    ChiBridge, Envelope, mp64_endpoint, lm1_endpoint,
    DOMAIN_MP64, DOMAIN_LM1, endpoint_domain,
)
from chimera.mp64.cluster import MP64Cluster
from chimera.mp64.core import IVEC_TIMER
from chimera.lm1.cluster import LM1Cluster
from chimera.devices.bus import DeviceBus
from chimera.devices.uart import UART
from chimera.devices.timer import Timer
from chimera.devices.mailbox import Mailbox
from chimera.devices.crc import CRC
from chimera.devices.aes import AES
from chimera.devices.sha3 import SHA3
from chimera.devices.trng import TRNG
from chimera.devices.field_alu import FieldALU
from chimera.devices.ntt import NTT
from chimera.devices.kem import KEM
from chimera.devices.storage import Storage
from chimera.devices.dma import DMAEngine
from chimera.devices.sysinfo import SysInfo
from chimera.devices.nic import NIC, LoopbackBackend
from chimera.devices.framebuffer import Framebuffer

# ── Canonical MMIO offsets (from bus base) ───────────────────────
# These match MegaPad's mp64_defs.vh where applicable.
MMIO_UART      = 0x0000  # 256B
MMIO_TIMER     = 0x0100  # 256B
MMIO_STORAGE   = 0x0200  # 256B
MMIO_SYSINFO   = 0x0300  # 256B
MMIO_NIC       = 0x0400  # 256B
MMIO_MAILBOX   = 0x0500  # 256B
MMIO_DMA       = 0x0600  # 256B
MMIO_CRC       = 0x07C0  # 32B
MMIO_AES       = 0x0800  # 128B
MMIO_SHA3      = 0x0880  # 64B
MMIO_TRNG      = 0x08C0  # 64B
MMIO_FIELD_ALU = 0x0900  # 72B
MMIO_NTT       = 0x0980  # 64B
MMIO_KEM       = 0x09C0  # 64B
MMIO_FB        = 0x0A00  # 256B


class ChimeraSoC:
    """Top-level Chimera-1 System-on-Chip emulator.

    Parameters
    ----------
    mp64_mem : bytearray
        Shared memory for all MP64 cores.
    mp64_cores : int
        Number of MP64 cores (default 4).
    lm1_tiles : int
        Number of LM-1 tiles (default 8).
    lm1_tile_memsz : int
        Memory size per LM-1 tile (default 1 MiB).
    """

    def __init__(self, mp64_mem: bytearray, *,
                 mp64_cores: int = 4,
                 lm1_tiles: int = 8,
                 lm1_tile_memsz: int = 1 << 20):
        self.mem = mp64_mem
        self.bridge = ChiBridge()
        self.mp64 = MP64Cluster(mp64_mem, mp64_cores, bridge=self.bridge)
        self.lm1 = LM1Cluster(lm1_tiles, lm1_tile_memsz, bridge=self.bridge)

        # ── Instantiate all MMIO devices ─────────────────────────
        self.uart      = UART()
        self.timer     = Timer()
        self.mailbox   = Mailbox()
        self.storage   = Storage()
        self.sysinfo   = SysInfo()
        self.nic       = NIC(backend=LoopbackBackend())
        self.dma       = DMAEngine()
        self.crc       = CRC()
        self.aes       = AES()
        self.sha3      = SHA3()
        self.trng      = TRNG()
        self.field_alu = FieldALU()
        self.ntt       = NTT()
        self.kem       = KEM()
        self.fb        = Framebuffer()

        # ── Build the device bus ─────────────────────────────────
        self.bus = DeviceBus()
        self.bus.register(MMIO_UART,      0x100, self.uart)
        self.bus.register(MMIO_TIMER,     0x100, self.timer)
        self.bus.register(MMIO_STORAGE,   0x100, self.storage)
        self.bus.register(MMIO_SYSINFO,   0x100, self.sysinfo)
        self.bus.register(MMIO_NIC,       0x100, self.nic)
        self.bus.register(MMIO_MAILBOX,   0x100, self.mailbox)
        self.bus.register(MMIO_DMA,       0x100, self.dma)
        self.bus.register(MMIO_CRC,       0x20,  self.crc)
        self.bus.register(MMIO_AES,       0x80,  self.aes)
        self.bus.register(MMIO_SHA3,      0x40,  self.sha3)
        self.bus.register(MMIO_TRNG,      0x40,  self.trng)
        self.bus.register(MMIO_FIELD_ALU, 0x48,  self.field_alu)
        self.bus.register(MMIO_NTT,       0x40,  self.ntt)
        self.bus.register(MMIO_KEM,       0x40,  self.kem)
        self.bus.register(MMIO_FB,        0x100, self.fb)

        # ── Wire MMIO bus to every MP64 core ─────────────────────
        for core in self.mp64.cores:
            core.mmio_read = self.bus.read
            core.mmio_write = self.bus.write

        # ── Wire DMA/Storage memory callbacks to shared RAM ──────
        def mem_r(addr: int) -> int:
            return mp64_mem[addr % len(mp64_mem)]

        def mem_w(addr: int, val: int):
            mp64_mem[addr % len(mp64_mem)] = val & 0xFF

        self.storage._mem_read = mem_r
        self.storage._mem_write = mem_w
        self.dma._mem_read = mem_r
        self.dma._mem_write = mem_w

    # ── Simulation ───────────────────────────────────────────────
    def step(self) -> int:
        """Step all cores and tiles once, advance timer, check IRQs."""
        n = self.mp64.step()
        n += self.lm1.step()
        # Advance timer once per step
        fired = self.timer.tick()
        if fired:
            self._deliver_timer_irq()
        return n

    def _deliver_timer_irq(self):
        """Route timer IRQ to first non-halted MP64 core with IE=1."""
        for core in self.mp64.cores:
            if not core.halted and core.flag_i:
                core._trap(IVEC_TIMER)
                return

    def run(self, max_steps: int = 100_000) -> int:
        """Run until all halted or max_steps."""
        total = 0
        while total < max_steps:
            if self.mp64.all_halted and self.lm1.all_halted:
                break
            total += self.step()
        return total

    @property
    def all_halted(self) -> bool:
        return self.mp64.all_halted and self.lm1.all_halted

    # ── UART convenience ─────────────────────────────────────────
    def uart_output(self) -> str:
        """Read all characters from the UART TX FIFO."""
        return self.uart.drain_tx().decode("utf-8", errors="replace")

    # ── Cross-domain messaging helpers ───────────────────────────
    def mp64_send(self, from_core: int, dest_ep: int,
                  msg_type: int, payload: bytes = b"") -> bool:
        """Send a bridge message from an MP64 core."""
        env = Envelope(
            source_id=mp64_endpoint(from_core),
            dest_id=dest_ep,
            msg_type=msg_type,
            payload_len=len(payload),
            payload=payload,
        )
        return self.bridge.send(env)

    def lm1_send(self, from_tile: int, dest_ep: int,
                 msg_type: int, payload: bytes = b"") -> bool:
        """Send a bridge message from an LM-1 tile."""
        env = Envelope(
            source_id=lm1_endpoint(from_tile),
            dest_id=dest_ep,
            msg_type=msg_type,
            payload_len=len(payload),
            payload=payload,
        )
        return self.bridge.send(env)

    def drain_bridge(self, max_msgs: int = 64) -> int:
        """Process pending bridge messages (deliver to HW queues).

        Returns number of messages processed.
        """
        processed = 0
        for _ in range(max_msgs):
            # Check each MP64 core inbox
            for i in range(self.mp64.n_cores):
                msg = self.mp64.recv_bridge_msg(i)
                if msg:
                    processed += 1
            # Check each LM-1 tile inbox
            for i in range(self.lm1.n_tiles):
                msg = self.lm1.recv_bridge_msg(i)
                if msg:
                    # Deposit into tile's queue 0 (bridge channel)
                    self.lm1.inject_to_queue(i, 0, msg.msg_type)
                    processed += 1
            if processed == 0:
                break
        return processed
