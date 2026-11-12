# The ethos of Fantasy Engine

Fantasy Engine is a computer that a person can understand from its desktop
down to its chips. That aim decides how the machine is built. This page
states the commitments that follow from it, with the reason for each and how
far each is built today. The [README](../README.md) lists what the machine
promises a person in daily use; this page describes the design behind those
promises. Fantasy Engine is in development, and its first release, an alpha,
is now being built.

## Open to inspection, nearly all the way down

The first commitment is that every layer can be read. The desktop, its
applications, the libraries under them, the operating system and the storage
driver are written in Forth, a small language whose programs are made of
words. The words the system is built from work like the words a person types
at its prompt, so a person can take a feature on the screen, look up the word
behind it, and follow that word through the words it is made of.

Below Forth the chain continues. The lowest words are written in the assembly
language of MegaPad, the chip that runs the system. The instruction set which
that assembly uses is documented, and the hardware designs of both chips are
public. The system is therefore close to one language all the way down: Forth
for nearly all of it, and under Forth a short chain of definitions, each of
which a person can read, ending at the chip's own circuit description.

## What MegaPad kept from the 1802

MegaPad is a successor in spirit to the RCA CDP1802, a microprocessor of 1976.
It kept what suits a small machine that runs Forth: registers that can each
take any role, and a compact way of writing instructions. Any register can
serve as the program counter, and MegaPad's Forth calls a word and returns
from it by switching registers. A core tests a flag line with a single branch,
a test made inside the core while the bus stays free for other work. Devices
work on memory themselves, as the 1802's did, and that arrangement is what
lets a second chip share MegaPad's memory.

The 1802's own parts for input and output came down unevenly. [MegaPad and
the 1802](1802-lineage.md) tells which of them survived, which were left
behind, and what the habit behind them still decides.

## A memory for each kind of work

MegaPad's memory is divided by use. System memory holds the BIOS, the
dictionary of words, the stacks and the heap. A separate bank serves heavy
arithmetic on blocks of numbers, so that work stays out of the system's way.
The screen has video memory of its own, and a large external memory holds
what the two chips share.

Two rules hold across all of it. The cores keep no cache of data, so the
value one part of the machine has written is the value another reads next.
And a part that works on another's memory is held inside ranges that the
hardware checks: the disk controller's transfers are, and so is every access
that LM1, the second chip, makes to the memory MegaPad lends it. The link
between the chips exists today in both hardware designs, where it is tested
in simulations of the circuits.

## Guarantees enforced by the hardware

Where parts of the machine compete, hardware sets the share each receives.
The arbiter of MegaPad's main bus grants the bus in weighted turns and counts
each port's use against a limit for every period of 65,536 clock cycles. That
circuit makes every grant, so a share it enforces holds whatever the software
does. The project calls this hard quality of service. The arbiter serves the
full cores and the clusters of small cores, and inside a cluster the small
cores take equal turns. The same scheme governs external memory, where each
port for a second chip has a weight and a limit.

Both arbiters are in the hardware design today. In the present design the
main bus's settings stay at their starting values, and the registers that set
them are still to be connected.

## Rigor

The chips are meant to be modest in size, so wasted work has a real cost, and
the project makes the machine faster by removing waste: work repeated where
once is enough, memory reserved up to a guessed limit, several special cases
where one general routine would do. Through those changes it keeps the checks
that protect a person's work, and rigor is its word for what it keeps. The
storage driver is the plainest case. Each time it opens a disk, before its
first write, it proves the disk's record of used space against every file,
and where the two disagree it refuses to write ([the ext4 driver](ext4.md)).

## A machine that could be built

The cost the project counts first is the cost on the real machine. Each chip
has a hardware design, and that design describes the chip the project wants.
Software is judged by what it would cost on those chips. A change that speeds
up only the simulation on a PC is welcome too, since the simulation is how
people can get to know the machine before the chips exist, and the project
says plainly which of the two a change improves.
