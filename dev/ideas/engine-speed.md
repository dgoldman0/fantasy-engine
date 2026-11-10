# Host speed of the emulator and the simulator

What a study on 2026-11-10 found still open after its quick fixes landed.
Nothing here is decided, and none of it changes what the machine does or
costs: every item is host time, for tests and for the simulated experience.

The figures were measured at MegaPad c3e8ef5f and Akashic 2bb7ffdc on one
machine that was running other work, so they order the items and should be
measured again before any of them is built.

## 1. The emulator: let translated blocks reach each other

The emulator translates guest code to host code a block at a time. On tight
Forth loops it runs 33 to 47 million instructions a second, and about 16
million in an ext4 write journey. Translated guest code is 5% of its time on
the loops and 2% in the journey. The rest is the work around each block:
finding it, checking the memory it will touch, and deciding on the way out
where to go next. Between a fifth and a third of the instructions still run in
the scalar interpreter.

Forth changes control flow every three or four instructions. A call through
the SEP dispatch is about fourteen instructions with five transfers. Blocks
therefore stay about three instructions long, and making them longer gains
little. The two-block regions the emulator already forms almost never apply to
Forth code.

The direction is to let a translated block jump straight to the next one
inside generated code, with the memory checks emitted inline, so that the
work around a block is paid once when blocks are linked and not at every
transfer. The estimate is several times the present speed. It is a redesign of
the translator's exits and of how a block is invalidated, measured in weeks,
and nothing of it has been prototyped.

Three smaller findings belong with it:

- In ext4 code the guest's 4 KB instruction cache misses on about 6% of
  instructions, and the host's block cache is rebuilt constantly: 332,000
  block builds in one journey. The first is a fact about the chip as well as
  the emulator.
- Reads of the system-information device reach Python a byte at a time, 1.65
  million byte reads in the journey.
- A build guided by a profile ran the loops it was trained on 21 to 39%
  faster and the ext4 journey about 10% faster.

An alternative for test time alone: the simulator runs the same Forth loop 19
to 33 times faster than the emulator, so suites like the ext4 one could run
there once its storage model can inject faults the way the emulator's does.

## 2. The simulator: Python around the engine

The simulator's native engine was reworked the same day (MegaPad 17db2bb7 and
the three commits after it): its kernels run 2.0 to 8.1 times faster, the
headless Desktop is ready in about 5.2 s where it took 6.2 s, and a typed
character shows in 0.064 s where it took 0.085 s. Measured afterwards, most of
the Desktop's host time is Python around the engine, in four places.

**Boot compile.** The three seconds before Desk starts are KDOS and the
linked source chunks going through the Python text interpreter and the native
line walker. The engine work did not touch them.

**Device words.** While Desk starts, the engine is entered about 20,400 times
for 134 million steps, and 16,400 of those returns are for words Python still
runs: the CRC device's (5,200 calls), the spinlock words `SPIN@` and `SPIN!`
(4,800), the disk unit words (1,800), `KEY?` (1,100), `TYPE` (800), and
`EXECUTE` of a token that is not a planned colon word (500). The words
themselves take 0.13 s together, so what costs is the return and the re-entry
around each. Every one has its service in Python, so running a word in the
engine means giving the engine that service's state. A typed character makes
about 540 returns, and 330 of them are `KEY?` and the UART read of the guest's
idle poll, which run while the guest waits for the next key.

**The session's own work for a frame.** A typed character takes about 0.064 s
from key to shown frame, and the engine is about 0.023 s of it. Much of the
rest is the session thread's Python: the rich-terminal host projects and
validates the retained scene for each frame (about 20 ms a frame under a
profiler, which inflates it), decodes the protocol, and waits on the display
cadence.

**Planning a word.** The first time a word runs, its plan is made from Python
IR objects built for every operation of the word, 293,000 of them while Desk
starts. A plan made straight from the native dictionary's records would skip
those objects for the words Python never dispatches itself.

One limit inside the engine also showed. The direct path knows one page of
ordinary memory at a time, and the simulator's memory is sparse 4 KiB pages,
so code that reads and writes across several pages keeps handing accesses to
the general path. About nine tenths of the Desktop's native steps take the
direct path, and a kernel that reads over four pages gained 3.4 times where
its neighbours gained five to eight. Letting the direct path hold several
qualified pages would close that.
