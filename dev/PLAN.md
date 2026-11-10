# Plan for the first release

This repository is the home of the first release of the fantasy-computing
ensemble. The release brings MegaPad, Akashic and the LM1 Lisp chiplet
together as one system that people can install and use. This plan covers the
work from now until that release ships.

This plan lives in `dev/`, which holds all of this repository's development
material: the plan, ideas still being worked out in `dev/ideas/`, and notes
for later releases. Everything outside `dev/` will document use and
function. The release is cut on a branch without `dev/`, so the release
carries none of it, while main keeps it for the next release (decision 33).

Status on 2026-11-03: release work has begun with Part 1h, test selection,
because every later part's testing goes through it. The rest of Part 1
(organization) stands as it did when the plan was locked in on 2026-10-27:
Part 1c, the LM1 split, is done, and Part 1d, the library inventory, has
its first static pass. The Chimera prototype that used to live here is kept
by the tag `archive/chimera-a499082-20261027`, and commit 54616ae removed it
from the tree.

Section 1 says what the release is. Sections 2 and 3 list the decisions
taken and the decisions still open. Section 4 records where each component
stands today. Section 5 sets out the work in eleven parts, each with its
steps, what "done" means and what it needs first. Sections 6 and 7 give the
order of the parts and the rules the work follows.

Three labels mark the status of each item. **Decided** items are settled.
**Proposed** items await approval. **Open** items are decisions still to be
made.

## 1. What the release is

- **One system** (Decided). MegaPad is the Forth machine: its native
  simulator and emulator, BIOS, KDOS and system modules. Akashic supplies the
  libraries, Desk, the applets and Practices. LM1 is a Lisp chiplet that
  works beside MegaPad as a partner device, and the two share memory.
  MegaPad handles control, I/O and number crunching. LM1 runs the sandbox's
  jobs and holds the data Desk wants collected, with type checks, allocation
  and garbage collection in hardware, and its own software is written in
  Lisp. The combined chip is Leviathan, and the system people run is Fantasy
  Engine.
- **The LM1 chiplet is in it** (Decided). There is no release until it is,
  and it is part of Leviathan in every configuration, not an add-on.
- **Sample configurations** (Decided). A handful of ready-made boot setups,
  each a Practice built around a task or subject, together cover what the
  system does. One of them is the System Practice, a place to learn the
  system by building with its own libraries.
- **Documentation about use and function only** (Decided).
- **Open licences** (Decided). All code, RTL included, is licensed under
  Apache-2.0, and documentation under CC BY 4.0.
- **It runs on a Linux PC** (platform Decided, the rest Proposed). People run
  the native simulator on 64-bit Intel or AMD Linux, or under WSL2 on
  Windows, and watch it through the rich-terminal viewer. The emulator stays
  available as a second backend.
- **Hardware designs ship with it** (Proposed). MegaPad's and LM1's RTL are
  part of the release, at the same recorded commits as the software.

## 2. Decisions taken

All were taken on 2026-10-27, except decisions 35 and 36, taken on
2026-10-28 and revised on 2026-11-03.

1. fantasy-engine is the release repository. It sits beside `megapad/`,
   `akashic/` and `lm1/` in the workspace.
2. The Chimera prototype is retired. The annotated tag
   `archive/chimera-a499082-20261027` keeps its last state, and commit
   54616ae removed it from the tree.
3. The first release includes the LM1 chiplet. Work toward the release
   builds up here while LM1 catches up.
4. The LM1 repository becomes the chiplet only, with its own OS and desktop
   retired by archive tag. This is done (Part 1c).
5. Practices keep their name. Each sample configuration is built around one
   Practice.
6. One Practice is about the system itself, including its libraries.
7. The libraries get an inventory. Only working, current libraries ship, and
   scrap stays out.
8. Release documentation covers use and function only. Development material
   stays in `dev/`, which the release leaves out (decision 33).
9. The release filesystem is ext4, supported to a reasonable degree rather
   than completely (Part 2).
10. Three items lead the work: reasonable ext4 support (Part 2), proper
    multicore support in the simulator (Part 3) and the LM1 chiplet
    (Part 8).
11. The LM1 chiplet's model is accelerated C++, written as a module that
    MegaPad's simulator imports. MegaPad's work therefore includes importing
    chiplet modules (Parts 3d and 8d).
12. A lock file in this repository records the component commits that make
    up the release (Part 1b).
13. All code, RTL included, is licensed under Apache-2.0, and documentation
    under CC BY 4.0. Apache-2.0 adds the explicit patent grant that CC0
    withholds. MegaPad versions already published under CC0 stay CC0, and
    LM1's MIT metadata line is replaced.
14. Compliance is set up early and finished at release. Part 1g adds licence
    files, per-file licence lines and notices; Part 11 adds a provenance
    scan, third-party notices and a software bill of materials.
15. "Reasonable" ext4 means what an alpha tester needs, done well (Part 2).
16. The simulator work in Part 3: every full core, then the clusters and
    microcores, with results equal to lock-step; speculative parallel rounds;
    a general way to attach devices; and chiplet module import.
17. LM1's Python emulator stays the reference model until the C++ chiplet
    module is complete. Because it may be wrong too, the spec is the referee
    between them (Part 8d).
18. MegaPad's git history keeps `cdp1802.pdf`, a copy of RCA's 1802 manual.
    Part 1g removes it from the tree, so neither the release nor future
    checkouts include it. History is purged only if the rights holder asks,
    because a purge would change every MegaPad commit ID since February.
19. Microcores get all 32 registers, as the design implies and the emulator
    already models. The RTL microcore, which has 16 and appears to ignore the
    REX prefix's extension bit, is widened to match (Part 3e).
20. The system and its command are called Fantasy Engine, and the combined
    MegaPad and LM1 chip is Leviathan. Both names get a trademark search
    before release (Part 11).
21. Every component carries one version, 0.1.0, aligned when the release is
    prepared.
22. The use-and-function rule covers this repository only, and here
    development material, including how the release is built, lives in
    `dev/` (decision 33). The component repositories keep their development
    material.
23. The alpha runs on Linux on 64-bit Intel and AMD PCs, with prebuilt parts
    compiled for the x86-64-v2 baseline. Windows users run it under WSL2,
    and macOS comes later.
24. LM1 is part of Leviathan in every configuration, not an add-on, so no
    configuration exists only for Lisp.
25. Each sample configuration is a Practice built around a task or subject.
    It binds the material the work needs, sets what may act there and opens
    what the work calls for; it is not a preset of which applets are open.
    Sound Lab and Observatory are not configurations as they stand.
26. The sample configurations are five Practices: Everyday, Workshop, Study
    and Publishing in the alpha, and Investigation after it (Part 6). The
    set can change later.
27. LM1 first shows what it does for Desk. The sandbox's jobs run on LM1,
    where typed values are tagged words, allocation and collection happen in
    hardware, and capability mode keeps jobs apart (Part 9c). Desk's
    growing, linked data follows as managed data (decision 28, Part 9d). The
    Lisp console is a learning tool in the Workshop (Part 7), and LM1's side
    of this work is written in Lisp.
28. LM1's collector manages only data in LM1's tagged format. Forth's memory
    doesn't mark which numbers are pointers, so no collector can manage it,
    wherever LM1 sits, and Forth's own buffers stay under manual control. A
    pointer mark on every word of MegaPad's memory would lift that limit,
    but it would change MegaPad's hardware and every Forth word that stores
    a reference, so it is not adopted. Desk code that wants its data
    collected creates it as managed data instead: LM1 objects in shared
    memory, made through an Akashic library and used under the rules in
    Part 9d.
29. MegaPad and LM1 share memory. Each chip reads and writes the other's
    data where it lies, so nothing is copied between them. The cost that
    remains is the hand-off when one chip asks the other to do work,
    signaling it and waiting for the answer, so work crosses as whole jobs.
    A hand-off would cost about the same on one die, and moving LM1 onto
    MegaPad's die wouldn't change the collector's limit either
    (decision 28), so LM1 stays a chiplet.
30. Leviathan gets a language of its own. Its meaning covers both plain data
    and collected objects, so it uses both of Leviathan's engines natively
    without naming either (decision 31). Existing languages each assume one
    kind of memory. Lisp, Factor, Joy, Erlang and Pony let a collector own
    every value, stacks included, while Forth has no managed values at all.
    The nearest exceptions each miss part of it: PreScheme compiles its
    manual level ahead of time, so the two never mix at run time; Rust
    tracks lifetimes precisely but has no collected side; and HP's RPL ran
    its two levels over one collected memory on one chip. WebAssembly with
    garbage collection has decision 28's split, raw memory plus managed
    references kept there only as handles, but it is a compile target rather
    than a language people write. None treats two instruction sets as one
    program. The language is new rather than a derivative. Factor comes
    closest, but its libraries need Factor's VM, and what would change (one
    collected heap, a tagged stack, open authority) is its core, so a
    derivative would keep only its look. The compatibility that matters is
    with Akashic's Forth and with Lisp's data: the language's plain-data
    side is Forth itself, so Akashic's words are its library as they stand,
    and its lists are the lists Lisp code uses, so data passes between them
    unchanged.
31. The language names what code needs and never names a chip, and where
    code runs never changes what it means. It names plain data, objects,
    capabilities and tasks, a task being work whose result comes later. Work
    moves between engines only as whole tasks, which the program marks, so
    no call hides a hand-off. A machine description outside the program says
    which engines a machine has and what each does well, and the compiler
    and job service place each task from it: a task that calls device words
    runs where the device is, and object-heavy work goes where objects are
    cheap. On Leviathan, a word placed on MegaPad compiles to an ordinary
    Forth word that any Forth code can call, and a word placed on LM1
    compiles to LM1 code. On a machine with one engine and a software
    collector, all of it runs there.

    Words carry checked stack effects, as Factor's do, written as Forth's
    stack comments, and their kinds describe data. Plain data, such as cells
    and spans (memory the caller provides and bounds), is managed by hand.
    Objects, such as records, lists and strings, are collected. The compiler
    inserts Part 9d's windows and handles itself, while hand-written Forth
    keeps to 9d's rules by hand; whether that insertion works well is
    untested. Cells wrap at 64 bits, and integers are exact. Quotations are
    ordinary lists (decision 34). Authority reaches code as capability
    values passed to it; where that rule meets Akashic's existing words,
    which reach devices directly, is open (`dev/ideas/language.md`). Code
    that uses no plain memory and holds authority only as capabilities could
    compile to the sandbox's artifact format, while the sandbox's own source
    language stays as its documentation ratifies it.
32. Work on the language starts with the checker when release work begins,
    and the language grows alongside Parts 2, 3 and 8 without being one of
    the leading items (decision 10). Its first version is small. The
    checker's core tracks kinds through stack shuffles and the return stack
    and needs nothing from LM1, so it is built first and tried on existing
    Akashic code, because tracking refs through shuffles and quotations is
    the part most likely to prove awkward; syntax waits for it. The compiler
    emits Forth source, which KDOS loads like any other, and it runs in the
    image builder on the host. The toolchain places everything on MegaPad,
    with LM1 only collecting through 9d's library, so an LM1 backend, tasks
    on LM1, and running lists built while a program runs come after the
    release.

    The object side follows once 9d's window and handle rules are specified,
    since the compiler inserts them, and those rules depend on the link
    specification in Part 8. Until then, 9d's rules are written precisely
    enough for a checker to enforce them. The release never waits for the
    language. Whether Study's concept map, the release's first managed-data
    component, is written in it is decided when those rules are specified
    (D12). The subset the release uses is frozen, so later changes to the
    language don't force changes to release code. The language stays small,
    Forth plus kinds, objects, capabilities and tasks, so that it doesn't
    split the library across a third language.
33. All of this repository's development material lives in `dev/`: this
    plan, ideas still being worked out, and notes for later releases. An
    idea is worked out in `dev/ideas/` until it is decided, then moves into
    the plan, and a dropped idea is deleted rather than kept. The release is
    cut on a release branch that removes `dev/`, and the release tag goes on
    that branch, so main keeps `dev/` for the next release. The repository
    is public, so everything in `dev/` is public once pushed, and material
    that must stay private goes elsewhere.
34. The language's quotations are ordinary lists of words and values, as in
    Joy, so programs are data. A quotation can be run, and it can be taken
    apart or built with the same words as any other list, so code that
    writes code is list work, and a quotation captures a value by holding it
    rather than through closure machinery. These are the lists Lisp code
    uses (decision 30), so Lisp code can build or read programs in the
    language. A task, being a quotation and its inputs, is an object that
    any engine can receive, and whichever engine the job service picks
    compiles it for itself (decision 31).

    A quotation can't change once it is made, so new code means a new list,
    and the compiled code cached for each list stays valid. A list holds the
    words themselves rather than their names, so a later definition can't
    silently change what an existing list does, which KDOS's
    case-insensitive names would otherwise make easy. Literal quotations are
    built once, when their word is compiled, and only quotations built while
    a program runs are allocated. Running a built list is like Forth's
    EVALUATE, so built code passes the same kind checks and authority rules
    as any other code. Whether sandboxed code may run lists it builds is
    open.
35. Sound Lab, Worlds and Observatory are not in the first release, and
    neither are audio output, with the sound synthesis libraries that feed
    it, or data graphics: the plots, waveforms and instruments of the
    rich-terminal series path, which only those applets use. Their tests
    stay in their repositories and run on request, but they leave the
    regression gate and the full runs of decision 36. The shared UIDL and
    rich-terminal modules still load the data-graphics widget, so its code
    stays in the image until the library inventory (Part 1d) settles it.
    The canonical Desktop stops loading Sound Lab as a built-in, so none of
    its code sits on the gate's image; Desk runs it, as it runs
    Observatory, outside the Desktop. Desk's launcher stays. Other journeys
    already open applets through it, an installed applet and Pad in one,
    Daybook and Streams in another, so nothing replaces Sound Lab in the
    canonical Desktop journey unless a need appears. The journey drops its
    Sound Lab stages, and the workspace AGENTS.md's description of the gate
    changes with it. A journey of Desk with one applet runs only when that
    applet, or code it loads, has changed. The transport tests behind
    Streams stay, since Streams and the internet are in the release, and
    MegaPad's system test waits for the release's final run.
36. A test runs only when something it reads has changed, in any of the
    system's repositories. The unit is a test file or a standalone journey,
    each run in a process of its own, so nothing one run holds in memory can
    reach another's result. Its key records what that process and every
    Python program it starts actually read: each file opened for reading and
    each directory listed, which takes in the sources `build_image` puts on
    a disk image, the BIOS and KDOS files the harness reads from MegaPad, and
    fixtures; each module imported, native extensions included; and the
    interpreter, arguments and environment the run starts with,
    PYTHONHASHSEED pinned among them. Files the run writes itself, such as
    its disk image, are outputs rather than inputs. Inputs are read from
    what the tools already know, never declared by hand, because a stale
    declaration silently skips a test that would have failed.

    A test whose key matches a passing run is skipped and reported as
    unchanged since that run. A run that starts a program other than Python
    always runs, because that program's reads go unrecorded; wrappers such
    as `env`, which only start another program, don't count. A wall-clock
    limit doesn't force a rerun: when nothing a test reads has changed, a
    rerun can differ only through the host's load, which says nothing about
    the code. A full run at the end of each of this plan's parts, before
    each merge and before each release, checks the selection, and any result
    it failed to predict counts as a missed input, fixed in the recording.
    One tool in this repository runs MegaPad's, Akashic's and LM1's tests
    and keeps one record of passing runs for all of them, and each
    repository's tests still run without it, with nothing skipped
    (Part 1h).

## 3. Open decisions

Each entry gives what is needed to decide it without other reading: the
background, the options with their consequences, a recommendation, and what
it blocks.

**D8. LM1's product scale.** This sets what LM1 becomes as a chiplet. Today's
spec describes a standalone accelerator: 256 tiles in 32 clusters, 256 KiB of
SRAM per tile and 2 MiB per cluster, and 32 GiB of HBM3E. The per-tile and
per-cluster SRAM are toy-scale, and the FPGA build fits only one 8-tile
cluster. The principle is decided: LM1 matches what the ecosystem demands of
the rest of Leviathan, neither above nor below production scale. The numbers
are chosen when LM1 work starts. Three questions remain:

- how much on-chip memory each tile and cluster gets, since more per tile
  means fewer tiles in the same area;
- how many tiles and clusters that demand calls for;
- where the chiplet's main memory lives.

For main memory there are two options, and the chips share memory under
either (decision 29). Its own memory, such as HBM or LPDDR, is fast and
keeps LM1's heap and collector traffic off MegaPad's bus, but it makes the
package more complex, and MegaPad's reads of managed data then cross the
link. MegaPad's memory, reached over the link, is cheaper and simpler, but
LM1's heap and collector then share bandwidth with Desk. Recommended: a
short sizing study as the first step of Part 8b. It measures the work
Leviathan gives LM1, which is sandbox jobs and Desk's managed data
(decisions 27 and 28), including how often MegaPad reads that data and how
much traffic the collector adds. It also sets an area budget relative to
MegaPad and compares the bandwidth of each memory option. The study comes
back with numbers before anything is chosen. Blocks Part 8b.

**D12. Whether Study's concept map is written in the language.** The concept
map is the release's first managed-data component (Part 9d), and the
language's first version is built alongside Parts 2, 3 and 8 (decision 32).
The choice is made when 9d's window and handle rules are specified. If the
language can then compile the concept map, with the compiler inserting the
windows and handles, the map is written in it: the map is written once, and
the compiler rather than hand-written Forth keeps 9d's rules. If not, the
map is written in Forth under 9d's rules. The release doesn't wait for the
language either way. Recommended: decide on evidence, namely the checker
working on existing Akashic code and the compiler handling a draft of the
concept map's code. Blocks the concept map's implementation in Part 9d.

## 4. Where things stand

These facts come from read-only surveys of each repository on 2026-10-27,
updated for the work done since.

### MegaPad (`megapad/`, 915 tracked files)

- Several entry points run the machine: `megapad.py` (emulator, simulator
  or hybrid mode), `cli.py`, `session_viewer.py` and `session_ctl.py`.
  `diskutil.py` makes and inspects disk images, and `make build` builds both
  native extensions.
- The native simulator needs `_megaforth_native`, and the emulator needs
  `_mp64_accel`. Both build with pybind11 and C++17. There is no
  requirements file and no package metadata. The README asks for Python
  3.12, `docs/getting-started.md` says 3.8 or later, and the extensions in
  the tree are built for 3.13.
- The hosted simulator supports exactly one full core, by contract
  (`docs/simulator-contract.md`). It hard-codes its device windows
  (`OneCorePlatformMMIO` in `simulator/platform.py`), and hybrid routines get
  no MMIO. The emulator runs several full cores in lock-step on one host
  thread, and new devices attach to it easily.
- About a third of the 61 top-level files are benchmarks or one-off scripts.
  Four are temporary import aliases: `megapad64.py`, `system.py`,
  `devices.py` and `accel_wrapper.py`.
- MP64FS holds at most 128 entries, counting files, directories and links
  together, and at most 32 MiB, with names of up to 23 characters. The
  Desktop image is already 32 MiB. An August record (`FILESYSTEM_HANDOFF.md`
  in the workspace root) found about 2.6 MiB of it free.
- The rich-terminal viewer and compositor live here, in
  `session_viewer.py` and `rich_terminal/`.
- Networking has loopback, UDP and TAP backends (`nic_backends.py`). The
  UDP backend only links emulator instances. Reaching real servers takes the
  TAP device `mp64tap0`, whose one-time setup needs `sudo`, plus forwarding
  rules for internet access.
- The MMIO map appears to have room above +0xC20, and port-bridge ports 4, 5
  and 7 are unassigned.
- Its 326 test files run only through Makefile targets such as
  `make test-sequential`, which build the accelerator first;
  `tests/conftest.py` stops a bare `pytest` run.
- Nothing in MegaPad mentions LM1.

### Akashic (`akashic/`, 697 library files in 31 groups)

- The applets are Desk, Pad, File Explorer, Daybook, Grid, Agent, Sound
  Lab, Streams, Library, Observatory and Worlds. The canonical Desktop opens
  Pad, Explorer, Daybook, Grid and Agent, and offers Streams as a built-in.
  It doesn't load Library, Sound Lab, Observatory or Worlds. There is no
  Forth console applet.
- Only the test harness builds images: `local_testing/akashic_tui.py`
  (37,370 lines, 160 profiles). A profile's roots expand to their REQUIRE
  closure. Large closures are packed into chunk files of up to 120 KiB,
  because MP64FS can't hold one file per module.
- The canonical profiles are test setups. The Agent uses a scripted
  provider, and Streams reads recorded fixtures.
- The runtime keeps one Practice head per system. A head holds identity,
  bound resources, grants, a manifest, a schema, an export root and
  policies. `docs/runtime/practice.md` specifies entry lenses, which say what
  a Practice opens, but they aren't built; an image's autoexec decides what
  opens. Development images enroll a blank Practice, which the harness README
  calls "not secure Practice enrollment".
- The filesystem bindings are MP64FS (read and write), FAT (read-only) and
  ext4 (read-only, plus a staged write mode labelled a
  "controlled/trusted-local preview", limited to 1 KiB blocks and 256-byte
  inodes). The image builder and the boot path use MP64FS only.
- The 543 test files all live in `local_testing/`. The harness reads
  `bios.asm` and `kdos.f` from the MegaPad checkout beside it, and some
  tests start `megapad.py` as a separate process.

### LM1 (`lm1/`, 215 tracked files)

- It holds a spec (`spec/00` to `spec/07`), RTL (28 SystemVerilog files), an
  FPGA target, a Python emulator with a C accelerator, an assembler and a
  Lisp compiler. Its own OS and desktop were archived on 2026-10-27
  (Part 1c).
- The spec still describes a standalone SoC: 256 tiles in 32 clusters,
  256 KiB of SRAM per tile and 2 MiB per cluster, 32 GiB of HBM3E, PCIe,
  NVMe, 100 GbE and an on-die display engine. It defines no link to MegaPad.
  It contradicts itself on the SRAM total (§3.1) and on the cluster count in
  its floorplan (§12.1).
- The emulator has 172 tests in its own harness, and nine of them fail on
  main. Eight GC tests use a `CARD_SIZE` that commit 6a40bd2 replaced with
  `card_shift` in February, and `alloc_nursery_overflow` fails. The same
  nine failed before the split.
- 41 RTL tests run on Verilator against a single core; the tile, cluster and
  GC-engine RTL is not simulated. The FPGA flow stops at synthesis, at about
  90K LUTs for one 8-tile cluster.

### Recent work elsewhere

The frames-follow-change plan (Akashic
`docs/rich-terminal/FRAMES-FOLLOW-CHANGE.md`) finished on 2026-11-01 and
landed on both components' main branches. Its worktrees and the components'
other local branches were retired the same day, so work in `megapad/` and
`akashic/` now happens in their main checkouts.

## 5. Parts

### Part 1. Organization

Goal: everything has one clear place, and we know what ships.

**1a. This repository's layout** (Proposed).

```
fantasy-engine/
  dev/               development material, left out of the release (decision 33)
    PLAN.md          this plan
    ideas/           ideas still being worked out
  README.md          the front door: what the system is, how to install and run it
  docs/              user documentation only
  configurations/    one folder per sample configuration
  fantasy_engine/    the package behind the fantasy-engine command
  <lock file>        component repositories and commits (Part 1b)
  tests/             release checks
```

`README.md` arrived early, on 2026-11-05. It says what the system is and what
it stands for, for readers who aren't engineers, and it ends with where the
work stands. With the first configuration that runs (Part 4), how to install
and run it replaces that ending and `docs/` arrives, so from then on nothing
outside `dev/` describes plans. Nothing in this repository copies component
source.

**1b. The lock file** (Decided). A small file here names each component's
repository and commit. The build takes exactly those commits, with
`git archive` from the checkouts in the workspace or from a fresh clone when
they're absent, so a dirty or switched checkout can't leak into a build.
Moving a component forward is a one-line commit here, and the file's history
records which combination passed which checks. Proposed: since pushes are
made by hand, the tool warns when a recorded commit isn't on its component's
remote yet. Done when one command assembles every component at
its recorded commit from a fresh checkout.

**1c. Split LM1 into the chiplet.** Done on 2026-10-27, LM1 commit 0afe4af.
The tag `archive/lm1-os-desktop-e19aebd-20261027` keeps the removed work: the
BIOS, the VFS, the display model, the Crystal desktop with its toolkit, fonts
and icons, the font compiler, the BIOS, OS and desktop design notes,
`BUILD-PLAN.md`, `ideas.md`, and their tests. Test phase 7 kept its
block-device and `JR` tests. The console, block I/O, byte-memory and debug
traps stay until the MegaPad link carries the chiplet's I/O. The GC and
runtime-setup traps stay as stand-ins for hardware controls that Part 8b
defines. The SoC spec's chiplet revision is Part 8b.

**1d. Library inventory** (Decided; criteria Proposed). A library ships when
it loads on the current system, its tests pass, and either something that
ships uses it or it is useful and documented on its own. Each library gets
one status: ships, needs work (with the gap named), or out.

A first, static pass ran on 2026-10-27 against Akashic main 95a06427. It
read the REQUIRE closures of all 160 harness profiles and looked for each
module's path in the test files. Appendix A has the counts by group. In
short:

- 317 of the 697 files load in the canonical Desktop, 346 in some applet and
  420 in some profile.
- 277 files load in no profile. 188 of those are named in tests, and 89 are
  named nowhere.
- The 89 include eight AT Protocol OAuth variants, 18 audio synthesis,
  effects and sequencing modules, nine concurrency primitives, 18 math
  modules, 11 render modules, the three font modules, both CBOR modules, and
  ten tui files. Among the tui files are the `scroll.f` and `split.f` drafts,
  which are known not to work.

The static pass only shows where to look:

- A library outside every profile can still be a real feature. The Agent's
  OpenAI and Codex providers and Streams' AT Protocol connectors sit outside
  the canonical Desktop, which uses a scripted provider and fixtures.
- The blockchain code, including its contract VM, belongs to a planned later
  phase of the chain. It is not scrap, however quiet it looks.

Next steps:

1. Load each group's modules on the current system and run its tests, one
   group at a time, within the workspace's resource rules. The full rich
   test set peaks near 9.2 GiB in one process, so it runs in pieces.
2. Record each library's status in Appendix A.
3. Each library that is out gets a decision: Akashic finishes it, retires
   it by archive tag, or keeps it outside the release.

Done when every library has a status and every library that is out has a
decision.

Progress (2026-11-09). Sixty-nine Akashic test files could not judge their
libraries: fifty counted failures without failing a test, nineteen held no test
that pytest collects, and most matched their expected text against KDOS's echo
of the program. They now fail a test whose check fails, reading only what the
program printed (Akashic 1188fd77, f61886a9, 2bb7ffdc). Thirty-three of them
load their modules from the modules' own REQUIRE lines, which in turn needed
thirteen of the chain's REQUIRE lines to name the folders they meant (Akashic
5648118e). Under the test tool, 43 of the 63 suites run pass, and test_tx passes
its 24 lighter tests. Among the passes are the concurrency primitives, base64,
URL, headers, HTTP, WebSocket, the web server, router and middleware, templates,
string, fmt, UTF-8, the font stack, FFT, tile compositing, the STARK AIR,
Ed25519, consensus, persistence, RPC, sync and cross-chain verification. Twenty
fail on what their libraries do:

- utils/string.f's STR-PARSE-TOKEN returns two cells for empty input where it
  promises four, so the ITC compiler underflows at the end of every source: 18
  ITC tests, and probably the contract VM's eight, which compiles through it.
  The fix is one line.
- concurrency/cvar.f's CV@ consumes its variable before UNLOCK, which then
  releases a garbage lock number. MegaPad's emulator raises a Python TypeError
  for that MMIO offset instead of a bus fault.
- The STARK verifier accepts three tampered traces. Either it leaves the
  boundary constraints unchecked or the tests' tampering still yields a valid
  trace; it needs a careful look.
- The sparse Merkle tree's prove and verify checks run to their step limits, and
  two of its tests call words that no longer exist. The light client and witness
  suites, which use it, fail too, as do block (nine tests), state (two) and node
  (two). The gossip and mempool suites exceed the tool's fifteen-minute limit.
- Taxonomy lookups and the TUI package manifest print memory from wild
  addresses, and the TUI package suite names a constant its module no longer
  defines.
- The SML tree (three tests), state tree (four), LEL (two), profile (two), SIMD
  tile transpose (one) and web request (one) suites expect values their
  libraries no longer give.

The four audio suites still cannot load their modules: their lists are stale,
and 65 REQUIRE lines in the audio modules name the wrong folder (37 write audio/
from inside audio/, 28 name a math module bare). test_sphincs passed the first
nine of its fifteen lighter tests before a 45-minute cap. The five SPHINCS+
tests with budgets of 50 to 100 billion steps, three there and two in test_tx,
wait on one measured run. The suites' own run loops lack forth_snapshot.py's
stall detection, so a hung load costs the tool's whole limit; moving them onto
ForthSnapshot would remove about sixty copies of that loop.

**1e. Retire the old working copies.** Older copies of LM1 and of this
repository outside the workspace hold nothing the workspace lacks once this
repository's commits are pushed and the old LM1 copy's never-committed
memory-hierarchy simulator has a decision. They are deleted only on
approval.

**1f. Component fixes the release depends on** (Proposed). MegaPad's four
temporary import aliases go. `bios.rom` is either built or tracked, not both;
it is tracked although `.gitignore` lists it. One Python version is stated
and used.

**1g. Licences and notices** (Decided).

1. Each repository gets the Apache-2.0 and CC BY 4.0 texts, following the
   REUSE specification: an SPDX licence and copyright line in every file
   that can carry one, and a `REUSE.toml` entry for files that can't, such
   as fonts, images and binary fixtures. `reuse lint` runs with each
   repository's tests.
2. `cdp1802.pdf`, RCA's 1802 manual, leaves MegaPad's tree, and the README
   links to a public copy instead. Its history stays (decision 18).
3. The generated Unicode tables carry the Unicode licence notice, and their
   generators write it: MegaPad's `rich_terminal/text_data.py` and Akashic's
   `akashic/text/unicode-tables.f`.
4. Roboto's Apache-2.0 text and DejaVu's Bitstream Vera licence sit beside
   the fonts.
5. Third-party material that is already recorded stays as it is: the CC0
   AT Protocol test vectors, with their source commit, and the
   public-domain photo.
6. MegaPad's README states that earlier versions remain CC0, and LM1's MIT
   metadata line is replaced.

Done when `reuse lint` passes in every repository.

**1h. Test selection** (Decided). Decision 36's selection is built first
among the release's parts, since every later part's testing goes through
it. The tool lives in this repository, as the first piece of the
`fantasy_engine/` package in Part 1a's layout.

1. Check whether `build_image` gives identical output for identical inputs,
   and look for anything else a run depends on that the recording can't
   see, such as a guest clock that follows the host's.
2. Record what each run reads. An audit hook, installed through
   `sitecustomize` in every Python process the run starts, notes each file
   opened, each directory listed, each module imported and each program
   started.
3. Run each test file and journey in a process of its own, compute its key,
   keep the keys and results of passing runs, and skip the tests whose keys
   match. Every skipped test is reported with the run it relies on and that
   run's component commits, so evidence notes cite what actually ran.
4. Drive each repository's tests through its own entry point: MegaPad's
   through its Makefile targets, Akashic's with the MegaPad checkout on the
   path, and LM1's through its emulator harness. Decision 35's tests form a
   set of their own that runs on request.
5. Let the record fill as units run in ordinary work. The selection can
   judge a unit only after its first run through the tool, so until then a
   slice's tests are found as before, by searching for the tests that read
   the files it changes. The first full run comes at the end of Part 2, as
   decision 36 asks at the end of each part, and a measurement of how many
   tests a typical slice skips follows it. The measurement also shows
   whether the 37,000-line harness file, which about 180 test files import
   and about one Akashic commit in seven has touched since October, reruns
   too much to stay whole.
6. Change Section 7's working rules and the workspace AGENTS.md so that the
   end of each slice runs the release's tests through the selection.

Done when every repository's tests run through the tool, a slice's run
skips the tests whose inputs the slice didn't change, and a full run finds
no result the selection failed to predict.

Progress on 2026-11-03. Step 1 is done. Built three times, twice with
PYTHONHASHSEED 0 and once with another seed, the pad, daybook, desktop and
rich desktop images held the same files, contents and layout every time.
Only MP64FS's per-entry time stamps differed, and no guest code reads them:
KDOS defines `DE.MTIME`, and nothing calls it. The guest clock is the one
input found that the recording can't see. Emulator runs from the harness
start it at zero or at the fixed sample date, but runs through the
simulator server, the physical journeys' path, start it at the host's
current time and tie its uptime to the host's monotonic clock, and Daybook,
the Agent's dispatch, mandates and Streams read it. Proposed: test runs
through the server pass a fixed start time, so their dates become a setting
the key records.

Steps 2 and 3 are built in `fantasy_engine.testing` (commit 43ab1a9), and
step 4 covers every test file of MegaPad, Akashic and this repository and
every LM1 batch: 323, 544, 2 and 39 units. Decision 35's 35 units form the
`outside` set, MegaPad's system test the `final` set that the release's
final run adds, and the remaining 872 units the `release` set that runs
with each change. Akashic's canonical Desktop no longer composes Sound Lab
(Akashic bb0b327b), and its journey runs Sound Lab's stages only when the
Desktop does; the checks of Desk with Sound Lab or Observatory alone moved
into a test file of their own in the `outside` set. Step 6 is done: Section
7 and the workspace AGENTS.md now send tests through the selection. The
standalone journeys aren't units yet: the physical driver runs `git` to
bind its evidence to the trees, and a unit that starts a program other
than Python always runs, so the journeys need a way to keep that binding
out of their keys. Two writes per MegaPad invocation came
to light:
the Makefile's accelerator step copies its 3 MB library into place even
when nothing changed, and pytest's cache plugin rewrote a 1.1 MB file of
test IDs. The tool builds the accelerator once per run and turns the cache
off, which brings a MegaPad unit from about 4.5 MB of writes to about
0.2 MB. Proposed: MegaPad's `accel` target writes nothing when the library
is current, which removes the remaining copy from every test target.

### Part 2. Storage: ext4

One of the three leading items (Decided): reasonable ext4 support, not
necessarily complete.

Goal: a configuration's image holds the shipped libraries as ordinary files
on ext4, with room to grow.

Today, MP64FS holds 128 entries and 32 MiB, the Desktop image already fills
32 MiB, and modules are packed into chunk files. Akashic's ext4 binding reads
ext4, and its staged write mode is a preview limited to 1 KiB blocks and
256-byte inodes. The image builder and the boot path handle MP64FS only.
MegaPad's storage controller takes 32-bit sector numbers, and
`docs/block-volume-contract.md` adds MBR and GPT volumes. Frames-follow-change
part 4 added a read-only settings volume on a second storage controller,
which landed on both main branches on 2026-11-01.

"Reasonable" means what an alpha tester needs, done well (Decided):

- **It never damages data.** Everything it does is correct and survives a
  crash. Akashic's writer already journals each change, and `e2fsck` on the
  host checks the result.
- **It refuses cleanly.** Anything it can't do fails with an error, using
  ext4's own feature flags.
- **It covers everyday use.** That means saving new files and saving over
  old ones, growing and shrinking files of realistic size, renaming,
  deleting, and making and removing folders of a few hundred entries.

Images are standard ext4, which host tools (e2fsprogs) can build and check.
Akashic's writer already creates, deletes and renames files and folders,
makes links, truncates, and grows files, each only in bounded cases. For the
alpha it closes the gaps those cases leave (Decided, 2026-11-04). The first
is general allocation, meaning growing and shrinking files beyond them. The
second is renaming over an existing file, which is the usual safe way to
save. The third is folders, since the standard names renaming and folders of
a few hundred entries. Today, making a folder or a link, or renaming into a
full directory block, fails; a folder can be removed only while it has never
grown past one block; a folder cannot be renamed within its parent, nor moved
unless it is empty; and in an indexed folder the first name in each block
cannot be deleted. The writer keeps 1 KiB blocks, which are legal ext4 and
fine at these sizes. Symlinks, extended attributes, permissions, quotas,
encryption and online resizing wait.

Each family of operations closes its gaps through one general routine, and
the bounded cases it replaces are deleted rather than kept beside it
(Decided, 2026-11-04). That means one extent tree of any depth, one block
allocator, and one directory insert that create, mkdir, link and rename
share. Code and tests that already pass get reworked, and the writer ends
with less code and no gaps between cases.

Each step-2 slice ends with its own tests plus one or two tests of every
other ext4 operation, and the whole ext4 suite runs once, when the step is
done (Decided, 2026-11-04). The suite is one selection unit of 797 cases and
about five hours, and every change to the driver reruns all of it, so a full
run per slice would add about 30 hours of waiting across the step.

Each transaction the writer makes today scans every other file's block map,
to prove that no other file owns a block the transaction allocates, rewrites
or frees, so even a small save costs more as the volume holds more files. The
writer instead proves once per mount, at its first write, that the block
bitmaps match what the files and the fixed metadata hold, with each block
owned once, and every transaction after that checks only its own changes
(Decided, 2026-11-04). Freeing a block needs its bit set and the file's old
map holding it once, allocating needs its bit clear, and the file's new map
must differ from its old one by exactly the blocks allocated and freed. That
last check is new: without it, a block mapped by mistake was caught only
when a later transaction's scan reached it. Nothing else writes a mounted
volume, so the proof and these checks answer everything the scan asked: the
guarantee is unchanged, and each save costs only what it touches. Production
ext4 trusts its bitmaps instead and leaves the cross-file check to fsck; the
device has no fsck, and that check is part of the writer's guarantee. The
writer refuses every write to a volume whose bitmaps and files disagree
anywhere, where the scan refused only a write that touched the mismatch. The
proof's working memory is one bit per block and one block of scratch, sized
from the volume and kept for the mount beside its other workspaces, because
every transaction's check reuses it while mount cleanup's journal writer
occupies the end of the mount arena (revised 2026-11-05).

Every configuration boots with three volumes (Decided, 2026-11-05).

- **System volume, ext4, read-only.** KDOS, the system modules, and Akashic's
  libraries and applets as plain files.
- **Settings volume, read-only.** Changed only from the host, as
  frames-follow-change part 4 built it.
- **User volume, ext4, writable.** Documents, Practice records and a
  learner's own modules. The Practice head files, which the runtime writes,
  move here.

A read-only system volume keeps the installed libraries safe (Part 7), and
resetting a system means replacing one file. The BIOS keeps loading KDOS
from a small MP64FS boot volume (Decided, 2026-11-04), because teaching the
BIOS ext4 would bloat it. The boot volume therefore also holds whatever KDOS
loads before it can mount ext4.

Steps:

1. Settle the boot path. Done: a small MP64FS boot volume.
2. Close the writer's alpha gaps: general allocation, renaming over an
   existing file, and folders. Prove block ownership once per mount rather
   than on every write.
3. Teach KDOS to load modules from ext4 volumes.
4. Build ext4 images on the host.
5. Move the image builder (Part 4a) onto them.

Done when the canonical Desktop boots from an ext4 system volume that holds
its modules as individual files, a user volume takes everyday writes and
passes the host's `e2fsck`, also after a run killed mid-write, and the
physical journey passes.

Progress (2026-11-04). The ext4 suite could not run until two repairs.
MegaPad's storage takes `file_holds_media` when media is replaced (MegaPad
2faa96d8), which the suite's two calls lacked, and the profile's pinned
e2fsprogs 1.47.4 is now built from its pinned source archive under
`~/.cache/fantasy-engine/e2fsprogs-1.47.4`. On the 64 MiB, 1 KiB-block
fixture, appending one 1 KiB block cost 230M guest steps and 5,079 block
reads, with 21 writes and 11 flushes, which is at least 2.3 s at the SoC's
100 MHz clock. Most of that repeated proofs inside one write. The ownership
scan re-read and re-verified the same descriptor and bitmap blocks for each
of the 1,281 blocks the resize inode maps. The journal-membership table
hashed by block number and probed thousands of slots per lookup. Each
checkpoint rebuilt the 4,096-entry journal map three times. With those
repetitions gone and every check kept, an append costs 79M steps and 953
reads. The rest follows from the per-write design: each checkpoint
reauthenticates the whole mount three times, each write walks every other
inode's map, both grow with the volume rather than the write, and each block
is its own transaction.

Progress (2026-11-04, continued). Writing file data is now one general
routine (Akashic e4047fca), which replaced eight bounded one-block cases. It
overwrites, grows a file from any end, and writes past the end, leaving
holes. It works on extent trees of any depth, inserting, splitting and
growing them as the kernel does, and it allocates runs next to the data
before them, setting up a never-used block group on that group's first
allocation. One call commits as much as one journal transaction holds under
the writer's profile, so a larger write spans several transactions.
Appending 20 KiB to a 54-byte file on the 1 KiB-block fixture, with a
16-home, 16-block profile, takes two transactions and 271M guest steps,
mount and unmount included; before, each 1 KiB block was its own append of
79M steps. The driver is 648 lines shorter and its tests 7,115. Truncation,
deleting large files, folders and renaming over a file remain. Six suite
failures predate this work and sit in that ground: the recovery-anchor and
preflight-authority tests, two orphan-cleanup flush-fence cases, an RMDIR
refusal test and a truncate-to-zero union test.

Truncation is one general routine too, for anything that fits one transaction
(Akashic db9cccc4). A shrink releases every block past the new end at any
extent depth and a growth leaves a hole, replacing the bounded same-block
shrink and the depth-zero truncate-to-zero. A truncate whose release does not
fit one transaction refuses; truncation across transactions, with the orphan
file carrying the file over a crash, comes next.

Truncation across transactions now runs through the orphan file (Akashic
aace7883), as the kernel's ext4 truncates. When a shrink's release does not
fit one transaction, the first transaction commits the new size behind a
modern orphan record and release passes free the blocks past the new end.
The record's final cleanup, folded into the last pass when its homes fit,
zeroes the tail of the block that holds the new end and removes the record.
A crash therefore leaves either the old file or a record that mount recovery
finishes with the same passes. Recovery runs them on a linked orphan's extent
tree at any depth, so it also finishes truncations the kernel leaves behind,
and before its first write it still refuses a union whose blocks another file
maps. The bounded truncate-to-zero insertion and the bounded linked cleanup
it fed are gone. Truncating the fixture's 340-extent depth-two file to zero
takes 1.37 billion guest steps with mount and unmount, at least 13.7 s at the
SoC's 100 MHz clock, and each release pass repeats the scan of every other
file's map that proving ownership once per mount replaces next. Deleting
large files, folders and renaming over a file remain after that. Of the six
older suite failures, the truncate-to-zero union test went with the bounded
truncate it tested (Akashic db9cccc4), and five remain.

Block ownership is now proved once per mount (Akashic 6ebed51d). Mount
recovery proves it before its first orphan cleanup and every mounted mutation
at its entry, so the proof runs only on mounts that write, at 28.6 million
guest steps on the fixture. Every staged transaction then checks that its
maps change by exactly the blocks it allocates and frees, in one routine that
writing, truncation, the release passes and every namespace operation share.
The per-write scans are gone, and the driver is 284 lines shorter. Ten cases
that create, link, unlink, remove, rename and set attributes and reclaim
orphans at mount take 32% fewer guest steps than at aace7883, between 23% and
39% fewer per operation with the proof included; appending 20 KiB takes 191
million steps, down from 271 million, and truncating the 340-extent file to
zero takes 1.29 billion, down from 1.37 billion. The five older suite
failures are unchanged, and the preflight-authority case among them fails the
same way at aace7883. Deleting large files, folders and renaming over a file
come next.

Deleting a file now runs the release passes too (Akashic 524ae3fa). Removing a
file's last name commits the removal behind a modern orphan record, and
release passes free its map from the end, at any extent depth or for any
legacy block map; the pass that frees the rest also deletes the inode when
the deletion's homes fit. The closed unlink, the last close of an open file
and mount recovery share the passes, so recovery also deletes files of any
size and map that Linux leaves unlinked, and it finishes a truncation of a
linked file with a legacy map. The bounded deletion shapes and their
classifier are gone, and the driver is 189 lines shorter. Unlinking the
fixture's 340-extent file, which 6ebed51d refused, takes 1.44 billion guest
steps with mount and unmount, at least 14.4 s at the SoC's 100 MHz clock.
Twenty reclaim and unlink cases of the older shapes take 1.1% more steps
than at 6ebed51d: the mount reclaims between 10% fewer and 5.6% more, and a
sparse file's unlink under a six-home writer 18% more, because the pass's
room check counts the superblock twice and splits that cleanup in two.
Each pass also validates the file's whole map several times, so the work
of deleting a fragmented file grows with the square of its runs: a
186-block legacy map with data in every branch takes 1.0 billion steps.
Both costs sit in the release passes, which truncation shares. Nine older
suite failures remain, the five and four write-prefix cases whose tables
expect the inode home first, all failing the same way at 6ebed51d. One
more test that failed at 6ebed51d now passes: recovery answers a linked
directory as unsupported recovery, where it answered with the write
path's feature detail. Folders and renaming over a file come next.

Release passes now walk each map once per write and count the superblock
once (Akashic a5c9cb70). Every step of an operation authenticated its
target by validating its whole map again, so under a sixteen-home,
one-revoke writer a release pass of a 120-extent file walked the map
twelve times and the pass that deletes the file eighteen. A validation
that passed is now kept until a write could change what it read, which a
journal write on a mount with proved ownership cannot. A plain pass
therefore walks the map three times: once in its checkpoint's reload after
the home writes, and twice in the map check, before and after the
transaction. The deletion pass walks it once, and every other operation
gains the same way. The room check counts the superblock once, so a
sparse file's unlink under a six-home writer is one transaction again. The
280 cases of the deletion and truncation families and the sample that pass
on both commits take 8.3% fewer guest steps than at 524ae3fa, and the
slowest is 0.17% slower. Unlinking the 340-extent file takes 534 million
steps, where it took 1.44 billion, at least 5.3 s at the SoC's 100 MHz
clock; truncating it to zero across transactions takes 661 million, where
it took 1.25 billion; and deleting the 186-block legacy map takes 883
million, 12.6% fewer. A plain pass's largest cost is now its checkpoint's
three reloads of the whole mount, 66 of its 119 million cycles in the
120-extent case, which grow with the volume rather than the file. Nine
older suite failures remain, and the six these families reach fail as at
524ae3fa. Folders and renaming over a file come next.

Checkpoints now skip the work that nothing has changed (Akashic b7e0242a,
c592897d and c98dd55a). A complete reload of the mount stands until something
outside the journal is written, and a transaction's data that takes only free
blocks, as an append at a block boundary or a hole fill does, leaves it
standing. While it stands, the reload before a checkpoint's home writes, the
one after its journal release and the first of the two at unmount validate
only the journal; the reload after the home writes stays complete,
and every checkpoint now rereads each block it wrote, as only the orphan modes
did before. Each range's static role is checked against a sorted table of the
volume's metadata, built once until the next write outside the journal, in
place of reading every group's descriptor for each range, and one journal
validation checks the journal map's checksum once. Truncating the fixture's
340-extent file to zero across transactions takes 434 million guest steps,
where it took 661 million, and unlinking it 388 million, where it took 534
million, at least 3.9 s at the SoC's 100 MHz clock. A 100-byte overwrite
costs 36 million cycles, where it cost 53 million, and an append or a hole
fill 25 million. The 303 cases that pass on both commits take 18.3% fewer
steps than at a5c9cb70. Of the 587 write-path and source-only cases run, ten
fail, all from before this work: the nine, failing as at 108fe9fd, and a
tenth that has failed since 6ebed51d, where the ownership proof refuses a
depth-one write whose index points into the journal ring as a block with two
owners, EXT4-D-DATA-MAP, before the journal check whose EXT4-D-JOURNAL the
test expects. A normal and safe mode like Desk's is recorded as a possibility
in the driver's document (Akashic 108fe9fd) and waits until these repeats are
gone. More rounds of the same kind come first, then folders and renaming over
a file.

Map walks and reloads now repeat less still (Akashic 5fe67063, 11733a88 and
6b8a3201). A walk that claims or releases the blocks it reads leaves the check
of a leaf's earlier entries for a shared block to those claims, which refuse
the same block first. A plain validation compares each entry with its two
neighbours among the leaf's earlier ranges, kept sorted, in place of every one
of them. The orphan plan's build keeps the counts its reload took in the same
map epoch, so a complete reload reads the orphan file once. Truncating the
340-extent file to zero across transactions takes 279 million guest steps,
where it took 434 million at c98dd55a, and unlinking it 279 million, where it
took 388 million. A 100-byte overwrite costs 29 million cycles, where it cost
37 million measured the same way, and the 172 cases that ran on both commits
with the same work take 15.6% fewer steps. The largest costs left are the
orphan file's count, a quarter of a small write, and in a large file's walks
the allocation checks, which load a descriptor and read a bitmap for every
extent.

Each group's block bitmap location and descriptor flags are now recorded once
per map epoch (Akashic 00bccf41), so the allocation checks of a map walk read
them in place of loading the group's descriptor for every range, about 11
thousand cycles a load. Truncating the 340-extent file across transactions
takes 237 million guest steps, where it took 279 million at 6b8a3201, and the
107 cases that ran on both commits with the same work take 8.2% fewer steps.
The rounds of removing repeated work end here, each having removed only work
that repeated a check on unchanged inputs. Since 108fe9fd, where they began, a
100-byte overwrite has gone from 53 to 29 million cycles, unlinking the
340-extent file from 534 to 241 million guest steps and truncating it to zero
across transactions from 661 to 237 million, at least 2.4 s at the SoC's 100
MHz clock. The run found an eleventh older suite failure, from 6ebed51d: a
test that fills every bitmap but one block, which no file owns, expects the
write to answer VFS-E-NOSPC, and the ownership proof now refuses that volume
as EXT4-D-DATA-MAP first. Folders and renaming over a file come next.

Renaming over an existing regular file now works (Akashic ab7b6c7d), the usual
safe way to save. The victim's record takes the source's inode and the
source's record joins its predecessor, so nothing is inserted, and the victim
loses that link in the same transaction. A final victim enters the orphan file
there, under a rename form of the final unlink's sealed certificate, whose
every image the checkpoint rebuilds from the media, and drains as an unlinked
file does: at once when closed, on its last close when open, and through mount
recovery after a crash. A remaining link needs another name in the same
folder, as unlink's does. A source that is the first name of an indexed leaf
is still refused, as unlink's is, until the folders' general removal lifts
that gate for both. Eight new cases pass, and so do the 214 cases of the
rename, unlink, rmdir and orphan-cleanup families with the sample, except the
older rmdir refusal failure, unchanged. The folders' shared directory insert
is next to be tested.

Create, mkdir and link now share one directory insert (Akashic c7da101d) that
grows a full folder as the Linux kernel does: a full one-block folder becomes
an index, a full block splits, a full index root gains a level, and a full
index node splits, up to the two levels ext4 allows without its large-directory
feature. New blocks come from the general allocator and extent tree, and the
bounded routines, their own allocator and map editor are gone. The insert
authenticates its folder once where the old paths did it up to five times, so
the first writes the tests measure take 2 to 62% fewer guest steps; on a
journal already active, its measuring pass stages the insert once more than
before. Its 61 cases, the source pins, the rename-over cases and the sample
pass. Removal and rename still accept only folders of one index node, so a
folder grown past that refuses them until the general removal and the folder
rename, the next two slices, use the insert's authentication.

Unlink and rmdir now share one directory removal (Akashic e570e175), run by
the same engine as the insert and admitting every folder it admits. A name
leaves its block as the kernel removes it, joining the record before it or,
as a block's first name, leaving its record unused, so the first name of an
index block is no longer refused. Rmdir removes any empty folder, of any size,
mode or shape, through the orphan file and the release passes a deleted file
uses, as the kernel's rmdir does; a small folder's removal therefore takes
three journal transactions where the bounded one-block path took one. Freed
folder blocks take no revoke records, since the journal is reset after every
transaction and nothing earlier is left in it to cancel. The removal's tests,
the sample, the unlink, rmdir, rename and orphan-cleanup families and the
insert's cases pass, 275 cases and one more skipped by design, and the older
rmdir refusal failure now passes under the new rules. Rename keeps its own
removal until the folder rename, the next slice, moves it onto this one and
the shared insert. The folder walk still refuses unused records that keep a
name, as older kernels and debugfs leave them, so a folder they edited refuses
writes.

Rename now runs on the shared removal and insert (Akashic dd0082e7), which
closes the step's last gap. The source's name leaves its folder as a removal
takes it out, and the new name enters as an insert places it, growing a full
folder, or takes over an existing name's record. Files and folders move within
one folder or between two, over a file or an empty folder, and a moved
folder's `..` follows it. Rename's own code is gone with the old removal it
called, so the driver went from 29,873 lines before the folder work to 26,884.
The rename tests and a sample of the insert and removal pass. The whole
test_vfs_ext4 unit then ran once, in 2 h 46 min: 797 cases passed, one was
skipped by design, and 12 failed. Ten are older failures recorded above, and
the eleventh recorded one, the rmdir refusal, passes. One more older failure
surfaced, identical at 00bccf41: a write into a file's own extent node is
refused with the right diagnosis, but the test also expects the write's
staging cell to name the node's block, and that cell holds zero. The last
failure came from renaming over a file, whose new capability the binding test
did not yet expect; Akashic 15345ea0 adds it. Eleven older failures remain.
The VFS name cache now limits folder size more than the writer does. ext4 has
no single-name lookup, so the VFS loads all of a folder's names before it
resolves, creates, links, renames or removes one there, and its cache holds at
most 64 KiB of names per mount. A folder with more names than that, about
1,600 of 20 characters, therefore answers VFS-E-NOMEM to every path through
it, before the writer runs.

The VFS no longer loads a folder to check one name (Akashic def0488c): ext4
looks a name up by reading only the blocks it can be in, and create, link,
rename and remove check names that way, so a folder of 2,000 names resolves,
reads, takes new names and loses them with only the names in use cached. The
name pool grows from the mount's storage in 4 KiB chunks, with a free list for
each name size (Akashic d96c1b0d), so a listing caches every name that storage
holds. The cache finds a name and a file's cached record through two hash
indexes, and a folder's names are linked both ways (Akashic 45cd7310), so
listing a folder costs time in proportion to its size: all 2,000 names list in
218 million guest cycles, where 1,600 had taken about 2 billion guest steps. A
binding that cannot look up a single name (MP64FS, FAT, the RAM disk) no longer
walks the cache for eviction on every path it resolves (Akashic dd27cfbc). After
a checkpoint tears, ext4 answers a read of a block the failed transaction was
writing with the writer's recorded fault, not the torn or stale block, and
answers every read so when the commit published and then failed the writer's own
check (Akashic a6b626ab). The four VFS test suites now fail a test whose check
fails, and their checks read only what the program printed, not KDOS's echo of
the source, which had let most MP64FS and FAT checks pass whatever the code did
(Akashic 0f1d76ce). A survey found the same gaps in 69 other Akashic test files:
in 50 the checks count failures without raising, and 19 are script-only drivers
that pytest and the test tool never run; most of the 69 also match text against
the echoed source.

### Part 3. The simulator: multicore and chiplet modules

One of the three leading items. Steps 3a to 3d are decided.

Goal: the native simulator runs MegaPad as the multicore machine it is, and
loads chiplets such as LM1 as modules.

Today, the hosted simulator supports exactly one full core by contract, and
its device windows are hard-coded. The emulator runs several full cores in
lock-step on one host thread. MegaPad's `docs/parallel-multicore-simulation-plan.md`
and `docs/microcore-kernels-plan.md` record directions accepted on
2026-10-27:

- each core runs a round on its own host thread, and the round commits only
  when no core touched memory another core wrote, falling back to lock-step
  otherwise;
- microcores run kernel words;
- Desk's screen path stays on one core, and extra cores take background
  work.

The same documents name two hardware gaps. The RTL microcore has 16
registers where microcores are specified with 32, and boot sets up no
microcore stacks.

- **3a. Multicore model.** The simulator models every full core, and then
  the clusters and their microcores. Its guest-visible results match the
  emulator's lock-step: host scheduling never picks a winner. Its contract
  (`docs/simulator-contract.md`) moves from one core to the full topology
  and the deterministic scheduler that contract already describes as the
  target.
- **3b. Parallel speed.** Speculative rounds land as a separately reviewed
  optimization, with one-, two- and four-lane differential evidence, as the
  parallel simulation plan requires.
- **3c. Attaching devices.** A general way to attach devices replaces the
  hard-coded windows, so new hardware doesn't need simulator surgery.
- **3d. Chiplet modules** (Decided). The simulator imports a chiplet's model
  as a C++ module through a defined interface. The interface covers link
  endpoints, shared memory windows, interrupts, reset, and the module's place
  in the simulator's rounds. Proposed: the emulator loads the same modules,
  so both backends run the same chiplet model.
- **3e. Microcore gaps.** Before microcore simulation is built, the RTL
  microcore widens to 32 registers and decodes the REX prefix's extension
  bits as the full core does, and boot gives microcores their stacks. A test
  runs R16 to R31 on a microcore in both the RTL and the emulator.

Done when:

- Desk runs on the multicore simulator, with background work on extra
  cores;
- differential tests agree with the emulator;
- a test chiplet module loads and exchanges messages over its link;
- the canonical Desktop journey passes.

As the workspace rules require, results here are reported as simulator
improvements, separate from device performance.

### Part 4. Building and running configurations

Goal: one command lists, builds and runs any configuration.

Today, only the test harness builds images. A Desktop session takes
`akashic_tui.py serve` plus MegaPad's `session_viewer.py`, and the canonical
profiles are test setups.

- **4a.** In Akashic, move image building (closure, linking, layout and
  validation) out of the test harness into a supported tool, and make the
  harness use it. This repository calls that tool at the recorded commit and
  doesn't copy it.
- **4b.** A configuration format: one TOML file per configuration, matching
  Desk's own TOML settings. It names the Practice, the machine's memory
  and cores (every configuration runs on the whole of Leviathan, LM1
  included), the volumes and their
  sizes, and any extra resources.
- **4c.** The `fantasy-engine` command, with `list`, `build NAME`, `run NAME`
  and `new NAME FROM`, which starts a configuration of your own from an
  existing one. `run` builds when needed, starts the simulator and opens the
  viewer.
- **4d.** Host setup: one documented way to install the dependencies and
  build the native extensions. Networking needs either a path that works
  without administrator rights or a clear one-time setup step.

Done when, on a clean Linux machine and following `README.md`, `run` boots
the canonical Desktop configuration from recorded commits, and the physical
journey passes through the command.

### Part 5. Practices open configurations

Goal: a configuration's Practice decides what opens and what it can reach.

- **5a. Entry lenses.** A Practice declares the applets that form its entry
  and what each opens with, and Desk realizes them when the Practice
  activates. `docs/runtime/practice.md` already splits the roles this way:
  the Practice owns the declaration, and Desk owns layout, focus and
  activation order.
- **5b. Bindings** for each configuration's resources: documents, sample
  files and library roots.
- **5c. Proper enrollment.** Release images enroll their Practice properly
  instead of the blank development Practice. This needs a design that
  follows `docs/runtime/practice.md` and `DESK_ECOSYSTEM_CONTRACT.md`.
- **5d. One Practice per image** fits today's single-head runtime. The
  multiple-Practice catalog (Gate 13A in `DESK_ECOSYSTEM_CONTRACT.md`) stays
  deferred unless a configuration needs several Practices.
- **5e. Desk without applet code** (Decided). Desk's own code is written for
  particular applets in three places, and each moves out. Desk loads
  modules from Daybook and the Agent and runs their services itself:
  Daybook's reminders and scheduled runs, and the Agent's runtime and
  dispatch. Reminders must fire while Daybook is closed, so something that
  stays running has to own them, but that owner becomes a general service
  Desk hosts. Desk's service table also hands some services only to named
  applets (the Agent's to the Agent, Daybook's automations to Daybook, the
  resource directory to Library), and a closed table lists the Daybook,
  File Explorer and Streams actions the Agent may call. The table is closed
  so that no applet can widen the Agent's reach. That protection stays, but
  the rules themselves move into the Practice, which sets what may act.
  Finally, Desk caps installed applets at 32 with a fixed constant, which
  gives way to a count sized from need.

Done when each configuration's applets open from its Practice, no applet is
queued by autoexec text, and Desk's code names no applet.

### Part 6. The sample configurations

Each configuration is a Practice built around a task or subject
(decision 25). It binds the material the work needs, sets what the Agent,
scheduled actions and sandboxed tools may do there, and opens what the work
calls for. LM1 is part of the machine in all of them. It runs their
sandboxed tools, holds managed data where their work builds it up, and runs
Lisp where the work calls for it.

The set (decision 26). The names are working names, and the set can change.

- **Everyday.** Daily computing, the internet included: writing, documents
  and PDFs, files, plans and reminders, tables, Bluesky and news feeds, and
  an Agent with a real AI provider. It binds the user's documents, calendar
  and feeds. The Agent may read, draft and set reminders; anything it would
  post or send waits for the user's approval.
- **Workshop** (the System Practice, Part 7). Learning the machine by
  building with it, in Forth on MegaPad and Lisp on LM1 side by side. It
  holds the shipped library sources read-only, a writable workspace, a
  console for each language, the reference docs, and the sandbox for trying
  modules safely. The Agent explains code and helps write modules.
- **Study.** A Practice around one subject: a corpus of documents and PDFs,
  feeds that follow the subject, notes and tables, and a growing map of the
  subject's concepts. The map is new work, kept on LM1 as managed data. The
  Agent summarizes with citations to the bound sources. It ships with one
  sample subject, whose material must be freely licensed.
- **Publishing.** Writing for the web: drafts in Pad, a small website served
  by the machine's own web server, a feed of the posts, and posting to
  Bluesky. The feed writer is new work, since Akashic's feed code only reads
  today. The Agent drafts, and nothing goes out without approval.
- **Investigation** (after the alpha). The Detective Box idea as a
  Practice: evidence kept tamper-evident with hashes from MegaPad's SHA-3
  hardware, a timeline, a graph of people, things and events, and findings
  that link back to their evidence. The graph lives on LM1 as managed data,
  and Lisp reasons over it. The Agent may propose links but never changes
  evidence. It needs new parts, an evidence store and the graph, so it is
  the largest.

Sound Lab, Worlds and Observatory don't ship in the first release
(decision 35).

For each configuration:

1. Design its Practice, covering what it binds, what may act there and
   what opens, and write its configuration file.
2. Check the real providers and connectors it uses, which the test profiles
   never exercise. The Agent needs a provider key, and Streams fetches live
   feeds.
3. Script a journey through its main tasks, and run it narrowly, with Desk
   and that configuration's applets. The canonical Desktop journey stays the
   regression gate.
4. Document it (Part 10).

Done when each of the first four runs from the command and passes its
journey. Investigation follows the same steps after the alpha.

### Part 7. The System Practice

Needs Parts 1d, 2 and 5, and Part 9e for its Lisp half.

Contents:

- the shipped libraries' sources, bound read-only from the system volume;
- a writable area on the user volume for the learner's own modules;
- Pad and Explorer;
- a Forth console applet, which doesn't exist yet. It loads modules from the
  user area and shows what they do;
- the Lisp console on LM1 (Part 9e), so both of Leviathan's engines can be
  learned side by side;
- the library reference, readable from inside the system.

Its authority covers reading the library sources, writing only in the user
area, and loading modules from there.

Done when a learner can open a shipped library's source, write a module that
uses it, load it and watch it run, do the same in Lisp on LM1, and nothing
inside the system can change the installed libraries.

### Part 8. The LM1 chiplet

One of the three leading items (Decided). It runs alongside Parts 2 to 7.

- **8a. Repair the emulator's failing tests.** Eight GC tests use the
  `CARD_SIZE` that 6a40bd2 replaced with `card_shift`, and
  `alloc_nursery_overflow` fails. The chiplet module in 8d builds on this
  emulator, so it should start from green.
- **8b. Product-scale design** (needs D8). Revise the spec for a chiplet:
  - Size it for production. The current 256 KiB per tile and 2 MiB per
    cluster are toy-scale. Interface limits stay fixed at
    production size, and resource limits follow need.
  - Replace PCIe, NVMe, 100 GbE and the display engine with the MegaPad
    link, since MegaPad handles I/O and Desk handles the display.
  - Decide where its memory lives: the chiplet's own HBM, or MegaPad's
    memory (D8).
  - Have MegaPad load and start the Lisp runtime over the link.
  - Turn the GC and runtime-setup traps into real hardware controls.
  - Make capability mode a required part of the chiplet. The spec lists it
    as optional, and the sandbox relies on it to keep jobs apart
    (decision 27).
  - Let LM1 compute with full 64-bit integers that wrap, as the sandbox's
    do, without the collector mistaking them for references. LM1's fixnums
    hold 63 bits and trap on overflow.
  - Give the objects MegaPad holds a place among the collector's roots, and
    define how MegaPad's writes reach the collector's records (decision 28).
    The spec's roots cover only LM1's own registers, stacks, tables and
    buffers.
  - Answer two questions raised in March. Does LM1 get its own built-in
    self-test, or does MegaPad run one for the whole package? Does LM1 adopt
    MegaPad's hard QoS and one-instruction-per-cycle rule?
  - Fix the spec's contradictions in §3.1 and §12.1.

  As with MegaPad, the RTL describes the chip we want. Fitting the FPGA is
  not a gate.
- **8c. The MegaPad link.** One spec covers doorbells and mailboxes, the
  shared memory both chips read and write (decision 29), handing jobs over
  and results back, MegaPad's side of managed data (handles, writes and the
  windows in Part 9d), interrupts, loading and starting programs, errors,
  reset and test access. Proposed: the spec lives in `lm1/` as the chiplet's
  interface, and MegaPad implements the host side.
- **8d. The chiplet module** (Decided). LM1's model is written in
  accelerated C++ as a chiplet module that MegaPad's simulator imports
  through Part 3d's interface, and it is built from `lm1/`. The Python
  emulator stays the reference model until the module is complete. It may be
  wrong too, so the spec is the referee: when the two disagree, check the
  spec, fix whichever is wrong, and add a test.
- **8e. RTL.** Bring the chiplet up to the new spec, and simulate its tiles,
  clusters and GC engines; only a single core is simulated today. Add
  MegaPad's side of the link to its SoC.
- **8f. Toolchain.** The assembler and compiler follow any ISA changes. They
  build the Lisp runtime image that MegaPad loads.
- **8g. Verification.** Link conformance tests, including handles that
  survive a collection and writes from MegaPad, are shared by the chiplet
  module, the Python reference and both RTL sides. Close the RTL test gaps
  listed in `docs/test_gap_ideas.md`.

Done when the simulator loads the chiplet module, MegaPad boots the chiplet
over the link and runs Lisp work sent from KDOS, and both RTL sides pass the
same link tests.

### Part 9. LM1 in the system software

Needs Part 5 and Parts 3d, 8c and 8d.

LM1 first shows what it does for Desk (decision 27): the sandbox's jobs run
on it, and the data Desk wants collected lives in its heap. Lisp is how
LM1's side is written, and the Lisp console is a learning tool.

- **9a.** MegaPad gets a system module for the chiplet, following
  `networking.f` and `rich-terminal.f`. MegaPad owns it, and system
  composition loads it at boot, since every configuration runs on
  Leviathan.
- **9b.** Akashic gets a library that hands work to the chiplet through that
  module's public interface. As with `rich-terminal.f`, Akashic doesn't
  REQUIRE a path into MegaPad or copy the module.
- **9c. The sandbox on LM1.** LM1 gets an engine that runs verified sandbox
  plans with the same results, limits and budgets as the MegaPad engine. The
  job service lends runnable jobs to LM1 the way it lends them to worker
  cores, so applets use the sandbox as before. In October 2026, Akashic's
  sandbox benchmark (`local_testing/sandbox-vm-bench.f`) measured one
  typed-value read at about 29,000 MegaPad cycles, almost all of it spent
  checking the value's handle in `value.f`. On LM1, typed values are tagged
  words, and capability mode keeps references from being forged and each
  job apart from the others, so the hardware does that checking. The
  MegaPad engine stays the reference until LM1's engine passes the same
  sandbox tests.
- **9d. Managed data.** Through the library in 9b, Desk code creates LM1
  objects in shared memory, and LM1's collector frees whatever nothing uses.
  Forth code works with these objects under four rules:
  1. It reads them directly.
  2. It writes them only through the library's words, which keep the
     collector's records.
  3. It works with them only inside short windows, and inside one it can
     follow references freely. The collector waits for open windows to
     close before it moves shared objects.
  4. Anything it keeps past a window, it keeps as a handle. The collector
     treats handles as in use and updates them when objects move. Each
     handle belongs to an owner Desk already tracks, such as an applet, a job
     or a document. All of an owner's handles are released when the owner
     closes, as the job service already discards a closing owner's jobs.

  Forth code therefore never frees managed objects one at a time or sizes
  them in advance, while its own buffers, such as screen frames, stay as
  they are. Study's concept map is the first user, and Investigation's graph
  follows after the alpha. Feeds, records and documents move over as applets
  need them. The rules are written precisely enough for a checker to enforce
  them (decision 32). Whether the concept map is written in the language or
  in Forth is decided when these rules are specified (D12).
- **9e. The Lisp console.** An applet talks to the chiplet's REPL, which
  `spec/06` places in the chiplet's own runtime along with the compiler. The
  Workshop includes it for learning (Part 7), and any Practice can. Pad holds
  programs, and examples come with it.

Done when, through Desk's normal path:

- an applet's sandbox job runs on LM1 and returns the MegaPad engine's
  result;
- managed data keeps the objects Forth holds through collections, and
  closing an applet releases every handle it held;
- in the Workshop, a journey evaluates Lisp expressions and runs a program
  written in Pad on LM1.

### Part 10. Documentation

The documents are written fresh for users. Component docs are sources of
facts, but they aren't copied as they stand, since many mix reference
material with plans and status.

The planned set:

- getting started: install, run a configuration, make your own;
- Desk and its applets;
- Practices, and what each sample configuration's Practice does;
- programming the machine: Forth, KDOS and the libraries;
- the LM1 chiplet: the sandbox on LM1, managed data, and Lisp;
- hardware reference: MegaPad, LM1 and the link;
- library reference, covering shipped libraries only (from Part 1d).

Some facts conflict between component documents. Settle each at its source
while writing:

- the Python version;
- the BIOS word count (481, 540 or 550);
- the Desktop's memory (320 or 384 MiB);
- the missing `rtl/README.md`.

The component repositories keep their own development docs (decision 22).

Done when every shipped feature is documented by use and function, and no
document talks about plans, phases, evidence or history.

### Part 11. Qualification and release

Needs every other part.

1. Package what people download: prebuilt images, the command, and native
   extensions built for the x86-64-v2 baseline instead of `-march=native`
   (decision 23).
2. Generate the notices from the lock file's commits: a third-party notices
   file and an SPDX software bill of materials. pybind11's BSD licence ships
   with the native extensions, which compile it in. Any bundled Python
   package brings its licence; pygame, under LGPL-2.1, stays a separate
   package users can replace. e2fsprogs, under the GPL, is not bundled; the
   command uses the copy on the user's machine.
3. Run a ScanCode scan of every repository at its recorded commit. It must
   find no unattributed copied code and no stray licence texts, and its
   result is recorded.
4. Settle what lies beyond licences. Check the release's names against
   existing trademarks (decision 20), and confirm the export position of the
   encryption code (open source, standard algorithms). The docs say that the
   Agent's and Streams' outside services run under their own terms, with the
   user's own keys.
5. Run the final checks: every configuration's journey, the canonical
   Desktop journey, the sandbox tests on both engines, LM1's emulator and
   RTL tests, and the link conformance tests. Each heavy run goes alone,
   under the workspace rules.
6. Tag every component with the release version, 0.1.0 (decision 21), and record the
   commits.
7. Write release notes about function.
8. Cut a release branch that removes `dev/`, and tag this repository on that
   branch (decision 33).

This is standard practice for an open alpha. Before anything commercial,
or before a chip is made, a lawyer reviews the licensing.

## 6. Order

- Part 1 comes first, and within it Part 1h (Decided), since every later
  part's testing goes through its selection. Part 1c is done, and 1b, 1d and
  1g proceed. Part 1g touches every repository; in `megapad/` and `akashic/`
  it goes on branches of its own.
- Three parts lead (Decided): Part 2 (ext4), Part 3 (the simulator) and
  Part 8 (the LM1 chiplet). They proceed side by side, mostly in different
  repositories: Part 2 in Akashic and MegaPad, Part 3 in MegaPad, and Part 8
  in `lm1/`.
- Parts 4 and 5 can proceed alongside them. Part 4's image builder moves
  onto ext4 once Part 2 lands.
- The language (decision 32) starts with the checker when release work
  begins and proceeds alongside the three leading parts, without being one
  of them. Whether Study's concept map uses it is decided when 9d's rules
  are specified (D12).
- Part 6 needs Parts 4 and 5. Part 7 needs Parts 1d, 2 and 5. Part 9 needs
  Part 5 and Parts 3d, 8c and 8d.
- Within Part 9, the sandbox (9c) comes first, since it needs only jobs
  handed over and results handed back. Managed data (9d) follows once the
  link's handle and window rules are specified, and Study's concept map
  waits for it.
- Part 10 grows with every part and is finished before Part 11.
- Each part starts on approval.

## 7. Working rules

The workspace `AGENTS.md` governs this work. In short:

- Commit each coherent slice once it is green, with an informative message
  that presents each decision and its reasons as the project's own, without
  quoting or narrating anyone. Commits carry the maintainer's authorship, and
  an assistant is credited only by a Co-Authored-By trailer. Never amend a
  commit; add a new one. The maintainer pushes.
- Test narrowly while working: unit and focused tests, then Desk with only
  the applets a change touches. Tests run through the selection (Part 1h):
  at a slice's end, the units already on record run with the tests the
  slice's changes reach, and each is skipped when nothing it reads has
  changed. The physical Desktop journey is the regression gate. It runs
  once, at the end of a slice that touches the rich path, the simulator or
  Desk.
- Run heavy tests one at a time, within the 900-second and 3.5 GiB guards,
  and send throwaway output to `/dev/shm`.
- Retire old work with an annotated `archive/` tag, then remove it. Don't
  leave legacy paths behind.
- Keep fixed limits only for interfaces and formats, sized for production.
  Size resources from need.
- The real device comes first. Say plainly when a change helps only the
  simulator.
- Update this plan when a decision is taken. Work out ideas in `dev/ideas/`,
  move each into the plan once it is decided, and delete dropped ideas
  rather than keeping them.

## Appendix A. Library inventory, first pass

Static counts from 2026-10-27, taken against Akashic main 95a06427:

- "Canonical Desktop" counts files in the `desktop-apt1` profile's REQUIRE
  closure.
- "Any applet" adds the Library, Worlds and Observatory profiles.
- "Any profile" covers all 160 harness profiles.
- "No profile, no test" counts files that load in no profile and whose path
  appears in no test file.

| Group | Files | Canonical Desktop | Any applet | Any profile | No profile, no test | Last change |
|---|---:|---:|---:|---:|---:|---|
| atproto | 34 | 2 | 2 | 5 | 8 | 2026-10-12 |
| audio | 32 | 8 | 8 | 12 | 18 | 2026-10-10 |
| cbor | 2 | 0 | 0 | 0 | 2 | 2026-03-12 |
| concurrency | 13 | 4 | 4 | 4 | 9 | 2026-10-10 |
| consensus | 1 | 0 | 0 | 0 | 0 | 2026-03-12 |
| css | 2 | 1 | 1 | 1 | 0 | 2026-03-12 |
| dom | 3 | 0 | 0 | 0 | 0 | 2026-03-12 |
| font | 3 | 0 | 0 | 0 | 3 | 2026-03-12 |
| game | 12 | 0 | 0 | 0 | 0 | 2026-03-26 |
| interop | 41 | 32 | 33 | 41 | 0 | 2026-10-18 |
| knowledge | 1 | 0 | 0 | 0 | 0 | 2026-03-12 |
| liraq | 7 | 5 | 5 | 5 | 1 | 2026-10-17 |
| markup | 6 | 4 | 4 | 5 | 0 | 2026-10-12 |
| math | 49 | 21 | 23 | 23 | 18 | 2026-10-17 |
| media | 5 | 5 | 5 | 5 | 0 | 2026-10-13 |
| net | 40 | 2 | 2 | 31 | 1 | 2026-10-13 |
| node | 1 | 0 | 0 | 0 | 0 | 2026-10-10 |
| numeric | 10 | 0 | 0 | 0 | 2 | 2026-09-30 |
| pdf | 17 | 17 | 17 | 17 | 0 | 2026-10-13 |
| persistence | 9 | 0 | 9 | 9 | 0 | 2026-07-26 |
| render | 16 | 3 | 3 | 3 | 11 | 2026-10-12 |
| runtime | 19 | 19 | 19 | 19 | 0 | 2026-10-12 |
| sandbox | 13 | 13 | 13 | 13 | 0 | 2026-10-09 |
| security | 26 | 0 | 0 | 3 | 1 | 2026-10-12 |
| sml | 2 | 0 | 0 | 0 | 0 | 2026-03-12 |
| store | 10 | 0 | 0 | 0 | 1 | 2026-07-27 |
| syndication | 5 | 5 | 5 | 5 | 0 | 2026-07-17 |
| text | 14 | 13 | 13 | 13 | 1 | 2026-10-12 |
| tui | 247 | 138 | 155 | 179 | 10 | 2026-10-18 |
| utils | 46 | 25 | 25 | 27 | 3 | 2026-10-13 |
| web | 11 | 0 | 0 | 0 | 0 | 2026-10-10 |
| **All** | 697 | 317 | 346 | 420 | 89 | |

Part 1d fills in each library's status: ships, needs work or out.
