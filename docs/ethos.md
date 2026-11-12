# The ethos of Fantasy Engine

Fantasy Engine is a whole computer designed by one project, from its two
chips to the applications on its desktop. On an ordinary computer those
layers come from different makers, each answering for its own, and the person
using the machine takes the rest on trust. One project can hold every layer
to the same standards, and this one holds them to three.

The first is openness to inspection: a person can read how any part of the
machine works, down to its chips. The second is dependability: the machine
keeps a person's work safe through its own failures, a crash in the middle of
a save included. The third is rigor: the parts check what they rely on, and
the project keeps the checks that protect a person's work while it makes the
machine faster.

Those standards reach the person using the machine as six commitments, listed
in the [README](../README.md). This page states each one with its reason and
with what it means in use.

Fantasy Engine is in development, and its first release, an alpha, is now
being built. Each section states what exists today and what that release is to
bring.

## The computer is organized around your work

A person sits down at a computer to do something: write a letter, study a
subject, publish a page. On a typical computer the person then chooses among
applications, each of which can usually reach any file its user can. Fantasy
Engine organizes the machine around the work itself. A Practice is a setup for
one kind of work, recording the material that work uses and what may act on
it, so that the desktop can open what the task needs when the person begins.
The desktop and its applications already run in development builds, and the
first release is planned around four Practices: everyday computing, learning
the machine, the study of one subject, and publishing to the web.

## Anything that acts for you needs permission

Within a Practice, as everywhere in the system, the authority to act is given
on purpose. Permission is given separately from installing an application or
adding a file, it is narrowed to what a task needs, and the person can take it
back. In the first release each Practice will state what the AI assistant,
scheduled actions and sandboxed tools may do inside it, and the assistant will
post or send only what the person approves. The project applies the same rule
between the chips. MegaPad, the main chip, lends its partner LM1 ranges of
memory to work in and checks each of LM1's accesses against them ([MegaPad and
the 1802](1802-lineage.md)). That link exists today in both chips' hardware
designs, tested in simulations of the circuits.

## Your data comes first

A person's files also have to survive the machine's own failures, a crash in
the middle of a save above all. The storage code is therefore held to one rule
above all others: everything it does is correct and survives a crash. It makes
each change through a journal, so at its next start after a crash it restores
every change that was fully recorded. A request beyond what the code can do
safely receives a clear error, and the files stay as they were. The format is
ext4, a standard Linux disk format, so the person's own PC can open the same
disk and check it. [The driver](ext4.md) exists today. The desktop still keeps
its own files in the system's native format, and the first release is to keep
the person's files in ext4.

## Every layer is open to you

A person can depend on these commitments only as far as they can be checked,
so the whole system is open to inspection. Every part of it, from the chips'
hardware designs to the applications, is developed in public, along with the
plan for the first release and the reason for each of its decisions, and all
of it is to be released under open licences. The main chip's software is
written in Forth, a small language in which the words the system is built from
work like the words a person types, so a curious person can follow a feature
from the screen down to the chip that runs it. The first release is to include
a Practice for that kind of study, where a learner reads the system's own
library sources and tries code against them while the installed system stays
safe.

## Speed comes from removing waste

With the code in view, a reader can see where the system gets its speed. The
chips are meant to be modest in size, so wasted work has a real cost, and the
project removes it: work the machine repeats when doing it once is enough,
memory reserved up to a guessed limit, a set of special cases where one
general routine would do. Through these changes the project keeps the checks
that protect a person's work, and its word for what it keeps is rigor. Storage
is the plainest case. Linux's own ext4 code relies on a disk's record of the
space in use and leaves the cross-check of that record to a repair tool run
from time to time. Fantasy Engine has no such tool on the machine, so its
driver already makes the check itself: each time it opens a disk, before its
first write, it proves the record against every file, afterwards it checks
what each change alters, and where the record and the files disagree it
refuses to write.

## A machine that could be built

The cost the project counts first is the cost on the real machine. Each chip
has a hardware design written in the languages chip designers use, and that
design describes the chip the project wants. The software is judged first by
what it would cost on those chips. A change that speeds up only the simulation
on a PC is welcome as well, since the simulation is how people can get to know
the machine before the chips exist, and the project says plainly which of the
two a change improves. Today the desktop runs in a simulation of MegaPad while
LM1 runs in an emulator of its own, and the first release is to bring them
together as one system a person can install.
