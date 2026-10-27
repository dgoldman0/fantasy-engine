# Plan for the first release

This repository is the home of the first release of the fantasy-computing
ensemble. The release brings MegaPad, Akashic and the LM1 Lisp chiplet
together as one system that people can install and use. This plan covers the
work from now until that release ships.

`PLAN.md` is the only development document in this repository. Everything
else here will document use and function. This file is deleted when the
release ships, and its history stays in git.

Status on 2026-10-27: Part 1 (organization) has started. The Chimera
prototype that used to live here is kept by the tag
`archive/chimera-a499082-20261027`, and commit 54616ae removed it from the
tree.

Section 1 says what the release is. Sections 2 and 3 list the decisions
taken and the decisions still open. Section 4 records where each component
stands today. Section 5 sets out the work in ten parts, each with its steps,
what "done" means and what it needs first. Sections 6 and 7 give the order of
the parts and the rules the work follows.

Three labels mark the status of each item. **Decided** means Daniel has
decided it. **Proposed** means it still needs Daniel's approval. **Open**
means a decision Daniel has yet to make.

## 1. What the release is

- **One system** (Decided). MegaPad is the Forth machine: its native
  simulator and emulator, BIOS, KDOS and system modules. Akashic supplies the
  libraries, Desk, the applets and Practices. LM1 is a Lisp chiplet that
  works beside MegaPad as a partner device: MegaPad handles control, I/O and
  number crunching, and LM1 runs Lisp. LM1's README gives "Leviathan" as a
  working name for the combined chip.
- **The LM1 chiplet is in it** (Decided). There is no release until it is.
- **Sample configurations** (Decided). A handful of ready-made boot setups
  each open one Practice, and together they cover what the system does. One
  of them is the System Practice, a place to learn the system by building
  with its own libraries.
- **Documentation about use and function only** (Decided).
- **It runs on a PC** (Proposed). People run the native simulator and watch
  it through the rich-terminal viewer. The emulator stays available as a
  second backend.
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
4. The LM1 repository becomes the chiplet only. Its own OS and desktop are
   retired the same way as Chimera: an archive tag, then removal (Part 1c).
5. Practices keep their name. Each sample configuration is built around one
   Practice.
6. One Practice is about the system itself, including its libraries.
7. The libraries get an inventory. Only working, current libraries ship, and
   scrap stays out.
8. Release documentation covers use and function only. This file is the one
   exception, and it goes when the release ships.

## 3. Open decisions

Each entry names what it blocks.

**D1. How the release locks component versions.** Daniel is weighing this.
It blocks Part 1b. There are two usual ways:

- Git submodules. This repository records each component's commit itself,
  and `git clone --recursive` fetches everything. In this workspace, though,
  it would add a second checkout of each component inside fantasy-engine,
  beside the checkouts already here.
- A lock file. A small file names each repository and commit, and the build
  takes exactly those commits, for example with `git archive`, which leaves
  the working checkouts alone. There are no second checkouts, but the build
  tool must fetch any component that isn't present.

Either way, each release also tags its commit in every component. Proposed:
the lock file. The workspace already keeps the components as sibling
checkouts, and Akashic's image builder already finds MegaPad as its sibling.

**D2. Licences.** No repository has a LICENSE file. MegaPad's README says
"CC0 (for all components not superseded by existing licenses)". LM1's README
says "TBD", while its emulator's `emu/pyproject.toml` says MIT. Akashic
states no licence; its fonts are Apache-2.0 and Bitstream Vera, and its
sample photo is public domain. MegaPad also tracks third-party material:
`cdp1802.pdf`, and Unicode-derived data in `rich_terminal/text_data.py`. The
release needs a licence for each component, notices for third-party
material, and a decision about what may be redistributed at all. Blocks
Part 10.

**D3. Names.** What people call the system, and the name of the command that
runs it. Blocks Part 3's command and the documents in Part 9.

**D4. Version scheme.** Nothing is tagged yet. The BIOS banner says v1.0,
KDOS says v1.1, the native extensions say 0.1.0, and MegaPad's
`ROADMAP-v1.0.md` plans a v1.0 of its own. Proposed: one version for the
whole release, tagged in every component. Blocks Part 10.

**D5. Whether the use-and-function rule also covers the component
repositories.** Their docs mix reference material with plans, handoffs and
evidence. Blocks the scope of Part 9.

**D6. Platforms.** The system runs only on Linux today. Sessions use
AF_UNIX sockets, networking uses a Linux TAP device, tests use POSIX process
groups, and the emulator's JIT exists only for Linux on x86-64. The native
extensions build with `-march=native`, which ties each binary to the kind of
CPU that built it. Blocks Part 10.

**D7. The release filesystem.** Part 2 sets out the choices. Blocks Parts 2
and 6.

**D8. LM1's product scale.** How many tiles and clusters, how much SRAM per
tile and per cluster, and whether the chiplet keeps its own HBM or uses
MegaPad's memory. Blocks Part 7a.

**D9. Which configurations ship.** Part 5 proposes six.

## 4. Where things stand

These facts come from read-only surveys of each repository on 2026-10-27.

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
- New devices attach easily to the emulator. The native simulator
  hard-codes its device windows and models one core. The MMIO map appears to
  have room above +0xC20, and port-bridge ports 4, 5 and 7 are unassigned.
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
  "controlled/trusted-local preview"). The image builder and the boot path
  use MP64FS only.
- The 512 test files all live in `local_testing/`.

### LM1 (`lm1/`, 240 tracked files)

- It holds a spec (`spec/00` to `spec/07`), RTL (28 SystemVerilog files), an
  FPGA target, a Python emulator with a C accelerator, an assembler, a Lisp
  compiler, and its own OS and desktop (Crystal).
- The spec describes a standalone SoC: 256 tiles in 32 clusters, 256 KiB of
  SRAM per tile and 2 MiB per cluster, 32 GiB of HBM3E, PCIe, NVMe, 100 GbE
  and an on-die display engine. It defines no link to MegaPad. It
  contradicts itself on the SRAM total (§3.1) and on the cluster count in its
  floorplan (§12.1).
- The emulator has 402 tests in its own harness: 87 for the core, 87 for the
  toolchain and 228 for the OS and desktop. 41 RTL tests run on Verilator
  against a single core; the tile, cluster and GC-engine RTL is not
  simulated. The FPGA flow stops at synthesis, at about 90K LUTs for one
  8-tile cluster.
- Several stated counts are stale. The README says 258 emulator tests and 42
  RTL tests.

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
  PLAN.md            this plan, deleted at release
  README.md          the front door: what the system is, how to install and run it
  docs/              user documentation only
  configurations/    one folder per sample configuration
  <command>/         the package behind the command (named by D3)
  <lock file>        component commits (per D1)
  tests/             release checks
```

`README.md` and `docs/` arrive with the first configuration that runs
(Part 3), so nothing here describes plans. Nothing in this repository copies
component source.

**1b. Lock the components** (needs D1, the locking mechanism). Record the
commit of each component's main branch, and update it as parts land. Done
when one command assembles every component at its recorded commit from a
fresh checkout.

**1c. Split LM1 into the chiplet** (approach Decided; file list Proposed).

1. Tag LM1's current main as `archive/lm1-os-desktop-<commit>-<date>`.
2. Remove the OS and desktop:
   `emu/lm1/{bios,crystal,desktop,desktop_test_driver,toolkit,vdi,font,icons,vfs}.py`,
   `emu/lm1/fonts/`, `tools/compile_font.py`, `design/{bios,os,desktop}.md`,
   `crystal_desktop_v2.png`, and their tests,
   `emu/tests/test_phase{7,9,10,11,13,15}.py`.
3. Cut the remaining ties to them: the display trap's handler (0x83) and its
   import in `emu/lm1/execute.py`, the `desktop` command in
   `emu/lm1/__main__.py`, the `vdi-*` builtins in `emu/lm1/compiler.py`, the
   two BIOS-boot tests in `test_phase8.py`, and the display tests and unused
   BIOS import in `test_phase14.py`.
4. Keep the other emulator traps for now. The console, block I/O and
   byte-memory traps serve the tests until the MegaPad link replaces them
   (Part 7). The GC and runtime-setup traps (0x90 to 0x96) stand in for
   hardware controls that Part 7a will define. The compiler's "OS entry
   point" also stays: it starts the compiled Lisp runtime, which MegaPad will
   start over the link instead of a BIOS.
5. Remove `BUILD-PLAN.md` and `ideas.md`, which plan the standalone machine
   and its desktop. Their notes on performance and architecture stay readable
   through the tag for Part 7a. Keep `docs/test_gap_ideas.md` as input to
   Part 7f, and keep `design/emulator.md` without its display and BIOS
   sections.
6. Rewrite the README to describe the chiplet, with correct test counts.

Done when the core and toolchain tests pass, the RTL test generators still
import, and nothing in the tree refers to a removed file.

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
3. For each library that is out, Daniel decides whether Akashic finishes it,
   retires it by archive tag, or keeps it outside the release.

Done when every library has a status and every library that is out has a
decision.

**1e. Retire the scrap copies.** `~/Documents/scrap/list-machine` and
`~/Documents/scrap/fantasy-engine`, with their identical backups under
`/media/projectspace/random_backup`, hold nothing the workspace lacks once
two things happen: fantasy-engine's commits are pushed, and Daniel decides
about the never-committed `tools/mem_hierarchy_sim.py`. They are deleted only
on Daniel's go-ahead.

**1f. Component fixes the release depends on** (Proposed). MegaPad's four
temporary import aliases go. `bios.rom` is either built or tracked, not both;
it is tracked although `.gitignore` lists it. One Python version is stated
and used.

### Part 2. Storage for real images

Goal: a configuration's image holds the shipped libraries as ordinary files,
with room to grow.

Today, MP64FS holds 128 entries and 32 MiB, the Desktop image already fills
32 MiB, and modules are packed into chunk files. Akashic can read ext4 and
FAT, but the image builder and the boot path handle MP64FS only. The
workspace's `FUTURE_FILESYSTEM_CONCEPTS.md` names an ext4-derived native
filesystem as the long-term direction; its format is not yet ratified.
MegaPad's storage controller takes 32-bit sector numbers, and
`docs/block-volume-contract.md` adds MBR and GPT volumes. Frames-follow-change
part 4 added a read-only settings volume on a second storage controller; that
work is on its branch and not yet merged.

Proposed: every configuration boots with three volumes.

- **System volume, read-only.** KDOS, the system modules, and Akashic's
  libraries and applets as plain files.
- **Settings volume, read-only.** Changed only from the host, as
  frames-follow-change part 4 built it.
- **User volume, writable.** Documents, Practice records and a learner's own
  modules. The Practice head files, which the runtime writes, move here.

A read-only system volume keeps the installed libraries safe (Part 6), and
resetting a system means replacing one file.

D7 picks the filesystem. The choices are:

- (a) ratify and build the ext4-derived native filesystem;
- (b) grow MP64FS;
- (c) mount the system volume through the existing read-only ext4 binding
  while (a) is built.

Under the workspace's capacity rule, the chosen format's fixed limits are
format rules sized for production, and what a volume holds follows from its
size.

Steps: take D7; design the volume layout and the boot path; build them in
MegaPad (storage, KDOS boot and module loading) and Akashic (VFS binding,
image builder); boot the canonical Desktop from the result.

Done when the canonical Desktop boots from a system volume that holds its
modules as individual files, and its physical journey passes.

### Part 3. Building and running configurations

Goal: one command lists, builds and runs any configuration.

Today, only the test harness builds images. A Desktop session takes
`akashic_tui.py serve` plus MegaPad's `session_viewer.py`, and the canonical
profiles are test setups.

- **3a.** In Akashic, move image building (closure, linking, layout and
  validation) out of the test harness into a supported tool, and make the
  harness use it. This repository calls that tool at the locked commit and
  doesn't copy it.
- **3b.** A configuration format: one TOML file per configuration, matching
  Desk's own TOML settings. It names the Practice, the machine (memory,
  cores, and whether the LM1 chiplet is present), the volumes and their
  sizes, and any extra resources.
- **3c.** The command (named by D3), with `list`, `build NAME`, `run NAME`
  and `new NAME FROM`, which starts a configuration of your own from an
  existing one. `run` builds when needed, starts the simulator and opens the
  viewer.
- **3d.** Host setup: one documented way to install the dependencies and
  build the native extensions. Networking needs either a path that works
  without administrator rights or a clear one-time setup step.

Done when, on a clean Linux machine and following `README.md`, `run` boots
the canonical Desktop configuration from locked commits, and the physical
journey passes through the command.

### Part 4. Practices open configurations

Goal: a configuration's Practice decides what opens and what it can reach.

- **4a. Entry lenses.** A Practice declares the applets that form its entry
  and what each opens with, and Desk realizes them when the Practice
  activates. `docs/runtime/practice.md` already splits the roles this way:
  the Practice owns the declaration, and Desk owns layout, focus and
  activation order.
- **4b. Bindings** for each configuration's resources: documents, sample
  files and library roots.
- **4c. Proper enrollment.** Release images enroll their Practice properly
  instead of the blank development Practice. This needs a design that
  follows `docs/runtime/practice.md` and `DESK_ECOSYSTEM_CONTRACT.md`.
- **4d. One Practice per image** fits today's single-head runtime. The
  multiple-Practice catalog (Gate 13A in `DESK_ECOSYSTEM_CONTRACT.md`) stays
  deferred unless a configuration needs several Practices.

Done when each configuration's applets open from its Practice, and no applet
is queued by autoexec text.

### Part 5. The sample configurations

Proposed set (D9). The names are working names.

| Configuration | What its Practice is for | Applets |
|---|---|---|
| Everyday | writing, planning and files | Pad, Explorer, Daybook, Grid, Agent |
| Sound | making and studying sound | Sound Lab |
| Reading | feeds, AT Protocol and documents | Streams, Library, Pad |
| Observatory | watching data series and models | Observatory, Worlds |
| System | learning the system by building with it | Pad, Explorer, a Forth console, the library sources (Part 6) |
| Lisp | the LM1 chiplet | a Lisp console, Pad (Part 8) |

For each configuration:

1. Write its Practice and its configuration file.
2. Check the real providers and connectors it uses, which the test profiles
   never exercise. The Agent needs a provider key, and Streams fetches live
   feeds.
3. Script a journey through its main tasks, and run it narrowly, with Desk
   and that configuration's applets. The canonical Desktop journey stays the
   regression gate.
4. Document it (Part 9).

Done when every configuration runs from the command and passes its journey.

### Part 6. The System Practice

Needs Parts 1d, 2 and 4.

Contents:

- the shipped libraries' sources, bound read-only from the system volume;
- a writable area on the user volume for the learner's own modules;
- Pad and Explorer;
- a Forth console applet, which doesn't exist yet. It loads modules from the
  user area and shows what they do;
- the library reference, readable from inside the system.

Its authority covers reading the library sources, writing only in the user
area, and loading modules from there.

Done when a learner can open a shipped library's source, write a module that
uses it, load it and watch it run, and nothing inside the system can change
the installed libraries.

### Part 7. The LM1 chiplet

This part starts after Part 1c and runs alongside Parts 2 to 6.

**7a. Product-scale design** (needs D8). Revise the spec for a chiplet:

- Size it for production. Daniel considers the current 256 KiB per tile and
  2 MiB per cluster toy-scale. Interface limits stay fixed at production
  size, and resource limits follow need.
- Replace PCIe, NVMe, 100 GbE and the display engine with the MegaPad link,
  since MegaPad handles I/O and Desk handles the display.
- Decide where its memory lives: the chiplet's own HBM, or MegaPad's memory
  (D8).
- Have MegaPad load and start the Lisp runtime over the link.
- Turn the GC and runtime-setup traps into real hardware controls.
- Answer two questions raised in March. Does LM1 get its own built-in
  self-test, or does MegaPad run one for the whole package? Does LM1 adopt
  MegaPad's hard QoS and one-instruction-per-cycle rule?
- Fix the spec's contradictions in §3.1 and §12.1.

As with MegaPad, the RTL describes the chip we want. Fitting the FPGA is not
a gate.

**7b. The MegaPad link.** One spec covers doorbells and mailboxes, shared
memory windows and DMA, interrupts, loading and starting programs, errors,
reset and test access. Proposed: the spec lives in `lm1/` as the chiplet's
interface, and MegaPad implements the host side.

**7c. A chiplet model for MegaPad's emulator and simulator.** The emulator
accepts Python devices through `bus.register`. The native simulator
hard-codes its device windows, so it first needs a general way to attach
devices, which is MegaPad work. A native model will probably be needed for
usable speed (inferred, not measured).

**7d. RTL.** Bring the chiplet up to the new spec, and simulate its tiles,
clusters and GC engines; only a single core is simulated today. Add
MegaPad's side of the link to its SoC.

**7e. Toolchain.** The assembler and compiler follow any ISA changes. They
build the Lisp runtime image that MegaPad loads.

**7f. Verification.** Link conformance tests are shared by the emulator
model, the simulator model and both RTL sides. Close the RTL test gaps listed
in `docs/test_gap_ideas.md`.

Done when, in both the emulator and the simulator, MegaPad boots the chiplet
over the link and runs Lisp work sent from KDOS, and both RTL sides pass the
same link tests.

### Part 8. LM1 in the system software

Needs Part 4 and Parts 7b and 7c.

- **8a.** MegaPad gets a system module for the chiplet, following
  `networking.f` and `rich-terminal.f`. MegaPad owns it, and system
  composition loads it at boot when the chiplet is present.
- **8b.** Akashic gets a library that hands work to the chiplet through that
  module's public interface. As with `rich-terminal.f`, Akashic doesn't
  REQUIRE a path into MegaPad or copy the module.
- **8c.** The Lisp Practice. A Lisp console applet talks to the chiplet's
  REPL, which `spec/06` places in the chiplet's own runtime along with the
  compiler. Pad holds programs, and examples come with it.

Done when the Lisp configuration's journey passes: evaluate expressions, run
a program written in Pad, and see the results, all through Desk's normal
path.

### Part 9. Documentation

The documents are written fresh for users. Component docs are sources of
facts, but they aren't copied as they stand, since many mix reference
material with plans and status.

The planned set:

- getting started: install, run a configuration, make your own;
- Desk and its applets;
- Practices, and what each sample configuration's Practice does;
- programming the machine: Forth, KDOS and the libraries;
- the LM1 chiplet and Lisp;
- hardware reference: MegaPad, LM1 and the link;
- library reference, covering shipped libraries only (from Part 1d).

Some facts conflict between component documents. Settle each at its source
while writing:

- the Python version;
- the BIOS word count (481, 540 or 550);
- the Desktop's memory (320 or 384 MiB);
- the missing `rtl/README.md`;
- LM1's test counts.

D5 decides whether the component repositories' docs get the same treatment.

Done when every shipped feature is documented by use and function, and no
document talks about plans, phases, evidence or history.

### Part 10. Qualification and release

Needs every other part, plus D2, D4 and D6.

1. Package what people download: prebuilt images, the command, and native
   extensions built for a portable CPU baseline instead of `-march=native`
   (D6).
2. Add licences and notices (D2).
3. Run the final checks: every configuration's journey, the canonical
   Desktop journey, LM1's emulator and RTL tests, and the link conformance
   tests. Each heavy run goes alone, under the workspace rules.
4. Tag every component with the release version (D4), and record the
   commits.
5. Write release notes about function.
6. Delete `PLAN.md`, and tag this repository.

## 6. Order

- Part 1 comes first. Parts 1c and 1d can run at the same time, since they
  touch different repositories.
- After Part 1, Parts 2, 3 and 4 proceed side by side. Part 7 starts after
  Part 1c and runs alongside the rest.
- Part 5 needs Parts 3 and 4. Part 6 needs Parts 1d, 2 and 4. Part 8 needs
  Part 4 and Parts 7b and 7c.
- Part 9 grows with every part and is finished before Part 10.
- Each part starts on Daniel's approval.

## 7. Working rules

The workspace `AGENTS.md` governs this work. In short:

- Commit each coherent slice once it is green, with an informative message.
  Commits are authored as Daniel, and an assistant is credited only by a
  Co-Authored-By trailer. Never amend a commit; add a new one. Daniel
  pushes.
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
- Update this plan when a decision is taken, and delete dropped ideas rather
  than keeping them.

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
