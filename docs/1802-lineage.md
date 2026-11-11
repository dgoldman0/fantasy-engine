# MegaPad and the 1802

MegaPad, the chip that runs Fantasy Engine's system, is a successor in spirit
to the RCA CDP1802, a microprocessor of 1976, and it still has input and
output instructions of the 1802's kind. A reader who knows the 1802 might
expect those instructions to connect MegaPad to its partner chip, LM1. The
link between the two chips uses a single one of them, a branch that tests a
flag. What the link depends on is a habit of design that the 1802 left in
MegaPad: devices work on memory for themselves. This page describes the
inherited instructions, the habit, and how the habit lets two chips work on
one memory.

## The 1802 and its devices

On other processors of its time, such as the 8080 and the 6502, a program
sent a byte to a device by loading the byte into a register and writing that
register out, so every byte passed through the processor. The 1802 let its
devices work on memory themselves, and it had four means of input and output.

- Its input and output instructions named a place in memory, and the byte
  passed between that place and the device while the processor supplied the
  address. These are its port instructions, one for each of seven ports in
  each direction.
- A device could fetch from memory or store into it by itself, by raising a
  request line. The 1802 kept one of its sixteen registers as the pointer for
  this. At each request a byte moved between the device and the place the
  pointer named, and the pointer stepped on. The 1802's companion video chip
  read the picture out of memory this way.
- A device signalled the processor on one of four flag lines, and a program
  tested a line with a single branch instruction.
- A program could set and clear one output line, called Q.

The processor's part was to keep the pointers and watch the flags, while the
devices read and wrote for themselves.

## What became of the inherited parts

MegaPad is a 64-bit chip designed new, with four full cores and twelve small
ones. Its instruction set shows the descent: any register can serve as the
program counter, as on the 1802, and MegaPad's Forth calls a word and returns
from it by switching registers. The four means above came down to MegaPad
unevenly, and the link to LM1 uses the third alone.

- The port instructions are present on the full cores, where a bridge maps
  each port to a register of one of MegaPad's devices. Each instruction moves
  a single byte, and that byte crosses MegaPad's bus twice, once out of
  memory and once into the device. The small cores lack the instructions.
  Two chips that share data need whole regions of memory, so the link does
  without the ports.
- The request lines are gone: MegaPad's cores have no pin by which a device
  asks for memory.
- Q became a bit inside each full core, which the core's own program sets
  and tests.
- The flag lines became a flag input on each core, together with the branch
  that tests it. A chip beside MegaPad signals a full core on this input.

## The habit that carried over

What MegaPad took from the 1802 in full is the arrangement those parts
served. MegaPad's disk and network controllers are new work, built in the
1802's manner: each reads and writes memory itself, as the 1802's video chip
did, and MegaPad holds the disk's transfers inside ranges of memory that it
checks. The cores, for their part, keep no cache of data, so the value a
device has just written is the value a core reads next. A device on MegaPad
therefore works on the very memory the cores see.

## Two chips on one memory

Leviathan packages MegaPad with LM1, a processor built for Lisp, as a second
die beside it. LM1 is to run jobs for programs on MegaPad and to hold data
that those programs read directly, so the two chips need the same data in
front of them.

MegaPad provides it by treating LM1 as one more device of its own kind. It
lends LM1 ranges of its memory, and LM1 reads and writes them in place.
MegaPad checks each of LM1's accesses against the ranges it lent,
the kind of check it already applies to its disk, and the check bounds what
LM1 can reach. Since the cores read data straight from memory, a core sees
what LM1 wrote as soon as LM1 has written it. An address means the same
thing on both chips, and each works on the single copy of the data.

When LM1 has finished a piece of work, it signals a core on that core's flag
input, and the waiting core tests the input with the branch instruction
MegaPad inherited. The test takes place wholly inside the core, so MegaPad's
bus stays free for other work.

## What the 1802 contributed

Of the 1802's four means of input and output, then, the link uses one flag
input. Everything else it needs comes from the arrangement behind them:
devices that act on memory, and a processor that lends the memory and checks
its use. Many devices today work on their host's memory, and a chip with no
1802 behind it could share memory with a neighbour the same way. MegaPad
came to the arrangement as the 1802's successor, built its own devices by
it, and now extends it to a second chip.

The link is part of both chips' hardware designs, where it is tested in
simulations of the circuits. The simulator that runs Fantasy Engine today
models MegaPad alone, and the first release is to bring LM1 in beside it.
