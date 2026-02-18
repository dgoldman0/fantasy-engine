"""Label-aware MP64 assembler.

Wraps the raw encoding helpers in ``asm.py`` with:
  - named labels (forward and backward references)
  - two-pass resolution for LDI64, LBR, and BR targets
  - data directives (.db, .dw, .dq, .ascii, .asciiz)
  - PC tracking relative to a configurable base address

Typical usage::

    a = MP64Asm()
    a.label("start")
    a.emit(asm.nop())
    a.LDI64(11, "handler")
    a.emit(asm.call_l(11))
    a.emit(asm.halt())
    a.label("handler")
    a.emit(asm.ret_l())
    rom = a.assemble()
"""
from __future__ import annotations
from chimera.mp64 import asm


class MP64Asm:
    """Two-pass MP64 assembler with label support."""

    def __init__(self, base: int = 0):
        self.buf = bytearray()
        self.base = base
        self.labels: dict[str, int] = {}
        self._fixups: list[tuple] = []  # (buf_off, label, type, *args)

    # ── address helpers ──────────────────────────────────────────
    @property
    def pc(self) -> int:
        """Current programme counter (base + bytes emitted so far)."""
        return self.base + len(self.buf)

    def here(self) -> int:
        """Alias for *pc*."""
        return self.pc

    # ── labels ───────────────────────────────────────────────────
    def label(self, name: str) -> int:
        """Define *name* at the current PC.  Returns the PC value."""
        if name in self.labels:
            raise ValueError(f"duplicate label: {name}")
        self.labels[name] = self.pc
        return self.pc

    # ── raw emission ─────────────────────────────────────────────
    def emit(self, *args: bytes | bytearray | int) -> None:
        """Append raw bytes/ints to the output."""
        for a in args:
            if isinstance(a, (bytes, bytearray)):
                self.buf.extend(a)
            else:
                self.buf.append(a & 0xFF)

    # ── data directives ──────────────────────────────────────────
    def db(self, *vals: int) -> None:
        for v in vals:
            self.buf.append(v & 0xFF)

    def dw(self, *vals: int) -> None:
        """16-bit little-endian."""
        for v in vals:
            self.buf.extend((v & 0xFFFF).to_bytes(2, "little"))

    def dd(self, *vals: int) -> None:
        """32-bit little-endian."""
        for v in vals:
            self.buf.extend((v & 0xFFFF_FFFF).to_bytes(4, "little"))

    def dq(self, *vals: int) -> None:
        """64-bit little-endian."""
        for v in vals:
            self.buf.extend((v & 0xFFFF_FFFF_FFFF_FFFF).to_bytes(8, "little"))

    def ascii(self, s: str) -> None:
        self.buf.extend(s.encode("ascii"))

    def asciiz(self, s: str) -> None:
        self.buf.extend(s.encode("ascii"))
        self.buf.append(0)

    def align(self, boundary: int = 8) -> None:
        """Pad with NOPs to align *pc* to *boundary*."""
        while self.pc % boundary:
            self.buf.append(0x01)  # NOP

    def pad_to(self, addr: int) -> None:
        """Pad with zeros until *pc* == *addr*."""
        while self.pc < addr:
            self.buf.append(0x00)

    # ── label-aware instruction wrappers ─────────────────────────

    def LDI64(self, rn: int, target: str | int) -> None:
        """``EXT.IMM64`` + ``LDI rn`` — label or literal."""
        if isinstance(target, str):
            self._fixups.append((len(self.buf), target, "ldi64", rn))
            self.emit(asm.ldi64(rn, 0))              # placeholder
        else:
            self.emit(asm.ldi64(rn, target))

    def LBR(self, cc: int, target: str | int) -> None:
        """Long branch — 16-bit signed offset, label or literal."""
        if isinstance(target, str):
            self._fixups.append((len(self.buf), target, "lbr", cc))
            self.emit(asm.lbr(cc, 0))                # placeholder
        else:
            self.emit(asm.lbr(cc, target))

    def BR(self, cc: int, target: str | int) -> None:
        """Short branch — 8-bit signed offset, label or literal."""
        if isinstance(target, str):
            self._fixups.append((len(self.buf), target, "br", cc))
            self.emit(asm.br(cc, 0))                  # placeholder
        else:
            self.emit(asm.br(cc, target))

    # ── convenience: CALL_L with optional label target ───────────

    def CALL_L_LABEL(self, target: str) -> None:
        """``ldi64 r11, <target>; call.l r11``."""
        self.LDI64(11, target)
        self.emit(asm.call_l(11))

    # ── resolution ───────────────────────────────────────────────

    def resolve(self) -> None:
        """Patch all forward references.  Raises on undefined labels."""
        for fixup in self._fixups:
            buf_off = fixup[0]
            label   = fixup[1]
            ftype   = fixup[2]

            if label not in self.labels:
                raise ValueError(f"undefined label: {label}")
            addr = self.labels[label]

            if ftype == "ldi64":
                rn = fixup[3]
                patch = asm.ldi64(rn, addr)
                self.buf[buf_off : buf_off + len(patch)] = patch

            elif ftype == "lbr":
                cc = fixup[3]
                insn_end = self.base + buf_off + 3
                rel = addr - insn_end
                if rel < -32768 or rel > 32767:
                    raise ValueError(
                        f"LBR target {label} offset {rel} out of ±32 KiB"
                    )
                patch = asm.lbr(cc, rel & 0xFFFF)
                self.buf[buf_off : buf_off + 3] = patch

            elif ftype == "br":
                cc = fixup[3]
                insn_end = self.base + buf_off + 2
                rel = addr - insn_end
                if rel < -128 or rel > 127:
                    raise ValueError(
                        f"BR target {label} offset {rel} out of ±128"
                    )
                patch = asm.br(cc, rel & 0xFF)
                self.buf[buf_off : buf_off + 2] = patch

    def assemble(self) -> bytearray:
        """Resolve fixups and return the finished bytecode."""
        self.resolve()
        return bytearray(self.buf)
