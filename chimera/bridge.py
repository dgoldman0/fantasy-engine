"""χ-Bridge: cross-domain messaging layer between MP64 and LM-1.

Implements 64-byte message envelopes that route between MP64 cores
and LM-1 tiles.  Each endpoint has a bounded inbox queue.
"""
from __future__ import annotations
import struct
from collections import deque
from dataclasses import dataclass, field


# ── Message type codes ───────────────────────────────────────────────
MSG_WORK_REQ     = 0x01
MSG_WORK_RESP    = 0x02
MSG_CRYPTO_REQ   = 0x03
MSG_CRYPTO_RESP  = 0x04
MSG_GC_PAUSE     = 0x05
MSG_GC_RESUME    = 0x06
MSG_EVID_WITNESS = 0x07
MSG_EVID_QUERY   = 0x08
MSG_EVID_DATA    = 0x09
MSG_STATUS_REQ   = 0x0A
MSG_STATUS_RESP  = 0x0B
MSG_EVAL_REQ     = 0x0C
MSG_EVAL_RESP    = 0x0D
MSG_SIMD_REQ     = 0x0E
MSG_SIMD_RESP    = 0x0F
MSG_SHUTDOWN     = 0x10

# ── Flags ────────────────────────────────────────────────────────────
FLAG_NEEDS_REPLY = 0x01
FLAG_PRIORITY    = 0x02

# ── Endpoint namespace ──────────────────────────────────────────────
# source_id / dest_id encoding:
#   bits 31:16 = domain (0 = MP64, 1 = LM-1)
#   bits 15:8  = cluster/core group
#   bits  7:0  = core/tile/thread index

DOMAIN_MP64 = 0
DOMAIN_LM1  = 1

def make_endpoint(domain: int, group: int, index: int) -> int:
    return (domain << 16) | ((group & 0xFF) << 8) | (index & 0xFF)

def mp64_endpoint(core_id: int) -> int:
    return make_endpoint(DOMAIN_MP64, 0, core_id)

def lm1_endpoint(tile_id: int, thread_id: int = 0) -> int:
    return make_endpoint(DOMAIN_LM1, tile_id, thread_id)

def endpoint_domain(ep: int) -> int:
    return (ep >> 16) & 0xFFFF

def endpoint_index(ep: int) -> int:
    return ep & 0xFF

def endpoint_group(ep: int) -> int:
    return (ep >> 8) & 0xFF


@dataclass
class Envelope:
    """64-byte cross-domain message envelope."""
    source_id:   int = 0
    dest_id:     int = 0
    msg_type:    int = 0
    flags:       int = 0
    payload_len: int = 0
    payload:     bytes = b""

    def pack(self) -> bytes:
        """Serialize to 64 bytes."""
        p = self.payload[:32].ljust(32, b"\x00")
        return struct.pack("<QQIIQ32s",
            self.source_id, self.dest_id,
            self.msg_type, self.flags,
            self.payload_len, p,
        )

    @classmethod
    def unpack(cls, data: bytes) -> "Envelope":
        """Deserialize from 64 bytes."""
        src, dst, mtype, flags, plen, payload = struct.unpack("<QQIIQ32s", data[:64])
        return cls(src, dst, mtype, flags, plen, payload.rstrip(b"\x00"))

    @classmethod
    def from_mem(cls, mem: bytearray, addr: int) -> "Envelope":
        return cls.unpack(bytes(mem[addr:addr+64]))

    def to_mem(self, mem: bytearray, addr: int):
        mem[addr:addr+64] = self.pack()


class ChiBridge:
    """Central message router for the Chimera-1 SoC.

    Routes envelopes between MP64 core inboxes and LM-1 tile queues.
    Each endpoint has a bounded FIFO inbox (default depth 16).
    """

    def __init__(self, *, inbox_depth: int = 16):
        self.inbox_depth = inbox_depth
        # Inboxes keyed by endpoint ID
        self._inboxes: dict[int, deque[Envelope]] = {}
        # Optional callbacks: {endpoint → callable(Envelope)}
        self._ipi_hooks: dict[int, list] = {}
        # Stats
        self.messages_routed = 0
        self.messages_dropped = 0

    def _get_inbox(self, ep: int) -> deque[Envelope]:
        if ep not in self._inboxes:
            self._inboxes[ep] = deque(maxlen=self.inbox_depth)
        return self._inboxes[ep]

    def register_endpoint(self, ep: int):
        """Pre-register an endpoint (creates empty inbox)."""
        self._get_inbox(ep)

    def register_ipi_hook(self, ep: int, hook):
        """Register a callback invoked when a message arrives at *ep*."""
        self._ipi_hooks.setdefault(ep, []).append(hook)

    def send(self, envelope: Envelope) -> bool:
        """Route an envelope to its destination inbox.

        Returns True if delivered, False if inbox full (message dropped).
        """
        inbox = self._get_inbox(envelope.dest_id)
        if len(inbox) >= self.inbox_depth:
            self.messages_dropped += 1
            return False
        inbox.append(envelope)
        self.messages_routed += 1
        # Fire IPI hooks
        for hook in self._ipi_hooks.get(envelope.dest_id, []):
            hook(envelope)
        return True

    def recv(self, ep: int) -> Envelope | None:
        """Non-blocking receive from an endpoint's inbox."""
        inbox = self._get_inbox(ep)
        return inbox.popleft() if inbox else None

    def pending(self, ep: int) -> int:
        """Number of messages waiting in an endpoint's inbox."""
        return len(self._get_inbox(ep))

    def broadcast(self, envelope: Envelope, endpoints: list[int]) -> int:
        """Send a copy of the envelope to multiple endpoints.

        Returns the number of successful deliveries.
        """
        delivered = 0
        for ep in endpoints:
            env_copy = Envelope(
                source_id=envelope.source_id,
                dest_id=ep,
                msg_type=envelope.msg_type,
                flags=envelope.flags,
                payload_len=envelope.payload_len,
                payload=envelope.payload,
            )
            if self.send(env_copy):
                delivered += 1
        return delivered
