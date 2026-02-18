"""MP64 multi-core cluster with IPI, barriers, and spinlocks.

Manages N MP64Core instances sharing the same memory, with:
  - Inter-Processor Interrupts (IPI) via CSRs 0x22/0x23
  - Hardware barrier (CSR 0x74/0x75)
  - 8 hardware spinlocks (MMIO offset 0x0600)
"""
from __future__ import annotations
from chimera.mp64.core import MP64Core
from chimera.devices.bus import DeviceBus
from chimera.bridge import ChiBridge, Envelope, mp64_endpoint


class MP64Cluster:
    """Multi-core MP64 cluster."""

    def __init__(self, mem: bytearray, n_cores: int = 4, *,
                 bridge: ChiBridge | None = None):
        self.mem = mem
        self.n_cores = n_cores
        self.bridge = bridge

        # Create cores
        self.cores: list[MP64Core] = []
        for i in range(n_cores):
            c = MP64Core(mem, core_id=i, n_cores=n_cores)
            self.cores.append(c)

        # IPI state: per-core pending mask (bit N = pending from core N)
        self.ipi_pending = [0] * n_cores

        # Hardware barrier
        self.barrier_arrived = 0    # bitmask: bit i = core i arrived
        self.barrier_done = False

        # 8 hardware spinlocks (0 = free, owner_core+1 = held)
        self.spinlocks = [0] * 8

        # Wire CSR hooks for IPI/barrier into each core
        for c in self.cores:
            self._wire_csr(c)

        # Register bridge endpoints
        if bridge:
            for i in range(n_cores):
                bridge.register_endpoint(mp64_endpoint(i))

    def _wire_csr(self, core: MP64Core):
        """Install CSR hooks for IPI and barrier on a core."""
        cluster = self
        cid = core.core_id

        def csr_read_hook(addr: int):
            a = addr & 0xFF
            if a == 0x22:  return cluster.ipi_pending[cid]
            if a == 0x74:  return cluster.barrier_arrived
            if a == 0x75:  return 1 if cluster.barrier_done else 0
            return None   # fall through to default

        def csr_write_hook(addr: int, val: int) -> bool:
            a = addr & 0xFF
            if a == 0x22:  # MBOX: send IPI to core N
                target = val & 0xFF
                if 0 <= target < cluster.n_cores:
                    cluster.ipi_pending[target] |= (1 << cid)
                return True
            if a == 0x23:  # IPIACK
                src = val & 0xFF
                cluster.ipi_pending[cid] &= ~(1 << src)
                return True
            if a == 0x74:  # BARRIER_ARRIVE
                cluster.barrier_arrived |= (1 << cid)
                all_mask = (1 << cluster.n_cores) - 1
                if cluster.barrier_arrived == all_mask:
                    cluster.barrier_done = True
                return True
            return False  # not handled → default

        core.csr_read_hook = csr_read_hook
        core.csr_write_hook = csr_write_hook

    def reset_barrier(self):
        """Reset the barrier for the next phase."""
        self.barrier_arrived = 0
        self.barrier_done = False

    def step(self) -> int:
        """Step all non-halted cores once (round-robin)."""
        total = 0
        for core in self.cores:
            if not core.halted:
                total += core.step()
        return total

    def run(self, max_steps: int = 100_000) -> int:
        """Run all cores until all halted or max_steps total."""
        total = 0
        while total < max_steps:
            alive = sum(1 for c in self.cores if not c.halted)
            if alive == 0:
                break
            total += self.step()
        return total

    @property
    def all_halted(self) -> bool:
        return all(c.halted for c in self.cores)

    def send_bridge_msg(self, from_core: int, envelope: Envelope) -> bool:
        """Send a message through the χ-Bridge."""
        if self.bridge is None:
            return False
        envelope.source_id = mp64_endpoint(from_core)
        return self.bridge.send(envelope)

    def recv_bridge_msg(self, core_id: int) -> Envelope | None:
        """Receive a bridge message for a core."""
        if self.bridge is None:
            return None
        return self.bridge.recv(mp64_endpoint(core_id))
