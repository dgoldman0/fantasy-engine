"""Chimera-1 Forth BIOS ROM builder.

Generates an MP64 ROM image containing a complete subroutine-threaded
Forth interpreter compatible with the MegaPad BIOS architecture:

  - Register conventions: R14=DSP (data stack), R15=RSP (return stack),
    R8=UART base address.
  - Dictionary: linked list with [link:8][flags+len:1][name:N][code].
  - Subroutine-threaded: CALL.L/RET.L, no NEXT/DOCOL.
  - 60+ core Forth words: stack, arithmetic, logic, memory, I/O,
    compiler, control flow, string output.

Usage::

    bios = ForthBIOS(ram_size=1 << 20)
    rom = bios.build()
    mem = bytearray(1 << 20)
    mem[:len(rom)] = rom
"""
from __future__ import annotations
from chimera.mp64.assembler import MP64Asm
from chimera.mp64 import asm

# ── MMIO addresses (must match chimera/soc.py) ──────────────────
MMIO_BASE  = 0xFFFF_FF00_0000_0000
UART_TX    = MMIO_BASE + 0x0000
UART_RX    = MMIO_BASE + 0x0001
UART_STAT  = MMIO_BASE + 0x0002
SYSINFO    = MMIO_BASE + 0x0300

# Condition codes
AL = asm.AL; EQ = asm.EQ; NE = asm.NE
CS = asm.CS; CC = asm.CC; MI = asm.MI; PL = asm.PL
GT = asm.GT; LE = asm.LE


class ForthBIOS:
    """Build the Chimera-1 Forth BIOS ROM image."""

    def __init__(self, ram_size: int = 1 << 20):
        self.ram_size = ram_size
        self.a = MP64Asm(base=0)
        self._latest_addr: int = 0          # link chain (0 = end)
        self._dict_entries: list[str] = []  # names for verification

    # ==================================================================
    #  Public API
    # ==================================================================

    def build(self) -> bytearray:
        """Assemble the complete BIOS and return the ROM image."""
        self._emit_boot()
        self._emit_helpers()
        self._emit_dictionary()
        self._emit_quit()
        self._emit_data()
        return self.a.assemble()

    # ==================================================================
    #  Boot code
    # ==================================================================

    def _emit_boot(self):
        a = self.a
        a.label("_start")

        # ── Set SPSEL = 15 so CALL.L/RET.L use R15 ─────────────
        a.emit(asm.ldi(1, 15))
        a.emit(asm.csrw(1, 0x03))           # CSR[0x03] = SPSEL = 15

        # ── Switch PC from R0 to R4 so R0 is free as scratch ───
        a.LDI64(4, "after_sep")             # R4 = addr after SEP
        a.emit(asm.sep(4))                  # PSEL = 4 → R4 is now PC
        a.label("after_sep")

        # ── R15 = RSP = ram_top (return stack grows down) ────────
        a.LDI64(15, self.ram_size)

        # ── R14 = DSP = ram_size / 2 (data stack grows down) ────
        a.LDI64(14, self.ram_size // 2)

        # ── R8 = UART TX base ───────────────────────────────────
        a.LDI64(8, UART_TX)

        # ── Initialise Forth variables ──────────────────────────
        # STATE = 0
        a.emit(asm.ldi(1, 0))
        a.LDI64(11, "var_state")
        a.emit(asm.str_(11, 1))

        # BASE = 10
        a.emit(asm.ldi(1, 10))
        a.LDI64(11, "var_base")
        a.emit(asm.str_(11, 1))

        # HERE = dict_free
        a.LDI64(1, "dict_free")
        a.LDI64(11, "var_here")
        a.emit(asm.str_(11, 1))

        # LATEST = latest_entry (patched during assembly)
        a.LDI64(1, "latest_entry")
        a.LDI64(11, "var_latest")
        a.emit(asm.str_(11, 1))

        # >IN = 0
        a.emit(asm.ldi(1, 0))
        a.LDI64(11, "var_to_in")
        a.emit(asm.str_(11, 1))

        # TIB_LEN = 0
        a.LDI64(11, "var_tib_len")
        a.emit(asm.str_(11, 1))

        # ── Print banner ────────────────────────────────────────
        a.LDI64(10, "str_banner")
        a.CALL_L_LABEL("print_str")

        # ── Enter outer interpreter ─────────────────────────────
        a.LBR(AL, "quit_loop")

    # ==================================================================
    #  Helper routines
    # ==================================================================

    def _emit_helpers(self):
        self._emit_emit_char()
        self._emit_key()
        self._emit_print_str()
        self._emit_print_crlf()
        self._emit_read_line()
        self._emit_parse_word()
        self._emit_find_word()
        self._emit_entry_to_code()
        self._emit_parse_number()
        self._emit_print_number()
        self._emit_compile_byte()
        self._emit_compile_literal()
        self._emit_compile_call()

    # ── EMIT character (R1 byte → UART) ─────────────────────────
    def _emit_emit_char(self):
        a = self.a
        a.label("emit_char")
        # st.b R8, R1  (mem[R8] = R1, R8 = UART TX)
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ret_l())

    # ── KEY (UART RX → R1), blocks until byte available ─────────
    def _emit_key(self):
        a = self.a
        a.label("key_char")
        # Poll UART_STAT until bit 1 (RX avail) is set
        a.label("key_poll")
        a.LDI64(11, UART_STAT)
        a.emit(asm.ld_b(1, 11))
        a.emit(asm.andi(1, 0x02))
        a.BR(EQ, "key_poll")
        # Read RX byte
        a.LDI64(11, UART_RX)
        a.emit(asm.ld_b(1, 11))
        a.emit(asm.ret_l())

    # ── print_str: null-terminated string at R10 ────────────────
    def _emit_print_str(self):
        a = self.a
        a.label("print_str")
        a.label("ps_loop")
        a.emit(asm.ld_b(1, 10))
        a.emit(asm.cmpi(1, 0))
        a.BR(EQ, "ps_done")
        a.emit(asm.st_b(8, 1))
        a.emit(asm.inc(10))
        a.BR(AL, "ps_loop")
        a.label("ps_done")
        a.emit(asm.ret_l())

    # ── print_crlf ──────────────────────────────────────────────
    def _emit_print_crlf(self):
        a = self.a
        a.label("print_crlf")
        a.emit(asm.ldi(1, 0x0D))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldi(1, 0x0A))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ret_l())

    # ── read_line: read UART into TIB buffer, R12 = length ──────
    def _emit_read_line(self):
        a = self.a
        a.label("read_line")
        a.LDI64(9, "tib_buffer")
        a.emit(asm.ldi(12, 0))             # len = 0

        a.label("rl_loop")
        a.CALL_L_LABEL("key_char")
        # CR (0x0D) → done
        a.emit(asm.cmpi(1, 0x0D))
        a.BR(EQ, "rl_done")
        # LF (0x0A) → done
        a.emit(asm.cmpi(1, 0x0A))
        a.BR(EQ, "rl_done")
        # Backspace (0x08 or 0x7F)
        a.emit(asm.cmpi(1, 0x08))
        a.BR(EQ, "rl_bs")
        a.emit(asm.cmpi(1, 0x7F))
        a.BR(EQ, "rl_bs")
        # Store character
        a.emit(asm.cmpi(12, 250))            # max 250 chars
        a.BR(EQ, "rl_loop")                  # full → ignore
        a.emit(asm.mov(11, 9))
        a.emit(asm.add(11, 12))
        a.emit(asm.st_b(11, 1))
        a.emit(asm.inc(12))
        # Echo
        a.emit(asm.st_b(8, 1))
        a.BR(AL, "rl_loop")

        a.label("rl_bs")
        a.emit(asm.cmpi(12, 0))
        a.BR(EQ, "rl_loop")
        a.emit(asm.dec(12))
        # Echo BS-SPACE-BS
        a.emit(asm.ldi(1, 0x08))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldi(1, 0x08))
        a.emit(asm.st_b(8, 1))
        a.BR(AL, "rl_loop")

        a.label("rl_done")
        # Save TIB length
        a.LDI64(11, "var_tib_len")
        a.emit(asm.str_(11, 12))
        a.emit(asm.ret_l())

    # ── parse_word: skip spaces, delimit next token ─────────────
    #   Input:  var_to_in, tib_buffer, var_tib_len
    #   Output: R9=word addr, R12=word length (0 = EOL)
    def _emit_parse_word(self):
        a = self.a
        a.label("parse_word")
        a.LDI64(11, "var_to_in")
        a.emit(asm.ldn(13, 11))             # R13 = >IN
        a.LDI64(9, "tib_buffer")
        a.LDI64(11, "var_tib_len")
        a.emit(asm.ldn(0, 11))              # R0 = TIB_LEN

        # skip leading spaces
        a.label("pw_skip")
        a.emit(asm.cmp(13, 0))
        a.BR(EQ, "pw_eol")                  # actually >= not eq
        # need unsigned compare: if R13 >= R0, eol
        a.emit(asm.mov(7, 13))
        a.emit(asm.sub(7, 0))
        a.BR(PL, "pw_eol")                  # R13 >= R0 → EOL
        # load char
        a.emit(asm.mov(11, 9))
        a.emit(asm.add(11, 13))
        a.emit(asm.ld_b(7, 11))
        a.emit(asm.cmpi(7, 0x20))           # space
        a.BR(NE, "pw_found")
        a.emit(asm.inc(13))
        a.BR(AL, "pw_skip")

        a.label("pw_eol")
        # end of line
        a.emit(asm.ldi(12, 0))             # length = 0
        a.LDI64(11, "var_to_in")
        a.emit(asm.str_(11, 13))
        a.emit(asm.ret_l())

        a.label("pw_found")
        # R13 = start of word, save it
        a.emit(asm.mov(12, 13))             # R12 = start pos

        a.label("pw_scan")
        # if >= TIB_LEN, end
        a.emit(asm.mov(7, 13))
        a.emit(asm.sub(7, 0))
        a.BR(PL, "pw_end")                  # R13 >= R0 → end
        a.emit(asm.mov(11, 9))
        a.emit(asm.add(11, 13))
        a.emit(asm.ld_b(7, 11))
        a.emit(asm.cmpi(7, 0x20))
        a.BR(EQ, "pw_end")
        a.emit(asm.inc(13))
        a.BR(AL, "pw_scan")

        a.label("pw_end")
        # Update >IN
        a.LDI64(11, "var_to_in")
        a.emit(asm.str_(11, 13))
        # R9 = TIB + start
        a.LDI64(9, "tib_buffer")
        a.emit(asm.add(9, 12))
        # R12 = length = current(R13) - start(R12)
        a.emit(asm.mov(0, 13))
        a.emit(asm.sub(0, 12))
        a.emit(asm.mov(12, 0))
        a.emit(asm.ret_l())

    # ── find_word: search dict for (R9=name, R12=len) ───────────
    #   Returns R9=entry (0=not found), R1=flags byte
    def _emit_find_word(self):
        a = self.a
        a.label("find_word")
        a.LDI64(11, "var_latest")
        a.emit(asm.ldn(13, 11))             # R13 = current entry

        a.label("fw_loop")
        a.emit(asm.cmpi(13, 0))
        a.BR(EQ, "fw_miss")

        # flags+len at entry+8
        a.emit(asm.mov(11, 13))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ld_b(7, 11))             # R7 = flags|len
        a.emit(asm.mov(0, 7))
        a.emit(asm.andi(0, 0x7F))           # R0 = name length
        a.emit(asm.cmp(0, 12))
        a.BR(NE, "fw_next")

        # Compare names (case-insensitive)
        a.emit(asm.mov(11, 13))
        a.emit(asm.addi(11, 9))             # entry name start
        a.emit(asm.ldi(1, 0))               # index

        a.label("fw_cmp")
        a.emit(asm.cmp(1, 12))
        a.BR(EQ, "fw_hit")
        # entry char → R0
        a.emit(asm.mov(0, 11))
        a.emit(asm.add(0, 1))
        a.emit(asm.ld_b(0, 0))
        # to upper
        a.emit(asm.cmpi(0, 0x61))           # 'a'
        a.BR(CC, "fw_eu1")
        a.emit(asm.cmpi(0, 0x7B))           # 'z'+1
        a.BR(CS, "fw_eu1")
        a.emit(asm.subi(0, 0x20))
        a.label("fw_eu1")
        # search char → R7
        a.emit(asm.mov(7, 9))
        a.emit(asm.add(7, 1))
        a.emit(asm.ld_b(7, 7))
        # to upper
        a.emit(asm.cmpi(7, 0x61))
        a.BR(CC, "fw_eu2")
        a.emit(asm.cmpi(7, 0x7B))
        a.BR(CS, "fw_eu2")
        a.emit(asm.subi(7, 0x20))
        a.label("fw_eu2")
        a.emit(asm.cmp(0, 7))
        a.BR(NE, "fw_next")
        a.emit(asm.inc(1))
        a.BR(AL, "fw_cmp")

        a.label("fw_hit")
        a.emit(asm.mov(9, 13))              # R9 = entry
        a.emit(asm.mov(11, 13))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ld_b(1, 11))             # R1 = flags byte
        a.emit(asm.ret_l())

        a.label("fw_next")
        a.emit(asm.ldn(13, 13))             # follow link
        a.BR(AL, "fw_loop")

        a.label("fw_miss")
        a.emit(asm.ldi(9, 0))
        a.emit(asm.ret_l())

    # ── entry_to_code: R9=entry → R9=code body address ──────────
    def _emit_entry_to_code(self):
        a = self.a
        a.label("entry_to_code")
        a.emit(asm.mov(11, 9))
        a.emit(asm.addi(11, 8))             # skip link
        a.emit(asm.ld_b(0, 11))             # flags+len
        a.emit(asm.andi(0, 0x7F))           # name length
        a.emit(asm.addi(11, 1))             # skip flags byte
        a.emit(asm.add(11, 0))              # skip name
        a.emit(asm.mov(9, 11))
        a.emit(asm.ret_l())

    # ── parse_number: word (R9, R12) → R1=value, R0=1 success ──
    def _emit_parse_number(self):
        a = self.a
        a.label("parse_number")
        a.emit(asm.ldi(1, 0))               # accumulator
        a.emit(asm.ldi(0, 0))               # sign flag
        a.emit(asm.mov(10, 9))              # R10 = ptr
        a.emit(asm.mov(13, 12))             # R13 = remaining len

        # Check for '-' prefix
        a.emit(asm.cmpi(13, 0))
        a.LBR(EQ, "pn_fail")
        a.emit(asm.ld_b(7, 10))
        a.emit(asm.cmpi(7, 0x2D))           # '-'
        a.BR(NE, "pn_check_hex")
        a.emit(asm.ldi(0, 1))               # sign = 1
        a.emit(asm.inc(10))
        a.emit(asm.dec(13))
        a.emit(asm.cmpi(13, 0))
        a.LBR(EQ, "pn_fail")

        # Check for '0x' prefix
        a.label("pn_check_hex")
        a.emit(asm.cmpi(13, 2))
        a.LBR(MI, "pn_base")                # len < 2 → use base
        a.emit(asm.ld_b(7, 10))
        a.emit(asm.cmpi(7, 0x30))           # '0'
        a.BR(NE, "pn_base")
        a.emit(asm.mov(11, 10))
        a.emit(asm.inc(11))
        a.emit(asm.ld_b(7, 11))
        a.emit(asm.cmpi(7, 0x78))           # 'x'
        a.BR(EQ, "pn_hex_start")
        a.emit(asm.cmpi(7, 0x58))           # 'X'
        a.BR(EQ, "pn_hex_start")
        a.BR(AL, "pn_base")

        # Hex parsing
        a.label("pn_hex_start")
        a.emit(asm.addi(10, 2))
        a.emit(asm.subi(13, 2))
        a.emit(asm.cmpi(13, 0))
        a.LBR(EQ, "pn_fail")
        a.emit(asm.ldi(1, 0))

        a.label("pn_hex_loop")
        a.emit(asm.cmpi(13, 0))
        a.BR(EQ, "pn_done")
        a.emit(asm.ld_b(7, 10))
        # '0'-'9'
        a.emit(asm.cmpi(7, 0x30))
        a.LBR(CC, "pn_fail")
        a.emit(asm.cmpi(7, 0x3A))           # '9'+1
        a.BR(CS, "pn_hex_alpha")
        a.emit(asm.subi(7, 0x30))
        a.BR(AL, "pn_hex_accum")

        a.label("pn_hex_alpha")
        # 'A'-'F'
        a.emit(asm.cmpi(7, 0x41))
        a.LBR(CC, "pn_fail")
        a.emit(asm.cmpi(7, 0x47))           # 'F'+1
        a.BR(CS, "pn_hex_lower")
        a.emit(asm.subi(7, 0x37))           # 'A'-10
        a.BR(AL, "pn_hex_accum")

        a.label("pn_hex_lower")
        # 'a'-'f'
        a.emit(asm.cmpi(7, 0x61))
        a.LBR(CC, "pn_fail")
        a.emit(asm.cmpi(7, 0x67))           # 'f'+1
        a.LBR(CS, "pn_fail")
        a.emit(asm.subi(7, 0x57))           # 'a'-10

        a.label("pn_hex_accum")
        a.emit(asm.lsli(1, 4))
        a.emit(asm.or_(1, 7))
        a.emit(asm.inc(10))
        a.emit(asm.dec(13))
        a.BR(AL, "pn_hex_loop")

        # Decimal parsing using BASE
        a.label("pn_base")
        # Load BASE
        a.LDI64(11, "var_base")
        a.emit(asm.ldn(3, 11))              # R3 = BASE
        a.emit(asm.ldi(1, 0))               # accumulator

        a.label("pn_dec_loop")
        a.emit(asm.cmpi(13, 0))
        a.BR(EQ, "pn_done")
        a.emit(asm.ld_b(7, 10))
        a.emit(asm.subi(7, 0x30))           # digit = char - '0'
        a.emit(asm.cmpi(7, 0))
        a.LBR(MI, "pn_fail")                # < 0
        a.emit(asm.cmp(7, 3))
        a.LBR(PL, "pn_fail")                # >= BASE
        # accum = accum * BASE + digit
        a.emit(asm.mul(1, 3))
        a.emit(asm.add(1, 7))
        a.emit(asm.inc(10))
        a.emit(asm.dec(13))
        a.BR(AL, "pn_dec_loop")

        a.label("pn_done")
        # Apply sign
        a.emit(asm.cmpi(0, 0))
        a.BR(EQ, "pn_success")
        a.emit(asm.neg(1, 1))

        a.label("pn_success")
        a.emit(asm.ldi(0, 1))               # success
        a.emit(asm.ret_l())

        a.label("pn_fail")
        a.emit(asm.ldi(0, 0))               # failure
        a.emit(asm.ret_l())

    # ── print_number: R1 = signed 64-bit value → UART ───────────
    def _emit_print_number(self):
        a = self.a
        a.label("print_number")
        # Simple: use a 20-char buffer on return stack
        # We always print in current BASE

        # Check sign
        a.emit(asm.cmpi(1, 0))
        a.BR(PL, "pn_pr_pos")
        # Negative: print '-' and negate
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 1))              # save value
        a.emit(asm.ldi(1, 0x2D))            # '-'
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldn(1, 15))
        a.emit(asm.addi(15, 8))
        a.emit(asm.neg(1, 1))

        a.label("pn_pr_pos")
        # Use a small 24-byte buffer at [R15-24..R15-1]
        a.emit(asm.subi(15, 24))
        a.emit(asm.mov(10, 15))             # R10 = buf start
        a.emit(asm.ldi(12, 0))              # digit count

        # Load BASE → R3
        a.LDI64(11, "var_base")
        a.emit(asm.ldn(3, 11))

        a.label("pn_pr_div")
        # R1 / BASE → quotient R1, remainder in separate calc
        # Use UMOD to get remainder, UDIV for quotient
        a.emit(asm.mov(7, 1))               # save dividend
        a.emit(asm.umod(7, 3))              # R7 = R1 % BASE (remainder)
        a.emit(asm.udiv(1, 3))              # R1 = R1 / BASE (quotient)
        # Convert digit to ASCII
        a.emit(asm.cmpi(7, 10))
        a.BR(CS, "pn_pr_hex_digit")
        a.emit(asm.addi(7, 0x30))           # '0'+digit
        a.BR(AL, "pn_pr_store")
        a.label("pn_pr_hex_digit")
        a.emit(asm.addi(7, 0x57))           # 'a'-10+digit
        a.label("pn_pr_store")
        # Store in buffer
        a.emit(asm.mov(11, 10))
        a.emit(asm.add(11, 12))
        a.emit(asm.st_b(11, 7))
        a.emit(asm.inc(12))
        # Continue while quotient > 0
        a.emit(asm.cmpi(1, 0))
        a.BR(NE, "pn_pr_div")

        # Print digits in reverse order
        a.label("pn_pr_out")
        a.emit(asm.cmpi(12, 0))
        a.BR(EQ, "pn_pr_end")
        a.emit(asm.dec(12))
        a.emit(asm.mov(11, 10))
        a.emit(asm.add(11, 12))
        a.emit(asm.ld_b(1, 11))
        a.emit(asm.st_b(8, 1))
        a.BR(AL, "pn_pr_out")

        a.label("pn_pr_end")
        a.emit(asm.addi(15, 24))            # deallocate buffer
        a.emit(asm.ret_l())

    # ── compile_byte: emit R1 at HERE, advance HERE ─────────────
    def _emit_compile_byte(self):
        a = self.a
        a.label("compile_byte")
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(2, 11))              # R2 = HERE
        a.emit(asm.st_b(2, 1))              # mem[HERE] = R1
        a.emit(asm.inc(2))
        a.emit(asm.str_(11, 2))             # HERE++
        a.emit(asm.ret_l())

    # ── compile_literal: emit code that pushes R1 at runtime ────
    #   Emits: ldi64 r1, <value>; subi r14, 8; str r14, r1
    def _emit_compile_literal(self):
        a = self.a
        a.label("compile_literal")
        # Save R1 (the value to compile)
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 1))

        # Emit: EXT.IMM64 (0xF0)
        a.emit(asm.ldi(1, 0xF0))
        a.CALL_L_LABEL("compile_byte")
        # Emit: LDI R1 (0x60, 0x01)
        a.emit(asm.ldi(1, 0x60))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x01))
        a.CALL_L_LABEL("compile_byte")

        # Emit 8 bytes of the immediate value (little-endian)
        a.emit(asm.ldn(0, 15))              # reload saved value
        # byte 0
        a.emit(asm.mov(1, 0))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        # byte 1
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        # byte 2
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        # byte 3
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        # byte 4
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        # byte 5
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        # byte 6
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        # byte 7
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")

        # Emit: subi r14, 8 (0x67, 0x0E, 0x08)
        a.emit(asm.ldi(1, 0x67))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")

        # Emit: str r14, r1 (0x54, 0xE1)
        a.emit(asm.ldi(1, 0x54))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0xE1))
        a.CALL_L_LABEL("compile_byte")

        a.emit(asm.addi(15, 8))             # pop saved value
        a.emit(asm.ret_l())

    # ── compile_call: emit ldi64 r11, R1; call.l r11 ────────────
    def _emit_compile_call(self):
        a = self.a
        a.label("compile_call")
        # R1 = code address to call
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 1))

        # Emit ldi64 r11, <addr>
        # F0 60 0B + 8 bytes LE
        a.emit(asm.ldi(1, 0xF0))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x60))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0B))            # r11 = 0xB
        a.CALL_L_LABEL("compile_byte")

        # 8 bytes of address
        a.emit(asm.ldn(0, 15))
        a.emit(asm.mov(1, 0))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")

        # Emit call.l r11 (0x0D, 0x0B)
        a.emit(asm.ldi(1, 0x0D))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0B))
        a.CALL_L_LABEL("compile_byte")

        a.emit(asm.addi(15, 8))
        a.emit(asm.ret_l())

    # ==================================================================
    #  Dictionary
    # ==================================================================

    def _dict_entry(self, name: str, *, immediate: bool = False) -> str:
        """Emit a dictionary header (link + flags + name).

        Returns the label for the code body (caller must emit code).
        The link field points to the previous entry (chained).
        """
        safe = name.replace("+", "plus").replace("-", "minus") \
                    .replace("*", "star").replace("/", "slash") \
                    .replace("!", "store").replace("@", "fetch") \
                    .replace(".", "dot").replace(",", "comma") \
                    .replace(":", "colon").replace(";", "semi") \
                    .replace("<", "lt").replace(">", "gt") \
                    .replace("=", "eq").replace("?", "q") \
                    .replace("\\", "bslash").replace("'", "tick") \
                    .replace("[", "lbrak").replace("]", "rbrak") \
                    .replace('"', "dquot")
        entry_lbl = f"d_{safe.lower()}"
        code_lbl  = f"w_{safe.lower()}"

        a = self.a
        a.label(entry_lbl)

        # Link → previous entry
        a.dq(self._latest_addr)
        self._latest_addr = a.labels[entry_lbl]

        # Flags + len
        flags_byte = len(name) & 0x7F
        if immediate:
            flags_byte |= 0x80
        a.db(flags_byte)

        # Name (uppercase ASCII)
        a.ascii(name.upper())

        # Code body label
        a.label(code_lbl)

        self._dict_entries.append(name)
        return code_lbl

    def _emit_dictionary(self):
        """Emit all built-in dictionary entries."""
        self._emit_stack_words()
        self._emit_arith_words()
        self._emit_comparison_words()
        self._emit_logic_words()
        self._emit_memory_words()
        self._emit_io_words()
        self._emit_compiler_words()
        self._emit_control_words()
        self._emit_system_words()

    # ── Stack manipulation ──────────────────────────────────────
    def _emit_stack_words(self):
        a = self.a

        # DUP ( x -- x x )
        self._dict_entry("DUP")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # DROP ( x -- )
        self._dict_entry("DROP")
        a.emit(asm.addi(14, 8))
        a.emit(asm.ret_l())

        # SWAP ( x y -- y x )
        self._dict_entry("SWAP")
        a.emit(asm.ldn(1, 14))              # y
        a.emit(asm.mov(11, 14))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ldn(0, 11))              # x
        a.emit(asm.str_(14, 0))             # TOS = x
        a.emit(asm.str_(11, 1))             # NOS = y
        a.emit(asm.ret_l())

        # OVER ( x y -- x y x )
        self._dict_entry("OVER")
        a.emit(asm.mov(11, 14))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ldn(1, 11))
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # ROT ( x y z -- y z x )
        self._dict_entry("ROT")
        a.emit(asm.ldn(1, 14))              # z
        a.emit(asm.mov(11, 14))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ldn(0, 11))              # y
        a.emit(asm.mov(7, 14))
        a.emit(asm.addi(7, 16))
        a.emit(asm.ldn(13, 7))              # x
        a.emit(asm.str_(7, 0))              # [+16] = y
        a.emit(asm.str_(11, 1))             # [+8]  = z
        a.emit(asm.str_(14, 13))            # [+0]  = x
        a.emit(asm.ret_l())

        # ?DUP ( x -- x x | 0 )
        self._dict_entry("?DUP")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.cmpi(1, 0))
        a.BR(EQ, "qdup_done")
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.label("qdup_done")
        a.emit(asm.ret_l())

        # DEPTH ( -- n )
        self._dict_entry("DEPTH")
        a.LDI64(1, self.ram_size // 2)
        a.emit(asm.sub(1, 14))
        a.emit(asm.lsri(1, 3))              # divide by 8
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # 2DUP ( x y -- x y x y )
        self._dict_entry("2DUP")
        a.emit(asm.mov(11, 14))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ldn(1, 11))              # x
        a.emit(asm.ldn(0, 14))              # y
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))             # push x
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 0))             # push y
        a.emit(asm.ret_l())

        # 2DROP ( x y -- )
        self._dict_entry("2DROP")
        a.emit(asm.addi(14, 16))
        a.emit(asm.ret_l())

        # NIP ( x y -- y )
        self._dict_entry("NIP")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # TUCK ( x y -- y x y )
        self._dict_entry("TUCK")
        a.emit(asm.ldn(1, 14))              # y
        a.emit(asm.mov(11, 14))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ldn(0, 11))              # x
        a.emit(asm.str_(11, 1))             # NOS = y
        a.emit(asm.str_(14, 0))             # TOS = x
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))             # push y
        a.emit(asm.ret_l())

        # PICK ( n -- x )
        self._dict_entry("PICK")
        a.emit(asm.ldn(1, 14))              # n
        a.emit(asm.lsli(1, 3))              # n*8
        a.emit(asm.addi(1, 8))              # +8 (skip PICK's own slot)
        a.emit(asm.add(1, 14))
        a.emit(asm.ldn(1, 1))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

    # ── Arithmetic ──────────────────────────────────────────────
    def _emit_arith_words(self):
        a = self.a

        # + ( a b -- a+b )
        self._dict_entry("+")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.add(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # - ( a b -- a-b )
        self._dict_entry("-")
        a.emit(asm.ldn(1, 14))              # b
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))              # a
        a.emit(asm.sub(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # * ( a b -- a*b )
        self._dict_entry("*")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.mul(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # / ( a b -- a/b )
        self._dict_entry("/")
        a.emit(asm.ldn(1, 14))             # b
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))             # a
        a.emit(asm.div(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # MOD ( a b -- a%b )
        self._dict_entry("MOD")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.mod(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # NEGATE ( n -- -n )
        self._dict_entry("NEGATE")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.neg(1, 1))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # ABS ( n -- |n| )
        self._dict_entry("ABS")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.cmpi(1, 0))
        a.BR(PL, "abs_done")
        a.emit(asm.neg(1, 1))
        a.emit(asm.str_(14, 1))
        a.label("abs_done")
        a.emit(asm.ret_l())

        # 1+ ( n -- n+1 )
        self._dict_entry("1+")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(1, 1))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # 1- ( n -- n-1 )
        self._dict_entry("1-")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.subi(1, 1))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # MAX ( a b -- max )
        self._dict_entry("MAX")
        a.emit(asm.ldn(1, 14))             # b
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))             # a
        a.emit(asm.cmp(0, 1))
        a.BR(GT, "max_a")
        a.emit(asm.str_(14, 1))            # b is max
        a.emit(asm.ret_l())
        a.label("max_a")
        # a already in [R14]
        a.emit(asm.ret_l())

        # MIN ( a b -- min )
        self._dict_entry("MIN")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.cmp(0, 1))
        a.BR(LE, "min_a")
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())
        a.label("min_a")
        a.emit(asm.ret_l())

    # ── Comparison ──────────────────────────────────────────────
    def _emit_comparison_words(self):
        a = self.a

        # = ( a b -- flag )
        self._dict_entry("=")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.cmp(0, 1))
        a.emit(asm.ldi(1, 0))
        a.BR(NE, "eq_done")
        a.emit(asm.dec(1))                  # -1 (true)
        a.label("eq_done")
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # < ( a b -- flag )  signed
        self._dict_entry("<")
        a.emit(asm.ldn(1, 14))             # b
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))             # a
        a.emit(asm.cmp(0, 1))
        a.emit(asm.ldi(1, 0))
        a.BR(PL, "lt_done")                # a >= b → false
        a.emit(asm.dec(1))
        a.label("lt_done")
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # > ( a b -- flag )  signed
        self._dict_entry(">")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.cmp(0, 1))
        a.emit(asm.ldi(1, 0))
        a.BR(LE, "gt_done")
        a.emit(asm.dec(1))
        a.label("gt_done")
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # 0= ( x -- flag )
        self._dict_entry("0=")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.cmpi(1, 0))
        a.emit(asm.ldi(1, 0))
        a.BR(NE, "zeq_done")
        a.emit(asm.dec(1))
        a.label("zeq_done")
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # 0< ( x -- flag )
        self._dict_entry("0<")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.cmpi(1, 0))
        a.emit(asm.ldi(1, 0))
        a.BR(PL, "zlt_done")
        a.emit(asm.dec(1))
        a.label("zlt_done")
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # <> ( a b -- flag )
        self._dict_entry("<>")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.cmp(0, 1))
        a.emit(asm.ldi(1, 0))
        a.BR(EQ, "neq_done")
        a.emit(asm.dec(1))
        a.label("neq_done")
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

    # ── Logic / bitwise ─────────────────────────────────────────
    def _emit_logic_words(self):
        a = self.a

        # AND ( a b -- a&b )
        self._dict_entry("AND")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.and_(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # OR ( a b -- a|b )
        self._dict_entry("OR")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.or_(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # XOR ( a b -- a^b )
        self._dict_entry("XOR")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.xor(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # INVERT ( x -- ~x )
        self._dict_entry("INVERT")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.not_(1, 1))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # LSHIFT ( x n -- x<<n )
        self._dict_entry("LSHIFT")
        a.emit(asm.ldn(1, 14))             # n
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))             # x
        a.emit(asm.shl(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # RSHIFT ( x n -- x>>n )
        self._dict_entry("RSHIFT")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))
        a.emit(asm.shr(0, 1))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

    # ── Memory access ───────────────────────────────────────────
    def _emit_memory_words(self):
        a = self.a

        # @ ( addr -- value )  64-bit fetch
        self._dict_entry("@")
        a.emit(asm.ldn(1, 14))             # addr
        a.emit(asm.ldn(1, 1))              # value = mem[addr]
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # ! ( value addr -- )  64-bit store
        self._dict_entry("!")
        a.emit(asm.ldn(1, 14))             # addr
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))             # value
        a.emit(asm.addi(14, 8))
        a.emit(asm.str_(1, 0))             # mem[addr] = value
        a.emit(asm.ret_l())

        # C@ ( addr -- byte )
        self._dict_entry("C@")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.ld_b(1, 1))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # C! ( byte addr -- )
        self._dict_entry("C!")
        a.emit(asm.ldn(1, 14))             # addr
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))             # byte
        a.emit(asm.addi(14, 8))
        a.emit(asm.st_b(1, 0))
        a.emit(asm.ret_l())

        # HERE ( -- addr )
        self._dict_entry("HERE")
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # ALLOT ( n -- )
        self._dict_entry("ALLOT")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(0, 11))
        a.emit(asm.add(0, 1))
        a.emit(asm.str_(11, 0))
        a.emit(asm.ret_l())

        # , ( x -- )  compile 64-bit value
        self._dict_entry(",")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(0, 11))
        a.emit(asm.str_(0, 1))             # mem[HERE] = x
        a.emit(asm.addi(0, 8))
        a.emit(asm.str_(11, 0))            # HERE += 8
        a.emit(asm.ret_l())

        # C, ( byte -- )  compile 1 byte
        self._dict_entry("C,")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # +! ( n addr -- )  add n to [addr]
        self._dict_entry("+!")
        a.emit(asm.ldn(1, 14))             # addr
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(0, 14))             # n
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(7, 1))              # old value
        a.emit(asm.add(7, 0))
        a.emit(asm.str_(1, 7))
        a.emit(asm.ret_l())

        # CELLS ( n -- n*8 )
        self._dict_entry("CELLS")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.lsli(1, 3))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # CELL+ ( addr -- addr+8 )
        self._dict_entry("CELL+")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(1, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

    # ── I/O words ───────────────────────────────────────────────
    def _emit_io_words(self):
        a = self.a

        # EMIT ( char -- )
        self._dict_entry("EMIT")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ret_l())

        # KEY ( -- char )
        self._dict_entry("KEY")
        a.CALL_L_LABEL("key_char")
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # KEY? ( -- flag )
        self._dict_entry("KEY?")
        a.LDI64(11, UART_STAT)
        a.emit(asm.ld_b(1, 11))
        a.emit(asm.andi(1, 0x02))
        a.emit(asm.ldi(0, 0))
        a.emit(asm.cmpi(1, 0))
        a.BR(EQ, "keyq_done")
        a.emit(asm.dec(0))                  # -1
        a.label("keyq_done")
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # CR ( -- )
        self._dict_entry("CR")
        a.CALL_L_LABEL("print_crlf")
        a.emit(asm.ret_l())

        # . ( n -- )  print number followed by space
        self._dict_entry(".")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.CALL_L_LABEL("print_number")
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ret_l())

        # U. ( u -- )  print unsigned
        self._dict_entry("U.")
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        # For unsigned, we just call print_number (which handles positives)
        # If negative as signed, the number will print as large positive in base
        a.CALL_L_LABEL("print_number")
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ret_l())

        # SPACE ( -- )
        self._dict_entry("SPACE")
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ret_l())

        # TYPE ( addr len -- )
        self._dict_entry("TYPE")
        a.emit(asm.ldn(12, 14))            # len
        a.emit(asm.addi(14, 8))
        a.emit(asm.ldn(10, 14))            # addr
        a.emit(asm.addi(14, 8))
        a.label("type_loop")
        a.emit(asm.cmpi(12, 0))
        a.BR(EQ, "type_done")
        a.emit(asm.ld_b(1, 10))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.inc(10))
        a.emit(asm.dec(12))
        a.BR(AL, "type_loop")
        a.label("type_done")
        a.emit(asm.ret_l())

        # .S ( -- )  print stack contents
        self._dict_entry(".S")
        # Print <n>
        a.emit(asm.ldi(1, 0x3C))           # '<'
        a.emit(asm.st_b(8, 1))
        # Calculate depth
        a.LDI64(1, self.ram_size // 2)
        a.emit(asm.sub(1, 14))
        a.emit(asm.lsri(1, 3))
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 1))             # save depth
        a.CALL_L_LABEL("print_number")
        a.emit(asm.ldi(1, 0x3E))           # '>'
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        # Print each element bottom-up
        a.emit(asm.ldn(12, 15))             # depth
        a.emit(asm.addi(15, 8))
        a.emit(asm.cmpi(12, 0))
        a.BR(EQ, "dots_done")
        # bottom = DSP + (depth-1)*8
        a.emit(asm.mov(10, 12))
        a.emit(asm.subi(10, 1))
        a.emit(asm.lsli(10, 3))
        a.emit(asm.add(10, 14))
        a.label("dots_loop")
        a.emit(asm.ldn(1, 10))
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 10))
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 12))
        a.CALL_L_LABEL("print_number")
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldn(12, 15))
        a.emit(asm.addi(15, 8))
        a.emit(asm.ldn(10, 15))
        a.emit(asm.addi(15, 8))
        a.emit(asm.subi(10, 8))
        a.emit(asm.dec(12))
        a.emit(asm.cmpi(12, 0))
        a.BR(NE, "dots_loop")
        a.label("dots_done")
        a.emit(asm.ret_l())

    # ── Compiler words ──────────────────────────────────────────
    def _emit_compiler_words(self):
        a = self.a

        # STATE ( -- addr )
        self._dict_entry("STATE")
        a.LDI64(1, "var_state")
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # : ( "name" -- )  begin colon definition
        self._dict_entry(":")
        # Parse name
        a.CALL_L_LABEL("parse_word")
        a.emit(asm.cmpi(12, 0))
        a.LBR(EQ, "colon_err")

        # Save name addr/len
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 9))             # name addr
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 12))            # name len

        # Build header at HERE
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(0, 11))              # R0 = HERE

        # Save entry start
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 0))

        # Link = current LATEST
        a.LDI64(11, "var_latest")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.str_(0, 1))              # mem[HERE] = LATEST
        a.emit(asm.addi(0, 8))

        # Flags+len
        a.emit(asm.ldn(12, 15))             # restore name len (at RSP+8)
        # Actually we need to be more careful about RSP layout
        # RSP+0 = entry start, RSP+8 = name len, RSP+16 = name addr
        a.emit(asm.mov(7, 15))
        a.emit(asm.addi(7, 8))
        a.emit(asm.ldn(12, 7))              # name len
        a.emit(asm.st_b(0, 12))
        a.emit(asm.inc(0))

        # Copy name
        a.emit(asm.mov(7, 15))
        a.emit(asm.addi(7, 16))
        a.emit(asm.ldn(9, 7))               # name addr
        a.emit(asm.ldi(1, 0))
        a.label("colon_copy")
        a.emit(asm.cmp(1, 12))
        a.BR(EQ, "colon_name_done")
        a.emit(asm.mov(7, 9))
        a.emit(asm.add(7, 1))
        a.emit(asm.ld_b(7, 7))
        # Convert to uppercase
        a.emit(asm.cmpi(7, 0x61))
        a.BR(CC, "colon_no_upper")
        a.emit(asm.cmpi(7, 0x7B))
        a.BR(CS, "colon_no_upper")
        a.emit(asm.subi(7, 0x20))
        a.label("colon_no_upper")
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.inc(1))
        a.BR(AL, "colon_copy")

        a.label("colon_name_done")
        # Update HERE (code starts here)
        a.LDI64(11, "var_here")
        a.emit(asm.str_(11, 0))

        # Set STATE = 1
        a.emit(asm.ldi(1, 1))
        a.LDI64(11, "var_state")
        a.emit(asm.str_(11, 1))

        # Save entry start in var_current, clean RSP
        a.emit(asm.ldn(0, 15))              # entry start (RSP+0)
        a.emit(asm.addi(15, 24))            # pop all 3 saves
        a.LDI64(11, "var_current")
        a.emit(asm.str_(11, 0))             # var_current = entry start

        a.emit(asm.ret_l())

        a.label("colon_err")
        a.LDI64(10, "str_no_name")
        a.CALL_L_LABEL("print_str")
        a.emit(asm.ret_l())

        # ; ( -- )  IMMEDIATE: compile ret.l, finalise definition
        self._dict_entry(";", immediate=True)
        # Compile ret.l
        a.emit(asm.ldi(1, 0x0E))            # ret.l opcode
        a.CALL_L_LABEL("compile_byte")

        # Set LATEST to the entry start (saved in var_current)
        a.LDI64(11, "var_current")
        a.emit(asm.ldn(0, 11))
        a.LDI64(11, "var_latest")
        a.emit(asm.str_(11, 0))

        # Set STATE = 0
        a.emit(asm.ldi(1, 0))
        a.LDI64(11, "var_state")
        a.emit(asm.str_(11, 1))
        a.emit(asm.ret_l())

        # EXIT  IMMEDIATE: compile ret.l
        self._dict_entry("EXIT", immediate=True)
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # VARIABLE ( "name" -- )
        self._dict_entry("VARIABLE")
        a.CALL_L_LABEL("parse_word")
        a.emit(asm.cmpi(12, 0))
        a.LBR(EQ, "colon_err")

        # Build header
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(0, 11))
        a.emit(asm.mov(13, 0))              # save entry start

        # Link
        a.LDI64(11, "var_latest")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.str_(0, 1))
        a.emit(asm.addi(0, 8))

        # Flags+len
        a.emit(asm.st_b(0, 12))
        a.emit(asm.inc(0))

        # Copy name (uppercase)
        a.emit(asm.ldi(1, 0))
        a.label("var_copy")
        a.emit(asm.cmp(1, 12))
        a.BR(EQ, "var_name_done")
        a.emit(asm.mov(7, 9))
        a.emit(asm.add(7, 1))
        a.emit(asm.ld_b(7, 7))
        a.emit(asm.cmpi(7, 0x61))
        a.BR(CC, "var_no_upper")
        a.emit(asm.cmpi(7, 0x7B))
        a.BR(CS, "var_no_upper")
        a.emit(asm.subi(7, 0x20))
        a.label("var_no_upper")
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.inc(1))
        a.BR(AL, "var_copy")

        a.label("var_name_done")
        # Code body: push address of data cell then ret.l
        # The data cell will be right after the ret.l
        # We need to compute its address after all the code
        # Code: ldi64 r1, <data_addr>; subi r14, 8; str r14, r1; ret.l
        # That's 11 + 3 + 2 + 1 = 17 bytes of code
        # data_addr = code_start + 17
        a.emit(asm.mov(10, 0))               # R10 = code_start
        a.emit(asm.addi(10, 17))             # data_addr = code_start + 17

        # Emit: ldi64 r1, <data_addr>
        # F0 60 01 + 8 bytes LE
        a.emit(asm.ldi(7, 0xF0))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.ldi(7, 0x60))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.ldi(7, 0x01))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        # Write 8 bytes of data_addr (R10) little-endian
        a.emit(asm.mov(7, 10))
        a.emit(asm.andi(7, 0xFF))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.mov(7, 10))
        a.emit(asm.lsri(7, 8))
        a.emit(asm.andi(7, 0xFF))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.mov(7, 10))
        a.emit(asm.lsri(7, 8))
        a.emit(asm.lsri(7, 8))
        a.emit(asm.andi(7, 0xFF))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        # Remaining 5 bytes are 0 (addresses < 1MB)
        a.emit(asm.ldi(7, 0))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        # Emit: subi r14, 8 (67 0E 08)
        a.emit(asm.ldi(7, 0x67))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.ldi(7, 0x0E))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.ldi(7, 0x08))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        # Emit: str r14, r1 (54 E1)
        a.emit(asm.ldi(7, 0x54))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.ldi(7, 0xE1))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        # Emit: ret.l (0E)
        a.emit(asm.ldi(7, 0x0E))
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        # Data cell (8 bytes, initialised to 0)
        a.emit(asm.ldi(7, 0))
        a.emit(asm.str_(0, 7))
        a.emit(asm.addi(0, 8))

        # Update HERE
        a.LDI64(11, "var_here")
        a.emit(asm.str_(11, 0))
        # Update LATEST
        a.LDI64(11, "var_latest")
        a.emit(asm.str_(11, 13))
        a.emit(asm.ret_l())

        # CONSTANT ( n "name" -- )
        self._dict_entry("CONSTANT")
        a.emit(asm.ldn(10, 14))             # value → R10
        a.emit(asm.addi(14, 8))
        a.CALL_L_LABEL("parse_word")
        a.emit(asm.cmpi(12, 0))
        a.LBR(EQ, "colon_err")

        # Build header
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(0, 11))
        a.emit(asm.mov(13, 0))

        a.LDI64(11, "var_latest")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.str_(0, 1))
        a.emit(asm.addi(0, 8))
        a.emit(asm.st_b(0, 12))
        a.emit(asm.inc(0))

        a.emit(asm.ldi(1, 0))
        a.label("const_copy")
        a.emit(asm.cmp(1, 12))
        a.BR(EQ, "const_name_done")
        a.emit(asm.mov(7, 9))
        a.emit(asm.add(7, 1))
        a.emit(asm.ld_b(7, 7))
        a.emit(asm.cmpi(7, 0x61))
        a.BR(CC, "const_no_upper")
        a.emit(asm.cmpi(7, 0x7B))
        a.BR(CS, "const_no_upper")
        a.emit(asm.subi(7, 0x20))
        a.label("const_no_upper")
        a.emit(asm.st_b(0, 7))
        a.emit(asm.inc(0))
        a.emit(asm.inc(1))
        a.BR(AL, "const_copy")

        a.label("const_name_done")
        # Update HERE past the header
        a.LDI64(11, "var_here")
        a.emit(asm.str_(11, 0))
        # Code: push constant value then ret.l
        # ldi64 r1, <value>; subi r14, 8; str r14, r1; ret.l
        a.emit(asm.mov(1, 10))
        a.CALL_L_LABEL("compile_literal")

        # compile ret.l
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")

        a.LDI64(11, "var_latest")
        a.emit(asm.str_(11, 13))
        a.emit(asm.ret_l())

        # IMMEDIATE ( -- )
        self._dict_entry("IMMEDIATE")
        a.LDI64(11, "var_latest")
        a.emit(asm.ldn(0, 11))
        a.emit(asm.addi(0, 8))             # flags byte addr
        a.emit(asm.ld_b(1, 0))
        a.emit(asm.ori(1, 0x80))
        a.emit(asm.st_b(0, 1))
        a.emit(asm.ret_l())

        # LITERAL  IMMEDIATE: compile a literal push
        self._dict_entry("LITERAL", immediate=True)
        a.emit(asm.ldn(1, 14))
        a.emit(asm.addi(14, 8))
        a.CALL_L_LABEL("compile_literal")
        a.emit(asm.ret_l())

        # [ IMMEDIATE: set STATE = 0
        self._dict_entry("[", immediate=True)
        a.emit(asm.ldi(1, 0))
        a.LDI64(11, "var_state")
        a.emit(asm.str_(11, 1))
        a.emit(asm.ret_l())

        # ] : set STATE = 1
        self._dict_entry("]")
        a.emit(asm.ldi(1, 1))
        a.LDI64(11, "var_state")
        a.emit(asm.str_(11, 1))
        a.emit(asm.ret_l())

        # ' ( "name" -- xt )  parse and find, push code addr
        self._dict_entry("'")
        a.CALL_L_LABEL("parse_word")
        a.emit(asm.cmpi(12, 0))
        a.LBR(EQ, "tick_fail")
        a.CALL_L_LABEL("find_word")
        a.emit(asm.cmpi(9, 0))
        a.LBR(EQ, "tick_fail")
        a.CALL_L_LABEL("entry_to_code")
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 9))
        a.emit(asm.ret_l())
        a.label("tick_fail")
        a.emit(asm.ldi(1, 0))
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # EXECUTE ( xt -- )
        self._dict_entry("EXECUTE")
        a.emit(asm.ldn(11, 14))
        a.emit(asm.addi(14, 8))
        a.emit(asm.call_l(11))
        a.emit(asm.ret_l())

    # ── Control flow (all IMMEDIATE) ────────────────────────────
    def _emit_control_words(self):
        a = self.a

        # >R ( x -- ) R:( -- x )  IMMEDIATE — compile inline push to RSP
        self._dict_entry(">R", immediate=True)
        # Compile: ldn r1, r14  (50 1E)
        a.emit(asm.ldi(1, 0x50))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x1E))
        a.CALL_L_LABEL("compile_byte")
        # addi r14, 8  (62 0E 08)
        a.emit(asm.ldi(1, 0x62))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # subi r15, 8  (67 0F 08)
        a.emit(asm.ldi(1, 0x67))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0F))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # str r15, r1  (54 F1)
        a.emit(asm.ldi(1, 0x54))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0xF1))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # R> ( -- x ) R:( x -- )  IMMEDIATE
        self._dict_entry("R>", immediate=True)
        # ldn r1, r15  (50 1F)
        a.emit(asm.ldi(1, 0x50))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x1F))
        a.CALL_L_LABEL("compile_byte")
        # addi r15, 8  (62 0F 08)
        a.emit(asm.ldi(1, 0x62))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0F))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # subi r14, 8  (67 0E 08)
        a.emit(asm.ldi(1, 0x67))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # str r14, r1  (54 E1)
        a.emit(asm.ldi(1, 0x54))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0xE1))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # R@ ( -- x ) R:( x -- x )  IMMEDIATE
        self._dict_entry("R@", immediate=True)
        # ldn r1, r15  (50 1F)
        a.emit(asm.ldi(1, 0x50))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x1F))
        a.CALL_L_LABEL("compile_byte")
        # subi r14, 8  (67 0E 08)
        a.emit(asm.ldi(1, 0x67))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # str r14, r1  (54 E1)
        a.emit(asm.ldi(1, 0x54))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0xE1))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # IF  IMMEDIATE: compile flag test + forward branch
        self._dict_entry("IF", immediate=True)
        # Pop flag: ldn r1, r14 (50 1E)
        a.emit(asm.ldi(1, 0x50))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x1E))
        a.CALL_L_LABEL("compile_byte")
        # addi r14, 8 (62 0E 08)
        a.emit(asm.ldi(1, 0x62))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # cmpi r1, 0 (66 01 00)
        a.emit(asm.ldi(1, 0x66))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x01))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        # lbreq <placeholder> (41 00 00)
        a.emit(asm.ldi(1, 0x41))
        a.CALL_L_LABEL("compile_byte")
        # Push HERE (fixup addr) onto DATA stack
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        # Placeholder offset
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # ELSE IMMEDIATE: compile unconditional branch, resolve IF
        self._dict_entry("ELSE", immediate=True)
        # Compile lbr <placeholder> (40 00 00)
        a.emit(asm.ldi(1, 0x40))
        a.CALL_L_LABEL("compile_byte")
        # Save new fixup addr
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(0, 11))              # new fixup
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        # Resolve IF's branch → HERE
        a.emit(asm.ldn(1, 14))              # old fixup addr
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(7, 11))              # current HERE
        a.emit(asm.sub(7, 1))
        a.emit(asm.subi(7, 2))              # offset = HERE - fixup - 2
        # Patch: high byte at fixup, low byte at fixup+1
        a.emit(asm.mov(11, 7))
        a.emit(asm.lsri(11, 8))
        a.emit(asm.st_b(1, 11))
        a.emit(asm.inc(1))
        a.emit(asm.andi(7, 0xFF))
        a.emit(asm.st_b(1, 7))
        # Replace data stack entry with new fixup
        a.emit(asm.str_(14, 0))
        a.emit(asm.ret_l())

        # THEN IMMEDIATE: resolve forward branch
        self._dict_entry("THEN", immediate=True)
        a.emit(asm.ldn(1, 14))              # fixup addr
        a.emit(asm.addi(14, 8))
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(7, 11))              # HERE
        a.emit(asm.sub(7, 1))
        a.emit(asm.subi(7, 2))              # offset = HERE - fixup - 2
        a.emit(asm.mov(11, 7))
        a.emit(asm.lsri(11, 8))
        a.emit(asm.st_b(1, 11))
        a.emit(asm.inc(1))
        a.emit(asm.andi(7, 0xFF))
        a.emit(asm.st_b(1, 7))
        a.emit(asm.ret_l())

        # BEGIN IMMEDIATE: push HERE (loop target)
        self._dict_entry("BEGIN", immediate=True)
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # UNTIL IMMEDIATE: compile conditional backward branch
        self._dict_entry("UNTIL", immediate=True)
        # Pop flag: ldn r1, r14 (50 1E)
        a.emit(asm.ldi(1, 0x50))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x1E))
        a.CALL_L_LABEL("compile_byte")
        # addi r14, 8 (62 0E 08)
        a.emit(asm.ldi(1, 0x62))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # cmpi r1, 0 (66 01 00)
        a.emit(asm.ldi(1, 0x66))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x01))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        # lbreq <begin_addr> — branch back when flag=0
        a.emit(asm.ldi(1, 0x41))           # LBREQ
        a.CALL_L_LABEL("compile_byte")
        # Calculate backward offset
        a.emit(asm.ldn(0, 14))              # begin_addr
        a.emit(asm.addi(14, 8))
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(7, 11))              # HERE (after the opcode byte)
        a.emit(asm.addi(7, 2))              # after the 2 offset bytes
        a.emit(asm.sub(0, 7))               # offset = begin - (HERE+2)
        # Write offset bytes
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.andi(0, 0xFF))
        a.emit(asm.mov(1, 0))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # AGAIN IMMEDIATE: compile unconditional backward branch
        self._dict_entry("AGAIN", immediate=True)
        a.emit(asm.ldi(1, 0x40))           # LBR AL
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldn(0, 14))
        a.emit(asm.addi(14, 8))
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(7, 11))
        a.emit(asm.addi(7, 2))
        a.emit(asm.sub(0, 7))
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.andi(0, 0xFF))
        a.emit(asm.mov(1, 0))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # WHILE IMMEDIATE: same as IF but within BEGIN..WHILE..REPEAT
        self._dict_entry("WHILE", immediate=True)
        # Pop flag
        a.emit(asm.ldi(1, 0x50))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x1E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x62))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x0E))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x08))
        a.CALL_L_LABEL("compile_byte")
        # cmpi r1, 0
        a.emit(asm.ldi(1, 0x66))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x01))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        # lbreq <placeholder>
        a.emit(asm.ldi(1, 0x41))
        a.CALL_L_LABEL("compile_byte")
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(1, 11))
        # Swap with BEGIN addr on stack: BEGIN was pushed first, WHILE fixup on top
        a.emit(asm.ldn(0, 14))              # begin_addr
        a.emit(asm.str_(14, 1))             # push while_fixup (replaces begin)
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 0))             # push begin_addr on top
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldi(1, 0x00))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ret_l())

        # REPEAT IMMEDIATE: branch to BEGIN, resolve WHILE
        self._dict_entry("REPEAT", immediate=True)
        # Pop begin_addr
        a.emit(asm.ldn(0, 14))
        a.emit(asm.addi(14, 8))
        # Compile backward branch to begin
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 0))             # save begin_addr
        a.emit(asm.ldi(1, 0x40))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.ldn(0, 15))
        a.emit(asm.addi(15, 8))
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(7, 11))
        a.emit(asm.addi(7, 2))
        a.emit(asm.sub(0, 7))
        a.emit(asm.mov(1, 0))
        a.emit(asm.lsri(1, 8))
        a.emit(asm.andi(1, 0xFF))
        a.CALL_L_LABEL("compile_byte")
        a.emit(asm.andi(0, 0xFF))
        a.emit(asm.mov(1, 0))
        a.CALL_L_LABEL("compile_byte")
        # Resolve WHILE's forward branch
        a.emit(asm.ldn(1, 14))              # while_fixup
        a.emit(asm.addi(14, 8))
        a.LDI64(11, "var_here")
        a.emit(asm.ldn(7, 11))
        a.emit(asm.sub(7, 1))
        a.emit(asm.subi(7, 2))
        a.emit(asm.mov(11, 7))
        a.emit(asm.lsri(11, 8))
        a.emit(asm.st_b(1, 11))
        a.emit(asm.inc(1))
        a.emit(asm.andi(7, 0xFF))
        a.emit(asm.st_b(1, 7))
        a.emit(asm.ret_l())

    # ── System words ────────────────────────────────────────────
    def _emit_system_words(self):
        a = self.a

        # HEX ( -- )
        self._dict_entry("HEX")
        a.emit(asm.ldi(1, 16))
        a.LDI64(11, "var_base")
        a.emit(asm.str_(11, 1))
        a.emit(asm.ret_l())

        # DECIMAL ( -- )
        self._dict_entry("DECIMAL")
        a.emit(asm.ldi(1, 10))
        a.LDI64(11, "var_base")
        a.emit(asm.str_(11, 1))
        a.emit(asm.ret_l())

        # BASE ( -- addr )
        self._dict_entry("BASE")
        a.LDI64(1, "var_base")
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # WORDS ( -- ) print all dictionary words
        self._dict_entry("WORDS")
        a.LDI64(11, "var_latest")
        a.emit(asm.ldn(13, 11))

        a.label("words_loop")
        a.emit(asm.cmpi(13, 0))
        a.BR(EQ, "words_done")
        # Print name
        a.emit(asm.mov(11, 13))
        a.emit(asm.addi(11, 8))
        a.emit(asm.ld_b(12, 11))            # flags+len
        a.emit(asm.andi(12, 0x7F))
        a.emit(asm.inc(11))                  # name start
        # Print each char
        a.emit(asm.ldi(1, 0))
        a.label("words_ch")
        a.emit(asm.cmp(1, 12))
        a.BR(EQ, "words_sp")
        a.emit(asm.mov(0, 11))
        a.emit(asm.add(0, 1))
        a.emit(asm.ld_b(0, 0))
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 1))
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 11))
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 12))
        a.emit(asm.mov(1, 0))
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldn(12, 15))
        a.emit(asm.addi(15, 8))
        a.emit(asm.ldn(11, 15))
        a.emit(asm.addi(15, 8))
        a.emit(asm.ldn(1, 15))
        a.emit(asm.addi(15, 8))
        a.emit(asm.inc(1))
        a.BR(AL, "words_ch")
        a.label("words_sp")
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        # Follow link
        a.emit(asm.ldn(13, 13))
        a.BR(AL, "words_loop")
        a.label("words_done")
        a.CALL_L_LABEL("print_crlf")
        a.emit(asm.ret_l())

        # BYE ( -- ) halt the CPU
        self._dict_entry("BYE")
        a.emit(asm.halt())

        # LATEST ( -- addr )
        self._dict_entry("LATEST")
        a.LDI64(11, "var_latest")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.emit(asm.ret_l())

        # The last dictionary entry marker (for LATEST init)
        a.label("latest_entry")
        # This label must point to the LAST dict entry,
        # but it's tricky: we need it to point backwards.
        # Instead, we'll patch var_latest init to use _latest_addr.
        # (done in _fixup_latest below)

    # ==================================================================
    #  Outer interpreter (QUIT)
    # ==================================================================

    def _emit_quit(self):
        a = self.a
        a.label("quit_loop")

        # Print prompt ">" if STATE=0
        a.LDI64(11, "var_state")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.cmpi(1, 0))
        a.BR(NE, "quit_no_prompt")
        a.emit(asm.ldi(1, 0x3E))           # '>'
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        a.label("quit_no_prompt")

        # Read line
        a.CALL_L_LABEL("read_line")

        # >IN = 0
        a.emit(asm.ldi(1, 0))
        a.LDI64(11, "var_to_in")
        a.emit(asm.str_(11, 1))

        # Interpret loop
        a.label("interp_loop")
        a.CALL_L_LABEL("parse_word")
        a.emit(asm.cmpi(12, 0))
        a.LBR(EQ, "interp_line_done")

        # Save word addr/len for error messages
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 9))             # save word addr
        a.emit(asm.subi(15, 8))
        a.emit(asm.str_(15, 12))            # save word len

        # Look up in dictionary
        a.CALL_L_LABEL("find_word")
        a.emit(asm.cmpi(9, 0))
        a.BR(EQ, "interp_try_number")

        # Found — check STATE
        a.LDI64(11, "var_state")
        a.emit(asm.ldn(11, 11))
        a.emit(asm.cmpi(11, 0))
        a.BR(EQ, "interp_execute")

        # STATE=1: compiling
        # Check IMMEDIATE flag (bit 7 of R1)
        a.emit(asm.andi(1, 0x80))
        a.emit(asm.cmpi(1, 0))
        a.BR(NE, "interp_execute")

        # Not IMMEDIATE → compile call
        a.CALL_L_LABEL("entry_to_code")
        a.emit(asm.mov(1, 9))
        a.CALL_L_LABEL("compile_call")
        # Pop saved word info
        a.emit(asm.addi(15, 16))
        a.LBR(AL, "interp_loop")

        # Execute the word
        a.label("interp_execute")
        a.CALL_L_LABEL("entry_to_code")
        a.emit(asm.mov(11, 9))
        a.emit(asm.call_l(11))
        a.emit(asm.addi(15, 16))
        a.LBR(AL, "interp_loop")

        # Try number
        a.label("interp_try_number")
        # Restore word addr/len
        a.emit(asm.ldn(12, 15))
        a.emit(asm.addi(15, 8))
        a.emit(asm.ldn(9, 15))
        a.emit(asm.addi(15, 8))

        a.CALL_L_LABEL("parse_number")
        a.emit(asm.cmpi(0, 0))
        a.BR(EQ, "interp_error")

        # Success — check STATE
        a.LDI64(11, "var_state")
        a.emit(asm.ldn(11, 11))
        a.emit(asm.cmpi(11, 0))
        a.BR(EQ, "interp_push")

        # Compiling → compile literal
        a.CALL_L_LABEL("compile_literal")
        a.LBR(AL, "interp_loop")

        # Interpreting → push to data stack
        a.label("interp_push")
        a.emit(asm.subi(14, 8))
        a.emit(asm.str_(14, 1))
        a.LBR(AL, "interp_loop")

        # Error: undefined word
        a.label("interp_error")
        a.emit(asm.ldi(1, 0x3F))           # '?'
        a.emit(asm.st_b(8, 1))
        a.emit(asm.ldi(1, 0x20))
        a.emit(asm.st_b(8, 1))
        a.CALL_L_LABEL("print_crlf")
        a.LBR(AL, "quit_loop")

        # Line done — print " ok" if interpreting
        a.label("interp_line_done")
        a.LDI64(11, "var_state")
        a.emit(asm.ldn(1, 11))
        a.emit(asm.cmpi(1, 0))
        a.BR(NE, "no_ok")
        a.LDI64(10, "str_ok")
        a.CALL_L_LABEL("print_str")
        a.label("no_ok")
        a.CALL_L_LABEL("print_crlf")
        a.LBR(AL, "quit_loop")

    # ==================================================================
    #  Data section (variables, strings, buffers)
    # ==================================================================

    def _emit_data(self):
        a = self.a

        # Fix up latest_entry: point it to the actual last dict entry
        # We do this by aliasing the label to the current _latest_addr
        # Since "latest_entry" is already defined (as a label after LATEST word),
        # we remove it and re-define it.
        del a.labels["latest_entry"]
        a.labels["latest_entry"] = self._latest_addr

        # ── Strings ─────────────────────────────────────────────
        a.label("str_banner")
        a.asciiz("Chimera-1 Forth BIOS v0.1\r\n")

        a.label("str_ok")
        a.asciiz(" ok")

        a.label("str_no_name")
        a.asciiz("? no name\r\n")

        # ── Variables (8 bytes each) ────────────────────────────
        a.align(8)
        a.label("var_state")
        a.dq(0)
        a.label("var_base")
        a.dq(10)
        a.label("var_here")
        a.dq(0)
        a.label("var_latest")
        a.dq(0)
        a.label("var_to_in")
        a.dq(0)
        a.label("var_tib_len")
        a.dq(0)
        a.label("var_current")
        a.dq(0)

        # ── TIB buffer (256 bytes) ──────────────────────────────
        a.label("tib_buffer")
        a.emit(bytes(256))

        # ── dict_free: user dictionary starts here ──────────────
        a.label("dict_free")
