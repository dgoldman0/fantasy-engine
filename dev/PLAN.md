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

Status on 2026-10-27: the plan is locked in. Part 1 (organization) is under
way: Part 1c, the LM1 split, is done, and Part 1d, the library
inventory, has its first static pass. The Chimera prototype that used to
live here is kept by the tag `archive/chimera-a499082-20261027`, and commit
54616ae removed it from the tree.

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

All were taken on 2026-10-27.

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
30. Leviathan gets a language of its own that spans both chips. Existing
    languages each assume one kind of memory. Lisp, Factor, Joy, Erlang and
    Pony let a collector own every value, stacks included, while Forth has
    no managed values at all. The nearest exceptions each miss part of it:
    PreScheme compiles its manual level ahead of time, so the two never mix
    at run time; Rust tracks lifetimes precisely but has no collected side;
    and HP's RPL ran its two levels over one collected memory on one chip.
    WebAssembly with garbage collection has decision 28's split, raw memory
    plus managed references kept there only as handles, but it is a compile
    target rather than a language people write. None treats two instruction
    sets as one program.
    The language is new rather than a derivative. Factor comes closest, but
    its libraries need Factor's VM, and what would change (one collected
    heap, a tagged stack, open authority) is its core, so a derivative would
    keep only its look. The compatibility that matters is with Akashic's
    Forth and LM1's Lisp data: the language's raw side is Forth itself, so
    Akashic's words are its library as they stand, and Lisp lists written in
    it are LM1 lists.
31. The language's shape is set. Words carry checked stack effects, as
    Factor's do, written as Forth's stack comments with kinds added: cell,
    span (memory the caller provides and bounds), ref, handle, and LM1's
    typed values. New raw words compile to ordinary Forth words that any
    Forth code can call. A window is syntax. Inside one, refs can be
    followed freely; the checker refuses a ref that would leave it, a keep
    word turns a ref into a handle tied to an owner, and writes to managed
    objects compile to the library's barrier words, so Part 9d's rules
    become compile errors rather than conventions. Cells wrap at 64 bits,
    and integers are exact. Quotations on the raw side can't outlive the
    word that made them, since an escaping closure needs allocation;
    escaping closures are LM1 closures. Each word or module names the chip
    it runs on, and a call across chips is an explicit job sent through the
    job service, whose result arrives later. Managed words get authority
    only as values passed to them. The subset with no raw memory, holding
    authority only as capabilities, could compile to the sandbox's artifact
    format, while the sandbox's own source language stays as its
    documentation ratifies it.
32. Work on the language starts once Part 9d is built. Whether the first
    release waits for it is open (D12). The first step is a checker for 9d's
    rules alone, because tracking refs through stack shuffles and quotations
    is untested and may prove awkward; syntax waits for that checker. Until
    then, 9d's rules are written precisely enough for a checker to enforce
    them. The language stays small, Forth plus kinds, windows and placement,
    so that it doesn't split the library across a third language.
33. All of this repository's development material lives in `dev/`: this
    plan, ideas still being worked out, and notes for later releases. An
    idea is worked out in `dev/ideas/` until it is decided, then moves into
    the plan, and a dropped idea is deleted rather than kept. The release is
    cut on a release branch that removes `dev/`, and the release tag goes on
    that branch, so main keeps `dev/` for the next release. The repository
    is public, so everything in `dev/` is public once pushed, and material
    that must stay private goes elsewhere.

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

**D12. Whether the first release waits for the language.** Decisions 30 to
32 give Leviathan a language that spans both chips and start its work once
Part 9d is built, beginning with a checker for 9d's rules. The release
already waits for the LM1 chiplet (decision 3), and the language adds a
second dependency on LM1's side. There are three options. The release can
ship without the language, which keeps its scope as it stands and puts the
language in a later release. It can wait for the checker alone, which then
checks the managed-data rules in Akashic's Forth code and ships as a tool,
while the language's syntax follows later. Or it can wait for a usable
language, which gives the Workshop both chips in one program but holds the
release on work whose hardest part, tracking refs through stack shuffles and
quotations, is untested. Recommended: ship without waiting, and include the
checker if it is ready in time, without making it a release requirement.
Blocks nothing before Part 9d; it decides whether Part 11 waits.

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
- Nothing in MegaPad mentions LM1.

### Akashic (`akashic/`, 697 library files in 31 groups)

- The applets are Desk, Pad, File Explorer, Daybook, Grid, Agent, Sound
  Lab, Streams, Library, Observatory and Worlds. The canonical Desktop opens
  Pad, Explorer, Daybook, Grid and Agent, and offers Sound Lab and Streams as
  built-ins. It doesn't load Library, Observatory or Worlds. There is no
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
- The 512 test files all live in `local_testing/`.

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

### Work under way elsewhere

The frames-follow-change plan (Akashic `docs/rich-terminal/FRAMES-FOLLOW-CHANGE.md`,
branch `feature/frames-follow-change`) has parts 0 to 5 done and parts 6 to
10 to go. Its worktrees under `.worktrees/frames-follow-change/` must stay
untouched while their journeys run. Release work in `megapad/` and
`akashic/` goes on branches of its own.

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

`README.md` and `docs/` arrive with the first configuration that runs
(Part 4), so nothing here describes plans. Nothing in this repository copies
component source.

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
part 4 added a read-only settings volume on a second storage controller; that
work is on its branch and not yet merged.

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
alpha it closes two gaps: general allocation, meaning growing and shrinking
beyond those cases, and renaming over an existing file, which is the usual
safe way to save. It keeps 1 KiB blocks, which are legal ext4 and fine at
these sizes. Symlinks, extended attributes, permissions, quotas, encryption
and online resizing wait.

Proposed: every configuration boots with three volumes.

- **System volume, ext4, read-only.** KDOS, the system modules, and Akashic's
  libraries and applets as plain files.
- **Settings volume, read-only.** Changed only from the host, as
  frames-follow-change part 4 built it.
- **User volume, ext4, writable.** Documents, Practice records and a
  learner's own modules. The Practice head files, which the runtime writes,
  move here.

A read-only system volume keeps the installed libraries safe (Part 7), and
resetting a system means replacing one file. One design question remains.
The BIOS loads KDOS from MP64FS today, so either a small MP64FS boot volume
stays, or the BIOS learns to read ext4.

Steps:

1. Settle the boot path.
2. Close the writer's two alpha gaps: general allocation, and renaming over
   an existing file.
3. Teach KDOS to load modules from ext4 volumes.
4. Build ext4 images on the host.
5. Move the image builder (Part 4a) onto them.

Done when the canonical Desktop boots from an ext4 system volume that holds
its modules as individual files, a user volume takes everyday writes and
passes the host's `e2fsck`, also after a run killed mid-write, and the
physical journey passes.

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

Done when each configuration's applets open from its Practice, and no applet
is queued by autoexec text.

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

Sound Lab and Observatory are not configurations as they stand; whether
they ship as applets follows from the inventory (Part 1d).

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
  them (decision 32).
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

- Part 1 comes first. Part 1c is done, and 1b, 1d and 1g proceed. Part 1g
  touches every repository; in `megapad/` and `akashic/` it goes on branches
  of its own.
- Three parts lead (Decided): Part 2 (ext4), Part 3 (the simulator) and
  Part 8 (the LM1 chiplet). They proceed side by side, mostly in different
  repositories: Part 2 in Akashic and MegaPad, Part 3 in MegaPad, and Part 8
  in `lm1/`.
- Parts 4 and 5 can proceed alongside them. Part 4's image builder moves
  onto ext4 once Part 2 lands.
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
  the applets a change touches. The physical Desktop journey is the
  regression gate. It runs once, at the end of a slice that touches the rich
  path, the simulator or Desk.
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
