"""Stage E: Forth BIOS — label-aware assembler + interactive Forth REPL.

Tests progress from assembler unit tests up through full Forth evaluation.
"""
from __future__ import annotations

import pytest

from chimera.mp64.assembler import MP64Asm
from chimera.mp64 import asm
from chimera.bios import ForthBIOS
from chimera.soc import ChimeraSoC


# ═══════════════════════════════════════════════════════════════════
#  Assembler unit tests
# ═══════════════════════════════════════════════════════════════════

class TestMP64Asm:
    """Label-aware assembler: forward refs, LDI64, LBR, BR patches."""

    def test_label_round_trip(self):
        a = MP64Asm()
        addr = a.label("foo")
        assert addr == 0
        assert a.labels["foo"] == 0

    def test_label_with_base(self):
        a = MP64Asm(base=0x1000)
        a.emit(asm.nop())
        addr = a.label("bar")
        assert addr == 0x1001

    def test_duplicate_label_raises(self):
        a = MP64Asm()
        a.label("x")
        with pytest.raises(ValueError, match="duplicate"):
            a.label("x")

    def test_ldi64_literal(self):
        a = MP64Asm()
        a.LDI64(5, 0xDEAD)
        rom = a.assemble()
        assert len(rom) == 11
        assert rom == bytearray(asm.ldi64(5, 0xDEAD))

    def test_ldi64_label_forward(self):
        """Forward reference resolved on assemble."""
        a = MP64Asm()
        a.LDI64(1, "target")
        a.emit(asm.halt())              # 1 byte
        a.label("target")
        a.emit(asm.nop())
        rom = a.assemble()
        # target PC = 11 (ldi64) + 1 (halt) = 12
        expected = asm.ldi64(1, 12)
        assert rom[:11] == bytearray(expected)

    def test_ldi64_label_backward(self):
        a = MP64Asm()
        a.label("top")
        a.emit(asm.nop())
        a.LDI64(2, "top")
        rom = a.assemble()
        assert rom[1:12] == bytearray(asm.ldi64(2, 0))

    def test_br_forward(self):
        a = MP64Asm()
        a.BR(asm.AL, "skip")
        a.emit(asm.nop())
        a.label("skip")
        a.emit(asm.halt())
        rom = a.assemble()
        # BR is 2 bytes, offset from end-of-insn (pc=2) to skip (pc=3) → +1
        assert rom[0] == 0x30              # br AL
        assert rom[1] == 1                 # offset

    def test_br_backward(self):
        a = MP64Asm()
        a.label("loop")
        a.emit(asm.nop())
        a.BR(asm.AL, "loop")
        rom = a.assemble()
        # BR at offset 1, insn ends at 3, target is 0 → offset = -3
        assert rom[2] == (-3) & 0xFF

    def test_lbr_forward(self):
        a = MP64Asm()
        a.LBR(asm.EQ, "far")
        a.emit(bytes(100))
        a.label("far")
        rom = a.assemble()
        # LBR is 3 bytes, target at 103, offset = 103 - 3 = 100
        off = 100
        assert rom[1] == (off >> 8) & 0xFF
        assert rom[2] == off & 0xFF

    def test_undefined_label_raises(self):
        a = MP64Asm()
        a.LDI64(0, "nowhere")
        with pytest.raises(ValueError, match="undefined"):
            a.assemble()

    def test_data_directives(self):
        a = MP64Asm()
        a.db(0xAA, 0xBB)
        a.dw(0x1234)
        a.dd(0xDEADBEEF)
        a.dq(0x0102030405060708)
        rom = a.assemble()
        assert rom[0:2] == bytes([0xAA, 0xBB])
        assert rom[2:4] == (0x1234).to_bytes(2, "little")
        assert rom[4:8] == (0xDEADBEEF).to_bytes(4, "little")
        assert rom[8:16] == (0x0102030405060708).to_bytes(8, "little")

    def test_ascii_and_asciiz(self):
        a = MP64Asm()
        a.ascii("Hi")
        a.asciiz("Ok")
        rom = a.assemble()
        assert rom == bytearray(b"HiOk\x00")

    def test_align(self):
        a = MP64Asm()
        a.db(0xFF)
        a.align(8)
        assert a.pc == 8

    def test_call_l_label(self):
        a = MP64Asm()
        a.CALL_L_LABEL("fn")
        a.emit(asm.halt())
        a.label("fn")
        a.emit(asm.ret_l())
        rom = a.assemble()
        # 11 (ldi64 r11) + 2 (call.l r11) + 1 (halt) = 14 → fn at 14
        assert rom[:11] == bytearray(asm.ldi64(11, 14))
        assert rom[11:13] == bytearray(asm.call_l(11))


# ═══════════════════════════════════════════════════════════════════
#  BIOS ROM build
# ═══════════════════════════════════════════════════════════════════

class TestBIOSBuild:
    """ForthBIOS.build() produces a valid ROM without errors."""

    def test_build_succeeds(self):
        bios = ForthBIOS(ram_size=1 << 20)
        rom = bios.build()
        assert isinstance(rom, bytearray)
        assert len(rom) > 256

    def test_rom_fits_in_ram(self):
        ram = 1 << 20
        bios = ForthBIOS(ram_size=ram)
        rom = bios.build()
        assert len(rom) < ram // 2, "ROM must fit well below the data stack"

    def test_banner_present_in_rom(self):
        bios = ForthBIOS(ram_size=1 << 20)
        rom = bios.build()
        assert b"Chimera-1 Forth BIOS v0.1" in rom

    def test_dictionary_labels(self):
        bios = ForthBIOS(ram_size=1 << 20)
        bios.build()
        # Check some dictionary entries exist
        for name in ["DUP", "DROP", "+", ".", "EMIT", ":", ";"]:
            safe = name.replace("+", "plus").replace("-", "minus") \
                        .replace(".", "dot").replace(":", "colon") \
                        .replace(";", "semi")
            lbl = f"w_{safe.lower()}"
            assert lbl in bios.a.labels, f"missing word label: {lbl}"

    def test_key_labels_defined(self):
        bios = ForthBIOS(ram_size=1 << 20)
        bios.build()
        for lbl in ["_start", "quit_loop", "var_state", "var_base",
                     "var_here", "var_latest", "tib_buffer", "dict_free",
                     "emit_char", "key_char", "print_str", "find_word",
                     "parse_number", "print_number", "compile_byte"]:
            assert lbl in bios.a.labels, f"missing label: {lbl}"


# ═══════════════════════════════════════════════════════════════════
#  Helpers — SoC harness
# ═══════════════════════════════════════════════════════════════════

def _make_soc(ram_size: int = 1 << 20) -> ChimeraSoC:
    """Build a ChimeraSoC loaded with the Forth BIOS ROM."""
    bios = ForthBIOS(ram_size=ram_size)
    rom = bios.build()
    mem = bytearray(ram_size)
    mem[:len(rom)] = rom
    soc = ChimeraSoC(mem, mp64_cores=1, lm1_tiles=1)
    return soc


def _run_until_input(soc: ChimeraSoC, max_steps: int = 2_000_000) -> str:
    """Run until the core blocks polling for UART RX (key_char loop)
    or halts. Returns UART output text collected so far.

    Detection: run batches of steps, check if TX output has stopped
    growing while RX is empty — that means the core is spinning in
    the key_char poll loop waiting for input.
    """
    core = soc.mp64.cores[0]
    BATCH = 50_000
    total = 0
    prev_tx_len = len(soc.uart.tx_buf)
    stall_count = 0

    while total < max_steps:
        if core.halted:
            break
        for _ in range(BATCH):
            if core.halted:
                break
            soc.step()
        total += BATCH

        cur_tx_len = len(soc.uart.tx_buf)
        if cur_tx_len == prev_tx_len and len(soc.uart.rx_buf) == 0:
            stall_count += 1
            if stall_count >= 5:
                break
        else:
            stall_count = 0
        prev_tx_len = cur_tx_len

    return soc.uart_output()


def _send_line(soc: ChimeraSoC, text: str, max_steps: int = 2_000_000) -> str:
    """Send a line of text (with CR terminator) to the UART, run until
    the core waits for input again. Returns NEW UART output."""
    # Clear any existing output
    soc.uart_output()
    # Push chars + CR
    for ch in text:
        soc.uart.push_rx(ord(ch))
    soc.uart.push_rx(0x0D)  # CR
    return _run_until_input(soc, max_steps)


# ═══════════════════════════════════════════════════════════════════
#  Boot & banner test
# ═══════════════════════════════════════════════════════════════════

class TestBIOSBoot:
    """Verify the BIOS boots and prints its banner."""

    def test_banner_printed(self):
        soc = _make_soc()
        output = _run_until_input(soc)
        assert "Chimera-1 Forth BIOS v0.1" in output

    def test_prompt_shown(self):
        soc = _make_soc()
        output = _run_until_input(soc)
        assert "> " in output


# ═══════════════════════════════════════════════════════════════════
#  Forth arithmetic & evaluation
# ═══════════════════════════════════════════════════════════════════

class TestForthArithmetic:
    """Basic Forth arithmetic via the outer interpreter."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)  # consume banner + first prompt

    def test_add(self):
        out = _send_line(self.soc, "3 4 +  .")
        assert "7 " in out

    def test_subtract(self):
        out = _send_line(self.soc, "10 3 - .")
        assert "7 " in out

    def test_multiply(self):
        out = _send_line(self.soc, "6 7 * .")
        assert "42 " in out

    def test_negate(self):
        out = _send_line(self.soc, "5 NEGATE .")
        assert "-5 " in out

    def test_ok_printed(self):
        out = _send_line(self.soc, "1 2 +  .")
        assert "ok" in out

    def test_hex_literal(self):
        out = _send_line(self.soc, "0xFF .")
        assert "255 " in out

    def test_negative_literal(self):
        out = _send_line(self.soc, "-42 .")
        assert "-42 " in out


# ═══════════════════════════════════════════════════════════════════
#  Stack operations
# ═══════════════════════════════════════════════════════════════════

class TestForthStack:
    """Stack manipulation words."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)

    def test_dup(self):
        out = _send_line(self.soc, "5 DUP . .")
        assert "5 5 " in out

    def test_drop(self):
        out = _send_line(self.soc, "1 2 DROP .")
        assert "1 " in out

    def test_swap(self):
        out = _send_line(self.soc, "1 2 SWAP . .")
        assert "1 2 " in out

    def test_over(self):
        out = _send_line(self.soc, "1 2 OVER . . .")
        assert "1 2 1 " in out

    def test_depth(self):
        out = _send_line(self.soc, "10 20 30 DEPTH .")
        # Depth should be 3 (10, 20, 30 on stack before DEPTH)
        assert "3 " in out


# ═══════════════════════════════════════════════════════════════════
#  Colon definitions
# ═══════════════════════════════════════════════════════════════════

class TestForthColon:
    """User-defined words via : and ;."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)

    def test_simple_colon(self):
        _send_line(self.soc, ": DOUBLE 2 * ;")
        out = _send_line(self.soc, "5 DOUBLE .")
        assert "10 " in out

    def test_colon_multiple_words(self):
        _send_line(self.soc, ": SQUARE DUP * ;")
        out = _send_line(self.soc, "7 SQUARE .")
        assert "49 " in out

    def test_colon_chain(self):
        _send_line(self.soc, ": DOUBLE 2 * ;")
        _send_line(self.soc, ": QUAD DOUBLE DOUBLE ;")
        out = _send_line(self.soc, "3 QUAD .")
        assert "12 " in out


# ═══════════════════════════════════════════════════════════════════
#  Control flow
# ═══════════════════════════════════════════════════════════════════

class TestForthControl:
    """IF/THEN, BEGIN/UNTIL control structures."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)

    def test_if_then_true(self):
        _send_line(self.soc, ": TEST 1 IF 42 THEN ;")
        out = _send_line(self.soc, "TEST .")
        assert "42 " in out

    def test_if_then_false(self):
        _send_line(self.soc, ": TEST2 0 IF 42 THEN 99 ;")
        out = _send_line(self.soc, "TEST2 .")
        assert "99 " in out

    def test_if_else_then(self):
        _send_line(self.soc, ": SIGN DUP 0= IF DROP 0 ELSE 0< IF -1 ELSE 1 THEN THEN ;")
        out = _send_line(self.soc, "5 SIGN .")
        assert "1 " in out

    def test_begin_until(self):
        # Count down from 3, push each value
        _send_line(self.soc, ": COUNTDOWN 3 BEGIN DUP . 1- DUP 0= UNTIL DROP ;")
        out = _send_line(self.soc, "COUNTDOWN")
        assert "3 " in out
        assert "2 " in out
        assert "1 " in out


# ═══════════════════════════════════════════════════════════════════
#  Memory & variables
# ═══════════════════════════════════════════════════════════════════

class TestForthMemory:
    """Memory access and VARIABLE/CONSTANT words."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)

    def test_constant(self):
        _send_line(self.soc, "42 CONSTANT ANSWER")
        out = _send_line(self.soc, "ANSWER .")
        assert "42 " in out

    def test_cells(self):
        out = _send_line(self.soc, "3 CELLS .")
        assert "24 " in out


# ═══════════════════════════════════════════════════════════════════
#  I/O words
# ═══════════════════════════════════════════════════════════════════

class TestForthIO:
    """I/O words: EMIT, CR, SPACE, .S."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)

    def test_emit(self):
        out = _send_line(self.soc, "65 EMIT")
        assert "A" in out

    def test_space(self):
        out = _send_line(self.soc, "SPACE")
        assert " " in out

    def test_cr(self):
        out = _send_line(self.soc, "CR")
        assert "\r\n" in out

    def test_dot_s_empty(self):
        out = _send_line(self.soc, ".S")
        assert "<0>" in out

    def test_dot_s_values(self):
        out = _send_line(self.soc, "1 2 3 .S")
        assert "<3>" in out


# ═══════════════════════════════════════════════════════════════════
#  System words
# ═══════════════════════════════════════════════════════════════════

class TestForthSystem:
    """System words: HEX, DECIMAL, BYE, WORDS."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)

    def test_hex_mode(self):
        out = _send_line(self.soc, "255 HEX .")
        assert "ff " in out.lower()

    def test_decimal_mode(self):
        _send_line(self.soc, "HEX")
        _send_line(self.soc, "DECIMAL")
        out = _send_line(self.soc, "255 .")
        assert "255 " in out

    def test_bye_halts(self):
        soc = self.soc
        # Clear output
        soc.uart_output()
        for ch in "BYE":
            soc.uart.push_rx(ord(ch))
        soc.uart.push_rx(0x0D)
        soc.run(max_steps=2_000_000)
        assert soc.mp64.cores[0].halted

    def test_undefined_word_error(self):
        out = _send_line(self.soc, "XYZZY")
        assert "?" in out


# ═══════════════════════════════════════════════════════════════════
#  Logic / comparison
# ═══════════════════════════════════════════════════════════════════

class TestForthLogic:
    """Comparison and logic words."""

    @pytest.fixture(autouse=True)
    def boot(self):
        self.soc = _make_soc()
        _run_until_input(self.soc)

    def test_equals_true(self):
        out = _send_line(self.soc, "5 5 = .")
        assert "-1 " in out

    def test_equals_false(self):
        out = _send_line(self.soc, "3 4 = .")
        assert "0 " in out

    def test_less_than(self):
        out = _send_line(self.soc, "3 5 < .")
        assert "-1 " in out

    def test_greater_than(self):
        out = _send_line(self.soc, "5 3 > .")
        assert "-1 " in out

    def test_and(self):
        out = _send_line(self.soc, "0xFF 0x0F AND .")
        assert "15 " in out

    def test_invert(self):
        out = _send_line(self.soc, "0 INVERT 1 AND .")
        assert "1 " in out
