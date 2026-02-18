"""Chimera-1 SoC: unified MP64 + LM-1 emulator with χ-Bridge.

Ties together MP64Cluster, LM1Cluster, and ChiBridge into a single
system that can be stepped or run as one unit.
"""
from __future__ import annotations
from chimera.bridge import (
    ChiBridge, Envelope, mp64_endpoint, lm1_endpoint,
    DOMAIN_MP64, DOMAIN_LM1, endpoint_domain,
)
from chimera.mp64.cluster import MP64Cluster
from chimera.lm1.cluster import LM1Cluster


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
        self.bridge = ChiBridge()
        self.mp64 = MP64Cluster(mp64_mem, mp64_cores, bridge=self.bridge)
        self.lm1 = LM1Cluster(lm1_tiles, lm1_tile_memsz, bridge=self.bridge)

    def step(self) -> int:
        """Step all cores and tiles once."""
        n = self.mp64.step()
        n += self.lm1.step()
        return n

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
