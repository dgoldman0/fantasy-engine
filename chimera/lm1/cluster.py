"""LM-1 multi-tile cluster.

Manages N LM1Core tiles, each with independent memory.
Cross-tile messaging routes through the χ-Bridge.
"""
from __future__ import annotations
from chimera.lm1.core import LM1Core
from chimera.bridge import ChiBridge, Envelope, lm1_endpoint


class LM1Cluster:
    """Multi-tile LM-1 cluster."""

    def __init__(self, n_tiles: int = 8, tile_memsz: int = 1 << 20, *,
                 bridge: ChiBridge | None = None):
        self.n_tiles = n_tiles
        self.bridge = bridge
        self.tiles: list[LM1Core] = []

        for i in range(n_tiles):
            mem = bytearray(tile_memsz)
            tile = LM1Core(mem, tile_id=i)
            tile.init_nursery()
            self.tiles.append(tile)

        # Register bridge endpoints
        if bridge:
            for i in range(n_tiles):
                bridge.register_endpoint(lm1_endpoint(i))

    def step(self) -> int:
        """Step all non-halted tiles once (round-robin)."""
        total = 0
        for tile in self.tiles:
            if not tile.thread.halted:
                total += tile.step()
        return total

    def run(self, max_steps: int = 100_000) -> int:
        """Run all tiles until all halted or max_steps total."""
        total = 0
        while total < max_steps:
            alive = sum(1 for t in self.tiles if not t.thread.halted)
            if alive == 0:
                break
            total += self.step()
        return total

    @property
    def all_halted(self) -> bool:
        return all(t.thread.halted for t in self.tiles)

    def send_bridge_msg(self, from_tile: int, envelope: Envelope) -> bool:
        """Send a message through the χ-Bridge."""
        if self.bridge is None:
            return False
        envelope.source_id = lm1_endpoint(from_tile)
        return self.bridge.send(envelope)

    def recv_bridge_msg(self, tile_id: int) -> Envelope | None:
        """Receive a bridge message for a tile."""
        if self.bridge is None:
            return None
        return self.bridge.recv(lm1_endpoint(tile_id))

    def inject_to_queue(self, tile_id: int, queue_id: int, value: int):
        """Push a value into a tile's hardware queue (from bridge)."""
        if 0 <= tile_id < self.n_tiles:
            q = self.tiles[tile_id].queues[queue_id]
            if len(q) < q.maxlen:
                q.append(value)
