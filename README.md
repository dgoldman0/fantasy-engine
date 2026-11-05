# Fantasy Engine

Fantasy Engine is a whole computer designed from scratch: two chips, the
operating system that runs on them, a desktop, and the applications you use
there. The chips exist only as designs so far, so Fantasy Engine runs as a
simulation on an ordinary PC, where you use it through a viewer window.

Fantasy computers are machines that exist only as software, usually small ones
whose tight limits are part of the fun. Fantasy Engine is a fantasy computer
designed as a full machine, one that could be built, and it is meant for
everyday work: writing, keeping plans, following the news, studying a subject,
publishing to the web, and learning how a computer works by building with one.

## What it stands for

Because one project designs every layer, from the chips to the applications,
it can hold all of them to the same commitments.

### The computer is organized around your work

On a typical computer, work is organized around applications: you open a
program, and it can usually reach any file you can. Fantasy Engine organizes
work around Practices, each set up for one kind of work, such as everyday
computing or the study of one subject. A Practice records the material that
work uses and what may act on it, and in the first release the desktop will
open what the work needs when you begin. Each file you add to a Practice stays
where it is, and the Practice holds a reference to it.

The first release is planned around four Practices, with a fifth to follow.
Their names are working names, and the set may change.

- **Everyday**: writing, documents and PDFs, files, plans and reminders,
  spreadsheets, news and Bluesky feeds, and the Agent, an AI assistant that
  may read, draft and set reminders. It will post or send only what you
  approve.
- **Workshop**: learning the machine by building with it. There the system's
  own library sources will be open to read, beside a place for your own code,
  a console for each of the machine's two programming languages, and a sandbox
  for trying what you write. The Agent will explain code and help you write
  it.
- **Study**: one subject's documents, feeds, notes and spreadsheets, with a
  growing map of the subject's ideas. The Agent will summarize the material,
  citing the sources you gathered.
- **Publishing**: writing for the web, with a small website the machine serves
  itself, a feed of your posts, and posting to Bluesky. The Agent will draft,
  and it will publish only what you approve.
- **Investigation**, after the first release: evidence sealed with hashes so
  that any change to it can be detected, along with a timeline, a map of the
  people, things and events involved, and findings that link back to their
  evidence. The Agent may suggest connections, and it will leave the evidence
  as it found it.

### Anything that acts for you needs permission

Permission to act, whether to change a file, set a reminder or reach outside
the machine, is given separately from installing an application or adding a
file to a Practice. It is narrowed to what the task needs, and it can be taken
back. Each Practice states what the Agent, scheduled actions and sandboxed
tools may do inside it, so the same assistant can draft for you in one
Practice and only read in another. Across the Practices above, the Agent will
draft, summarize and suggest within what each Practice allows, and you will
approve whatever it would post or send. Untrusted code is held more tightly
still: it runs in a sandbox, where it computes within set limits and reaches
only what it is handed.

### Your data comes first

Fantasy Engine will keep your files in ext4, a standard Linux disk format, and
its storage code is held to one rule above all others: everything it does is
correct and survives a crash. It writes every change to a journal before
making it, so after a crash in the middle of a save the disk is still in good
order.

The storage code also checks its own work. A disk holds a record of which of
its space is in use. Before writing a change, the storage code proves that the
change leaves every other file's space untouched, and where that record and
the files on the disk disagree, it refuses to write. Linux's own ext4 code
relies on the record, and Linux leaves the cross-check to a repair tool that
is run from time to time. Fantasy Engine has no such tool on the machine, so
its storage code makes the check itself, as part of its guarantee. It answers
any request beyond what it can do safely with a clear error and leaves your
data as it was.

### Every layer is open to you

Every part of Fantasy Engine, from the chips' hardware designs to the
applications on its desktop, is developed in public, and all of it will be
released under open licences. With all of it in view, a curious person can
follow a feature from the screen down to the chip that runs it. The main
processor's software, from the operating system up, is written in Forth, a
small language in which you type a word and it runs at once, and in which the
words the system is built from work just like the ones you write yourself. The
Workshop is meant for this kind of curiosity. There you will be able to open
the source of a library the system ships with, write your own code that uses
it and watch it run, in either of the machine's languages, while the installed
system stays safe from anything you try.

### Speed comes from removing waste, and every check stays

The chips are meant to be modest in size, so wasted work has a real cost. When
the project makes Fantasy Engine faster, it removes work the machine repeats
when doing it once would be enough, and it keeps every check that protects
you, including checks other systems leave out. A limit guessed in advance
costs something too: memory reserved up to it goes unused when the work needs
less, and work that needs more is refused although the machine has room for
it. The project therefore sizes memory and storage from what the work in hand
needs, and keeps a fixed limit only where a standard or a file format sets
one. In the code itself, where one general way of doing a job can replace a
set of special cases, the project builds it and deletes the special cases,
which leaves fewer places for something to go wrong.

### A machine that could be built

The chips are designed as real chips: each has a hardware design written in
the languages chip designers use, describing the chip the project wants. The
software is held to the same standard and judged first by what it would cost
that real machine. A change that speeds up only the simulation on your PC is
welcome as well, since the simulation is how people can get to know the
machine before the chips exist, and the project says plainly which of the two
a change improves.

## What's inside

The machine's two chips, MegaPad and LM1, are packaged together as one, called
Leviathan.

**MegaPad** runs the system and everything you see. It drives the screen,
storage and the network, does fast arithmetic on blocks of numbers, and has
hardware for the cryptography used by secure connections and sealed records.
Its operating system and the software above it are written in Forth.

**LM1** is a processor built for Lisp, a language whose programs and data are
made of linked lists. Its hardware records what kind of value each piece of
memory holds and clears away values that have gone out of use, work that most
processors leave to software. In Fantasy Engine it will run the sandbox's
jobs, keeping each one apart from the others, and hold the desktop's growing,
connected information, such as Study's map of ideas. The two chips share
memory, so when one hands work to the other, the data stays where it is.

**Akashic** is the software above the operating system: the libraries
applications are built from, the Practices, and the desktop, called Desk.
Desk's applications include Pad for writing, File Explorer for files, Daybook
for plans and reminders, Grid for spreadsheets, Streams for feeds, and the
Agent. The Agent and Streams reach outside services, such as an AI provider
and Bluesky, under those services' own terms, and any account they use is
yours.

You watch and use the machine through a viewer window on your PC. The machine
sends that window what its screen holds, as text with its styles, links,
controls and images, and the viewer draws them in its own fonts. The same
applications also run in a plain text terminal.

## Where it stands

Fantasy Engine is in development, and everything in it is still a rough draft.
The desktop and its applications already run in MegaPad's simulator, in builds
made for development and testing, while LM1 runs separately in an emulator of
its own. The first release, version 0.1.0, is an alpha now being built. That
release will be one system you can install, with its four Practices, a
`fantasy-engine` command that builds and runs them, LM1 working beside
MegaPad, and storage in ext4, so your files are kept on a disk that your PC's
own tools can open and check. It will run on 64-bit Intel and AMD PCs under
Linux, and under Windows through WSL2; macOS comes later. Its code, hardware
designs included, will be licensed under Apache-2.0, and its documentation
under CC BY 4.0.

The plan for the first release, with the reasons for each decision, is public
in [dev/PLAN.md](dev/PLAN.md). For now this repository holds that plan and the
tool that runs the whole system's tests, and the release itself will be
assembled here.

The parts are developed in their own public repositories, which are written
for engineers: [MegaPad](https://github.com/dgoldman0/megapad) for the
machine, its simulator and its operating system,
[Akashic](https://github.com/dgoldman0/akashic) for the libraries, Desk and
its applications, and [LM1](https://github.com/dgoldman0/lisp-machine-LM1) for
the Lisp processor.

To talk about the project, join the Tinkerers Guild channel on the
Barayin-Adamah Discord server: <https://discord.gg/AnrXxhs3b2>.
