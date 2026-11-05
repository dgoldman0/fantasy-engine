# Fantasy Engine

Fantasy Engine is a whole computer designed from scratch: two chips, the
operating system that runs on them, a desktop, and the applications you use
there. The chips exist only as designs so far, so Fantasy Engine runs as a
simulation on an ordinary PC, where you use it through a viewer window.

Fantasy computers are machines that exist only as software, and most are small
ones whose tight limits are part of the fun. Fantasy Engine is a fantasy
computer of another kind. It is a full machine, designed so that it could be
built, and it is meant for everyday work: writing, keeping plans, following
the news, studying a subject, publishing to the web, and learning how a
computer works by building with one.

## What it stands for

Because one project designs every layer, from the chips to the applications,
the same commitments can run through all of them.

### Your work decides what opens

On a typical computer, work is organized around applications: you open a
program, and it can usually reach any file you can. Fantasy Engine organizes
work around Practices instead. A Practice is set up for one kind of work, such
as everyday computing or the study of one subject. It gathers the material
that work uses, sets what may act on that material, and opens what the work
calls for when you begin. Adding a file to a Practice doesn't copy or move it,
and doesn't by itself let anything touch it.

The first release is planned around four Practices, with a fifth to follow.
Their names are working names, and the set may change.

- **Everyday**: writing, documents and PDFs, files, plans and reminders,
  spreadsheets, news and Bluesky feeds, and the Agent, an AI assistant that
  may read, draft and set reminders. Anything it would post or send waits for
  your approval.
- **Workshop**: learning the machine by building with it. The system's own
  library sources are open to read, beside a place for your own code, a
  console for each of the machine's two programming languages, and a sandbox
  for trying what you write. The Agent explains code and helps you write it.
- **Study**: one subject's documents, feeds, notes and spreadsheets, with a
  growing map of the subject's ideas. The Agent summarizes with citations to
  the sources you gathered.
- **Publishing**: writing for the web, with a small website the machine serves
  itself, a feed of your posts, and posting to Bluesky. The Agent drafts, and
  nothing goes out without your approval.
- **Investigation**, after the first release: evidence sealed so that any
  change to it shows, a timeline, a map of the people, things and events
  involved, and findings that link back to their evidence. The Agent may
  suggest connections but never changes the evidence.

### Nothing acts for you without permission

Installing an application or adding a file to a Practice grants nothing by
itself. Permission to act, whether to change a file, set a reminder or reach
outside the machine, is given separately, narrowed to what the task needs, and
can be taken back. Each Practice sets what the Agent, scheduled actions and
sandboxed tools may do inside it, so the same assistant can draft for you in
one Practice and only read in another. In the Practices above, the Agent
drafts, summarizes and suggests, and what it would post or send waits for you.
Code that isn't trusted runs in a sandbox, where it computes within set limits
and reaches only what it is handed.

### Your data comes first

Fantasy Engine will keep your files in ext4, a standard Linux disk format, and
its storage code is held to one rule above all others: it never damages data.
Every change goes into a journal before it is made, so a crash in the middle
of a save leaves the disk in good order. The storage code also checks its own
work. A disk keeps a record of which of its space is in use. Before writing a
change, Fantasy Engine proves that the change touches no space belonging to
another file, and where that record and the files on the disk disagree, it
refuses to write. Linux's own code for ext4 trusts the record and leaves that
cross-check to a repair tool run from time to time. Fantasy Engine has no such
tool on the machine, so it makes the check itself, as part of its guarantee.
Whatever it can't do safely, it refuses with a clear error, leaving your data
as it was.

### Every layer is open to you

Every part of Fantasy Engine, from the chips' hardware designs to the
applications on its desktop, is developed in public, and all of it will be
released under open licences. With all of it in view, a curious person can
follow a feature from the screen down to the chip that carries it out. The
main processor's software, from the operating system up, is written in Forth,
a small language in which you type a word and it runs at once, and in which
the words the system is built from work just like the ones you write yourself.
The Workshop is meant for this kind of curiosity. There you will be able to
open the source of a library the system ships with, write your own code that
uses it and watch it run, in either of the machine's languages, while the
installed system stays safe from anything you try.

### Speed comes from removing waste, not checks

The chips are meant to be modest in size, so wasted work has a real cost. When
the project makes Fantasy Engine faster, it looks for work the machine repeats
without need and removes it, and it keeps every check that protects you, even
where other systems leave that check out. Size follows the same thinking. A
limit guessed in advance either holds memory that nothing uses or turns away
work that would have fit, so the project's rule is to size memory and storage
from what the work in hand needs, and to keep a fixed limit only where a
standard or a file format sets one. Where one general way of doing a job can
replace a set of special cases, the project builds it and deletes the special
cases rather than keeping them beside it, which leaves fewer places for
something to go wrong.

### A machine that could be built

No one has made the chips yet, but they are designed as real chips. Each has a
hardware design written in the languages real chips are made from, and each
design describes the chip that's wanted rather than one cut down to fit a test
board. Work on the software is judged first by what it would cost the real
machine. A change that only speeds up the simulation on your PC is welcome as
well, since the simulation is how people can get to know the machine before
the chips exist, but the project says plainly which of the two a change
improves.

## What's inside

The machine's two chips, MegaPad and LM1, are packaged together as one, called
Leviathan.

**MegaPad** runs the system and everything you see. It drives the screen,
storage and the network, does fast arithmetic on blocks of numbers, and has
hardware for the cryptography that secure connections and sealed records
depend on. Its operating system and the software above it are written in
Forth.

**LM1** is a processor built for Lisp, a language whose programs and data are
made of linked lists. Its hardware knows what kind of value each piece of
memory holds, and it clears away whatever nothing uses any more, work that
most processors leave to software. In Fantasy Engine it will run the sandbox's
jobs, keeping each one apart from the others, and hold the desktop's growing,
connected information, such as Study's map of ideas. The two chips share
memory, so neither has to copy data to hand work to the other.

**Akashic** is the software above the operating system: the libraries
applications are built from, the Practices, and the desktop, called Desk.
Desk's applications include Pad for writing, File Explorer for files, Daybook
for plans and reminders, Grid for spreadsheets, Streams for feeds, and the
Agent. The Agent and Streams reach outside services, such as an AI provider
and Bluesky, under those services' own terms, and any account they use is
yours.

You watch and use the machine through a viewer window on your PC. The machine
doesn't send that window pictures of its screen. It sends what the screen
holds: text with its styles, links, controls and images. The viewer draws them
in its own fonts. The same applications also run in a plain text terminal.

## Where it stands

Fantasy Engine hasn't been released, and everything in it is still a rough
draft. The desktop and its applications already run in MegaPad's simulator, in
builds made for development and testing, while LM1 runs separately in an
emulator of its own. The first release, version 0.1.0, is an alpha now being
built. It will bring the parts together into one system you can install: the
Practices above, a `fantasy-engine` command that builds and runs them, LM1
working beside MegaPad, and storage in ext4, so your files sit on a disk your
PC's own tools can open and check. It will run on 64-bit Intel and AMD PCs
under Linux, and under Windows through WSL2; macOS comes later. Its code,
hardware designs included, will be licensed under Apache-2.0, and its
documentation under CC BY 4.0.

The plan for the first release, with the reasons for each decision, is public
in [dev/PLAN.md](dev/PLAN.md). For now this repository holds that plan and the
tool that runs the whole system's tests, and the release itself will be
assembled here.

The parts are developed in their own repositories, which are written for
engineers: [MegaPad](https://github.com/dgoldman0/megapad) for the machine,
its simulator and its operating system,
[Akashic](https://github.com/dgoldman0/akashic) for the libraries, Desk and
its applications, and [LM1](https://github.com/dgoldman0/lisp-machine-LM1) for
the Lisp processor.

To talk about the project, join the Tinkerers Guild channel on the
Barayin-Adamah Discord server: <https://discord.gg/AnrXxhs3b2>.
