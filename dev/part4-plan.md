# Part 4 plan: building and running configurations

This document stages release Part 4 of [PLAN.md](PLAN.md): one command that
lists, builds and runs any configuration, with the host privacy that
decision 40 adds as item 4e. It was written on 2026-11-24 from read-only
surveys of MegaPad 42e09564, Akashic c43b39cf, LM1 71049c0 and this
repository at 585deac, plus a few small measurements that section 6 lists.
It was approved on 2026-11-24 with every recommendation of section 4, the
networking choice (C7) among them as revised that day, and the stages run in
the order 1, 7, 2, then 3 to 6 and 8.

Part 4 is done, as PLAN.md states, when `run` boots the canonical Desktop
configuration from recorded commits on a clean Linux machine by following
`README.md`, and the physical journey passes through the command.

## 1. Where things stand

### Image building lives in the test harness

Akashic's harness, `local_testing/akashic_tui.py`, has grown to 39,016 lines
and 162 profiles. About 26,000 of those lines are the profiles themselves,
mostly test boot scripts. About 2,450 lines build images: the REQUIRE
closure, the boot-script composition (places, system and user volumes,
networking, the rich terminal), linking and cold-source packing, validation,
the settings disk, the ext4 volumes, token forms and `build_image` itself.
`smoke` takes 5,800 lines, `accept` 1,900, and the profile classes with
Desk's composition another 1,240 at the top. Building also uses two harness
modules,
`forth_dependencies.py` (the closure) and `generate_ext4_profile_fixtures.py`
(the ext4 profile and its toolchain check), and MegaPad's `diskutil`,
`shared/token_form.py`, `shared/boot_identity.py` and simulator.

A build of the canonical Desktop (profile `desktop-apt1`) in the shipping
form, from clean copies of the three repositories, took 8.8 seconds and
peaked at 0.73 GB, including one boot in the simulator that records the
token forms. It wrote a 32 MiB boot volume, a 1 MiB settings disk, a 131 MiB
system volume holding 331 modules, 309 of them as token forms, and a 64 MiB
user volume with 41 sample documents. The two ext4 volumes are sparse files:
4.4 MiB and 456 KiB are allocated.

Three things the command cannot inherit as they are:

- Every build writes a fresh user volume over the old one, and a build
  without `--user-volume` deletes it. That suits tests. A user's volume holds
  their documents and must outlive builds.
- Files come out with the umask's mode: 0664 on this machine, 0644 under the
  common umask 0022. The one exception is the `--codex-auth-checkpoint`
  option, which writes OAuth tokens into the boot volume's `autoexec.f` as
  literal bytes and then sets the boot volume's file to 0600.
- The builder accepts only e2fsprogs 1.47.4, checking the version banner and
  library, while Part 11 has the command use the user's own copy.

### Running a session

`akashic_tui.py serve` starts `megapad.py --mode simulator` with the storage
units, memory, cores and rich-terminal policies, and MegaPad's
`session_viewer.py` connects to its socket. `accept` runs the physical
journey with its own server, viewer and driver.

MegaPad's session server (`shared_session.py`) listens on a Unix socket. It
sets the socket to 0600 after binding and refuses a path owned by another
user. The default paths are fixed names in the shared `/tmp`:
`/tmp/megapad-session-<uid>.sock`, and `/tmp/akashic-tui.sock` for the
harness's `serve`. The viewer's client connects to whatever listens there and
checks neither the socket's owner nor the process at the other end.

That one socket carries the viewer's methods (`claim_display`, `present`,
`display_*`, `screen`, `send_*`) and, with no gate, the debugging methods:
`forth` reads dictionary entries, `peek` reads 1 to 256 cells at any guest
address, `pause`, `resume`, `step` and `reset` control the machine, three
methods run phase profiles, `network` reports diagnostics, `raw` and `text`
return guest output, and `capture` writes the screen as text, JSON or PNG to
a path the client names. The physical journey's driver reads guest state
through `forth` and `peek`, and so do the headless Grid check, MegaPad's
`session_ctl.py` and two of MegaPad's test files.

The simulator server has no option to attach a chiplet module. Tests attach
LM1's module inside their own process.

### Desk's settings

Desk keeps TOML 1.0 settings, read in the guest by `utils/toml.f`:
`desk.toml` for appearance (`[desk.theme]`), and `system.toml` on the
read-only settings disk (`[desk.rich-terminal]` with `safe-mode` and the full
refresh times). Pad has `pad.toml`. Keys are lowercase words joined by
hyphens, in dotted tables, with comments that explain each value. An
installable applet's `project.toml` already names its entry word in an
`[app]` table.

### This repository

`fantasy_engine/` holds only the test tool of Part 1h. There is no lock file
(decision 12, Part 1b), no command, no `pyproject.toml` and no
`configurations/` folder.

### Host dependencies

- **Python.** MegaPad's README asks for 3.12 and its getting-started guide
  for 3.8 or later. The workspace builds and tests with 3.13.7, which is the
  interpreter the test record knows. The command needs at least 3.11 for
  `tomllib`. Ubuntu 24.04 ships 3.12.
- **Native parts.** Built from clean copies on this 16-core machine:
  MegaPad's simulator extension `_megaforth_native` in 37 s (1.1 GB peak, no
  `-march` flag), its emulator accelerator `_mp64_accel` in 51 s (1.9 GB,
  `-march=native`), and LM1's chiplet module in 7 s (`-march=x86-64-v2` and
  fixed flags). pybind11 and setuptools build the first two.
- **Viewer.** pygame (LGPL-2.1) draws the window, and Pillow decodes the
  PNG and JPEG pictures the rich terminal shows. Fonts come through
  fontconfig, with Noto families as fallbacks.
- **e2fsprogs.** Tests pin 1.47.4 under `~/.cache`. Given the same
  arguments, `mke2fs.conf` and fixed time, this machine's own 1.47.0
  (Ubuntu 24.04) built a byte-identical empty user volume, and a volume of
  235 files (9.6 MB) written through `debugfs` that differed from 1.47.4's
  only in the superblock's lifetime-writes counter (offset 0x178) and its
  checksum, in the primary and both backup superblocks. Each image passed
  both versions' `e2fsck` and the driver's admission facts. 1.47.0 introduced
  the `orphan_file` feature the profile uses, so Ubuntu 22.04, which keeps
  e2fsprogs 1.46, cannot build these volumes.
- **Containers.** Neither Docker nor Podman is installed, and Ubuntu 24.04
  restricts unprivileged user namespaces
  (`kernel.apparmor_restrict_unprivileged_userns = 1` here), which rootless
  containers and `slirp4netns` rely on.

### Networking

The simulator has no network device. Its BIOS words `NET-SEND`, `NET-RECV`,
`NET-STATUS` and `NET-MAC@` are primitives that drop every frame, receive
none, report status 0 and give an all-zero address, and the harness refuses
`--nic-tap` for the simulator. The emulator models the network card
(`emulator/accel/mp64_nic.h`) and reaches real servers through the TAP
backend in `nic_backends.py`, which needs a one-time `sudo` setup: the TAP
device, its address, a masquerade rule and IP forwarding. The guest's stack,
`networking.f` (about 19,000 lines), speaks DHCP and otherwise uses 10.64.0.2
with 8.8.8.8 for DNS. On record, MegaPad's `tests/test_live_net.py` and
Akashic's `test_live_multi_conn.py` skip all their tests for want of TAP, and
`test_live_web.py` runs nothing.

Ubuntu 24.04 packages libslirp 4.7.0 (main, depending on GLib), the
user-mode network QEMU uses, under the BSD-3-Clause and MIT licences; it is
not installed here. Its `SlirpConfig` has one setting that limits where the
guest may connect, `disable_host_loopback`, which refuses connections to the
host's 127.0.0.1 and nothing else. Its protocol emulation (`enable_emu`),
which its header calls unsafe, stays off unless asked for.

### Test selection

The release set has 964 units. The latest passes of the 957 with a pass on
record took 12,762 s (3.55 h) one after another, and units run one at a
time, so machine time is wall time. These inputs decide what Part 4's
changes rerun:

| File a change touches | Units that read it | Their recorded time |
|---|---:|---:|
| Akashic `local_testing/akashic_tui.py` | 163 | 5,733 s (1.59 h) |
| Akashic `local_testing/forth_dependencies.py` | 404 | 10,885 s (3.02 h) |
| MegaPad `simulator/core_words.py` | 382 | 4,551 s (1.26 h) |
| MegaPad `_megaforth_native` library | 392 | 4,559 s (1.27 h) |
| MegaPad `_mp64_accel` library | 519 | 18,273 s, final-set units included |
| MegaPad `shared_session.py` | 59 | 355 s |
| MegaPad `session_viewer.py` | 27 | 100 s |
| Akashic `generate_ext4_profile_fixtures.py` | 19 | the four ext4 files and their emulator units |
| MegaPad `nic_backends.py` | 4 | 6 s |

Every closing that changes the harness therefore costs about 1.6 hours, and
one that changes the closure module about 3 hours, because Akashic's other
Forth harnesses read it too. The plan gathers all of Part 4's harness changes
into stage 2's closing.

## 2. Proposed design

### Who does what

- **This repository** holds the command: the lock file and the assembly of
  components at their recorded commits, the native builds, each
  configuration's folder and its privacy, the network helper, and the
  lifecycle of server and viewer. It never interprets Akashic's or Desk's
  settings and never copies component code.
- **Akashic** holds the image tool. It reads a configuration, builds its
  volumes, and writes a session manifest that says what the server needs.
  The harness builds every profile through the same tool.
- **MegaPad** gains server options for debugging access, chiplet modules and
  a network backend, a client that checks whom it talks to, and the
  simulator's network device.
- **LM1** keeps its chiplet module as it is; the command builds it.

### The lock file and assembly (Part 1b)

`components.toml` at this repository's root names each component's
repository and full commit:

```toml
[megapad]
repository = "https://github.com/dgoldman0/megapad"
commit = "42e09564…"   # the full 40-character commit
```

The command assembles a component with `git archive` of its recorded commit,
from the workspace's checkout when the commit is in its object store and
otherwise from a shallow fetch of that one commit, into
`~/.cache/fantasy-engine/components/<name>-<commit>/`. It then builds the
native parts there and marks the folder complete. A dirty or switched
checkout cannot leak in, since only the recorded commit's tree is read. The
command warns when a recorded commit is on no remote-tracking branch, as
Part 1b proposes. A development mode, `--workspace DIR`, builds from the
working trees as they stand, which is what slices and their journeys use.

### The image tool (4a)

The tool lives in Akashic's `toolchain/image/`, beside the language checker,
and runs as `python3 -m toolchain.image`. It moves out of the harness:

- the closure (`forth_dependencies.py`) and the boot-script composition;
- Desk's composition from a list of applets, the blank Practice's
  provisioning, the records seeds and the sandbox policy, kept as a bridge
  until Part 5 replaces them;
- linking, cold-source packing and validation;
- the MP64FS boot volume and the settings disk (through MegaPad's
  `diskutil`), and the ext4 system and user volumes with the ext4 profile's
  manifest, `mke2fs.conf`, argument rendering and superblock checks;
- token-form recording in the simulator;
- the build itself and the build description it takes, which replaces the
  building half of the harness's `Profile`.

The harness keeps the profiles, `smoke`, `accept`, the failure markers and
the diagnostic boot options (the frame shadow check and every-frame checks).
It converts each profile into a build description and calls the tool. Both
forms remain: the shipping form (token forms on the ext4 system volume, with
the user volume) for configurations, and the linked form for the harness's
`--linked` journey.

Four behaviours change for the command's sake and are built into the move,
so that the harness changes once:

- the tool writes every file 0600 and every folder 0700;
- it keeps an existing user volume unless asked for a fresh one, which the
  harness asks for;
- its toolchain check takes either the tests' pin, 1.47.4, or the command's
  minimum, 1.47.0 with `orphan_file`;
- it writes a session manifest (JSON) beside the volumes: storage units,
  memory, cores, the rich-terminal policies, and the commits and
  configuration it was built from.

Three harness changes that later stages need ride in the same closing. The
harness passes `--debug-access` wherever it reads guest state; `accept` learns
to drive a session another program serves, which stage 8's journey through
the command uses; and the harness's `--nic-tap` becomes `--nic SPEC`, passed
to MegaPad's servers unread, so stage 7's network backends need no harness
change. MegaPad's servers gain the matching `--debug-access` and `--nic`
options, the simulator refusing every network backend until stage 7.

The configuration reader (stage 3) is a module the harness never imports, so
later changes to it rerun only its own tests.

### The configuration format (4b)

One TOML file per configuration, in the style of Desk's settings. The
canonical Desktop would read:

```toml
[configuration]
format = 1
title = "Desktop"
description = "Desk with Pad, File Explorer, Daybook, Grid and the Agent, and Streams on the launcher."

[practice]
title = "Desktop"
# Built-in applets Desk offers on its launcher without opening them.
offer = ["streams"]

# The applets Desk opens in tiles, in order.
[[practice.entry]]
applet = "pad"

[[practice.entry]]
applet = "file-explorer"

[[practice.entry]]
applet = "daybook"

[[practice.entry]]
applet = "grid"

[[practice.entry]]
applet = "agent"

[agent]
provider = "scripted"

[machine]
memory-mib = 384
cores = 1

[volumes.user]
size-mib = 64
documents = "akashic:assets/samples/desktop"

[volumes.system]
keep-source = false

[viewer]
cols = 160
rows = 48
font-size = 16

[network]
enabled = false

# Desk's system settings, written to the settings volume as system.toml.
[desk.rich-terminal]
safe-mode = false
full-refresh-quiet-ms = 1000
full-refresh-interval-ms = 5000
```

The rules:

- `[[practice.entry]]` lists what the Practice opens. Until Part 5a the tool
  composes it into Desk's boot script as the harness does today; 5a makes the
  same list the Practice's entry-lens declaration and adds what each applet
  opens with, so files written now keep working.
- `[agent]` names the Agent's provider. `scripted` is the development
  provider the canonical journey relies on; real providers come with Part 6.
- `[machine]` gives MegaPad's external memory and its full cores, one to
  four on the simulator. LM1 belongs to every configuration (decision 24),
  so the format has no switch for it; `[machine.lm1]` arrives when
  PLAN.md's open decision D8, LM1's product scale, sets LM1's memory.
- `documents` names a folder that is copied into the user volume's documents
  place when that volume is created, and never again. A plain path is
  relative to the configuration file; `akashic:` and the other component
  names resolve inside that component at its recorded commit. The canonical
  file's folder in Akashic follows C4's recommendation.
- `[viewer]` sets the terminal's size and the font size for `run`; the
  journey sets its own. `[network]` turns on the network of stage 7 and will
  list the forwarded ports.
- `keep-source` writes module source beside the token forms, as the
  Workshop needs (Part 7).
- Tables named after Desk's settings files, such as `[desk.rich-terminal]`,
  set those values in the file the settings volume carries, whose comments
  stay as Desk's repository writes them.
- The reader refuses an unknown table or key and names it, since a misspelt
  key would otherwise be ignored without a word.

### The command (4c)

```
fantasy-engine list
fantasy-engine build NAME
fantasy-engine run NAME [--no-viewer] [--debug-access]
fantasy-engine new NAME FROM
```

`list` shows the shipped configurations, from `configurations/` at the
recorded commit of this repository, and the user's own, with whether each is
built. `build` assembles the components, builds the native parts when they
are missing, calls the image tool, and creates the user volume when there is
none. `run` builds when the build's inputs have changed (the recorded
commits, the configuration file and its documents), starts the simulator
server, opens the viewer, and stops the server when the viewer closes.
`--no-viewer` only serves, for the journey's driver. `new` copies a
configuration's file and documents under a new name for the user to edit;
the new configuration gets a fresh user volume.

Each configuration has one folder (0700),
`~/.local/share/fantasy-engine/configurations/<name>/`, holding the
configuration file when it is the user's own, the boot, settings and system
volumes, the user volume, and `build.json` with the session manifest. Builds
replace the first three and never touch the user volume. `--data-dir` and
`--cache-dir` move both trees, so tests and journeys keep them in
`/dev/shm`.

### Privacy on the host (4e)

- The command sets its umask to 077, the tool writes 0600 files and 0700
  folders whatever the umask, and `run` refuses an image file another
  account owns or can read.
- The socket lives in a private folder: `$XDG_RUNTIME_DIR/fantasy-engine/`,
  or the 0700 folder that MegaPad's `runtime_paths.py` already creates and
  checks.
- The machine reaches the internet and nothing local by default. The
  network device refuses the guest's packets to the user's own computer and
  to local addresses: loopback, the private, shared and link-local ranges,
  and their IPv6 counterparts. That covers more than libslirp's
  `disable_host_loopback`, which the device also sets. A configuration
  setting, `local_access` (proposed name), opens them for a power user who
  tests Desk against local services. With it on, `run` prints a warning
  that any program on the machine, including an installed applet or code
  that a feed or page leads it to run, can then reach services on the
  user's computer and local network that expect only local callers. Desk
  shows the same warning at every start, from its system settings.
- MegaPad's client refuses a socket another account owns and checks the
  server's user through `SO_PEERCRED` before sending anything, so a socket
  planted by another account cannot collect keystrokes.
- The server refuses the debugging methods listed in section 1 unless it was
  started with `--debug-access`. Without it the server also turns off core
  dumps and other processes' access to its memory (`prctl` with
  `PR_SET_DUMPABLE` 0), which keeps the Agent's key and unsealed tokens out
  of crash reports and same-account inspection.
- Screen profiles, phase profiles and `capture` need debugging access, and
  the command writes no log of guest output.
- The supported tool has no `--codex-auth-checkpoint`.
- The getting-started guide tells users to keep the configuration folder as
  safe as any file of passwords, since the machine has no accounts.

### Host setup (4d)

The documented way, from source until Part 11 ships prebuilt parts:

1. Install `uv`, which needs no administrator rights and provides Python
   3.13 where the system lacks it.
2. Have git, a C++17 compiler with make, e2fsprogs 1.47.0 or later,
   fontconfig fonts, and libslirp's development files, which bring GLib's.
   Desktop systems usually carry e2fsprogs, fontconfig and GLib already.
   Installing the rest takes administrator rights once (on Ubuntu, `sudo apt
   install git build-essential libslirp-dev`), and Part 11's prebuilt parts
   remove the need for the compiler and the development files.
3. Install the command from this repository with `uv`, which also brings
   pygame and Pillow.
4. `fantasy-engine doctor` (proposed name) checks each requirement and says
   what to do about any that is missing.

The command builds every native part for x86-64-v2, as LM1's module already
is, so what a user builds matches what Part 11 will ship. The workspace's
development builds keep their own flags, so nothing on record reruns.

### Networking without administrator rights (4d)

The simulator first needs a network device. Its four network words take a
host frame backend from the server: `--nic slirp` or `--nic tap:IF`. The
hook sits in `simulator/core_words.py`, a one-time change that reruns 382
units (1.26 h); the device itself goes in a module that is imported only
when a backend is configured, so later changes rerun only the network tests.
The TAP backend lives in `nic_backends.py`, which the emulator already uses,
and the slirp backend joins it in MegaPad's native extension.

libslirp is the user-mode path (decided 2026-11-24). Linked into MegaPad's
native extension, it needs nothing else installed or started and leaves no
socket file to protect. It runs without privileges and turns the guest's
Ethernet frames into ordinary connections from the user's own account, with
DHCP, DNS forwarding and chosen inbound ports. It also runs on macOS and
Windows, should a later release reach them. The command gives the guest the
addresses `networking.f` expects and binds forwards, such as Publishing's web
server, to 127.0.0.1. Its packet handling runs inside the simulator's
process, which holds the guest's secrets, so the device turns on only what
the guest uses (DHCP, DNS and NAT), leaves libslirp's TFTP server and
protocol emulation off, and refuses local destinations unless the
configuration allows them (section 2, privacy on the host).

TAP stays documented as the alternative for anyone who wants the machine on
their local network, at the cost of a `sudo` setup after each boot. The live
tests gain the slirp backend, so they run on any machine with libslirp; they
reach real servers, so they run on request.

## 3. Stages

Agent hours are ranges. Recent rounds have finished below their estimates,
the ext4 tests' move onto the simulator most of all (2.7 agent hours on
2026-11-16), so the low ends are the likelier. Machine time counts closing
runs, journeys and checks.

| Stage | Work | Agent hours | Machine time | Waits on | Blocks |
|---|---|---:|---:|---|---|
| 1 | Lock file, assembly, command skeleton | 4–7 | 10 min | nothing | 4, 8 |
| 2 | Image tool in Akashic, with MegaPad's debug gate | 12–22 | 3.5 h | no other round editing the harness | 3, 4, 5 |
| 3 | Configuration format, canonical Desktop file | 6–12 | 15 min | 2 | 4, Parts 5 and 6 |
| 4 | The command | 8–14 | 20 min | 1, 3 | 5, 6, 8 |
| 5 | Privacy on the host | 6–10 | 20 min | 2, 4 | 8 |
| 6 | Host setup | 4–8 | 20 min | 1, 4 | 8 |
| 7 | Networking without administrator rights | 15–29 | 1.5 h | 1; 4 for the command's part | Part 6 step 2 |
| 8 | README, journey through the command, clean machine, full run | 6–10 | 4 h | all | Part 4's end |
| | **Total** | **61–112** | **about 10.5 h** | | |

The final set at Part 4's end, the four ext4 files on the emulator and
MegaPad's system test, adds about 2 hours and peaks near 8 GiB, so it runs
only on approval. Stage 7 touches only MegaPad's simulator and backends, so a
second agent can take it beside stages 2 to 6.

### Stage 1. Lock file, assembly and command skeleton

`components.toml`, the assembly described above, the native builds in the
assembled trees, the warning about unpushed commits, and the package skeleton:
`pyproject.toml` with the `fantasy-engine` entry point.

Done when one command assembles every component at its recorded commit from a
fresh checkout (Part 1b's done-when), a dirty or switched checkout changes
nothing assembled, and the native parts build in the assembled trees. Gate:
this repository's units. Its test that runs `git` reruns every time, which
costs seconds.

### Stage 2. The image tool

The move of section 2 and the three harness changes that ride with it, with
MegaPad's `--debug-access` and `--nic` options and MegaPad's tests passing
the first, in one combined closing.

Done when the harness holds no image-building code, every one of the 162
profiles builds byte-identical images before and after the move (same
`PYTHONHASHSEED`, same day, since one sample carries the date), the four
behaviours above work, and MegaPad's server refuses debugging methods
without the option. Gate: the closing run, about 3.1 h, since 406 release
units read the harness, the closure module or the ext4 profile code, the
four ext4 files among them, and MegaPad's session units join them; the
25-case ext4 sample on the emulator (about 4 min); the byte-identity builds
(about 20 min); and the canonical Desktop journey in the shipping and linked
forms (about 5 min), since the move reaches the linked chunks and the
cold-source loader. If C4 moves the sample documents into Akashic's files,
that change joins this closing as well.

Moving the closure module costs about 1.3 of those hours. It could instead
move just before Part 4's full run, which reruns everything anyway, but the
tool would then import it from the harness's folder for several stages. The
plan moves it with the rest.

### Stage 3. The configuration format

The reader in `toolchain/image`, the format's document in Akashic's docs,
and `configurations/desktop/configuration.toml` in this repository.

Done when the tool builds a configuration file into volumes and a session
manifest, and the canonical Desktop file builds the same boot, settings and
system volumes as the harness's `desktop-apt1`, and the same fresh user
volume. Gate: the reader's tests and that comparison.

### Stage 4. The command

`list`, `build`, `run` and `new`, the configuration folders, the rebuild
rule, the server and viewer lifecycle, `--no-viewer`, and development mode.
Under C9, MegaPad's simulator server also gains `--chiplet MODULE`, a change
to `simulator/server.py`, which 11 units read (about 4 min).

Done when each subcommand works in both modes, `run` keeps the user volume
across rebuilds, and Desk with Pad runs a journey through the command in
development mode. Gate: this repository's units and that journey (about
3 min).

### Stage 5. Privacy on the host

The measures of section 2 not already built in stage 2: the private socket
folder, the client's checks, the server's core-dump and memory-access
setting, debugging access for profiles and captures, refusing exposed image
files, and the guide's text.

Done when tests show 0600 files and 0700 folders under umask 0000 and 0022,
a socket owned by someone else refused, the debugging methods refused without
the option and served with it, and no file written outside the
configuration's folder during a run. Gate: MegaPad's session and viewer
units (about 8 min) and the canonical Desktop journey once, since the server
changes.

### Stage 6. Host setup

`doctor`, the x86-64-v2 builds, the Python version stated in every
repository's README (Part 1f's Python item), and the install section of the
README.

Done when `doctor` reports each requirement correctly on this machine and in
a bare environment, and the canonical journey built at x86-64-v2 takes no
longer than with the current flags beyond run-to-run noise. Gate: this
repository's units and two journeys for the speed comparison (about 5 min).

### Stage 7. Networking without administrator rights

The simulator's network device, the slirp backend behind the `--nic` option
of stage 2, the refusal of local destinations with the `local_access`
setting and its two warnings, and the live tests on either backend. The
harness already passes `--nic` through, so nothing here reruns its 163 units.

Done when the simulator passes frames both ways under the same contract the
BIOS words have on the emulator; a Desk session on the simulator fetches a
public HTTPS page through libslirp without administrator rights; and tests
show the guest's connections to the user's computer and local addresses
refused by default, and allowed with both warnings shown when the setting is
on. Gate: the closing run (382 units for the hook, about 1.5 h) and the
network tests; the live tests and the live Desk check run on request, since
they reach real servers. They should follow the TLS round's change to a
standard set of web roots, which they exercise. The first prototype confirms
libslirp's DHCP and DNS hand the guest settings `networking.f` accepts, and
that its timers keep pace with the simulator's real-time clock.

### Stage 8. Documentation, the journey through the command, a clean machine

`README.md` gains how to install and run in place of its ending, and
`docs/getting-started.md` arrives with install, run, making your own
configuration, and keeping its files safe. The physical driver,
`physical_desktop_acceptance.py`, gains a mode that builds and serves through
the command and binds its evidence to the lock file's commits instead of
`git` checkouts; three units read the driver, and `accept` already drives an
outside session since stage 2. Then the clean-machine check of choice C11,
and Part 4's full run under decision 36.

Done when Part 4's done-when holds and the full run finds nothing the
selection failed to predict. Gate: the journey through the command in both
modes (about 6 min), the clean-machine run (about 15 min, with downloads),
and the full release set (about 3.6 h).

## 4. Decisions to take

The choices are numbered C1 to C16 within this document, so that they stay
apart from PLAN.md's open decision D8.

**C1. Fold Part 1b into Part 4.** Part 4's done-when names recorded commits,
and no lock file exists. Options: build it as Part 4's first stage; build it
separately first; or let Part 4 build only from the workspace, which leaves
the done-when unmet. Recommended: the first stage, as section 3 has it. Cost:
4 to 7 agent hours, which the done-when needs anyway.

**C2. Where the image tool lives and who reads configurations.** The tool
must sit in Akashic, and something must turn a configuration into images.
Options: (a) Akashic's `toolchain/image` reads the whole configuration and
writes volumes and a session manifest, and the command only orchestrates;
(b) this repository parses configurations and drives a lower-level Akashic
tool, which copies Akashic's knowledge of applets and Desk's settings into
this repository; (c) a new top-level `tools/` folder in Akashic.
Recommended: (a), which keeps each piece of knowledge in one repository.
Cost: the same in each.

**C3. What opens, before Part 5a.** Desk learns what to open from its boot
script today. Options: (a) the `[[practice.entry]]` list, composed into the
boot script by the tool until 5a makes it the Practice's declaration; (b)
wait for 5a. Recommended: (a). Cost: about 2 hours now and 1 hour to remove
the bridge in 5a; (b) stalls Part 4 for the length of 5a.

**C4. The canonical Desktop's test material.** The journey needs the
Agent's scripted provider and 41 sample files (65 KB) that the harness
generates in Python, and the README needs a Desktop a user can run.
Options: (a) ship `configurations/desktop/` now, naming the scripted provider
and sample documents that Akashic keeps as files, with its generators kept as
the script that writes them, as it does for its Unicode tables; the
configuration moves to `dev/` once Part 6's configurations arrive; (b) the
same, with the documents copied into this repository, where they drift from
the harness; (c) a configuration without samples and without the scripted
provider, and a journey that derives its own with `new` and adds them.
Recommended: (a). Cost: 3 to 5 hours inside stage 2's closing; (c) costs as
much in the driver, and the README's Desktop then opens empty.

**C5. The Python version (Part 1f).** Options: (a) 3.13, what the workspace
runs and the record knows, installed through `uv` where the system ships
older; (b) 3.12, Ubuntu 24.04's own, which reruns every unit once (about
5.5 hours of machine time) and needs a new development interpreter; (c)
several versions, which multiplies the testing. Recommended: (a). Cost: none.

**C6. e2fsprogs at release.** Options: (a) the user's `mke2fs`, `debugfs` and
`e2fsck` from 1.47.0 on, checked by version and feature, with tests keeping
the 1.47.4 pin; (b) require 1.47.4, which users would build themselves; (c) a
host-side ext4 writer that needs no e2fsprogs, which is a large new piece.
Recommended: (a). 1.47.0 builds the same system volume as the pin, byte for
byte. Its user volume differs only in marking the block groups that hold
superblock backups (1, 3 and 5 on a 64 MiB volume) BLOCK_UNINIT, which
Akashic's ext4 driver refused at its first write until stage 2 taught it the
bitmap such a group stands for (measured and fixed 2026-11-24). Cost: about
2 hours inside stage 2, and about 2 more for the driver. The alpha's hosts
then start at Ubuntu 24.04, Debian 12 and current Fedora.

**C7. Networking without administrator rights.** Decided 2026-11-24:
libslirp, linked into MegaPad's native extension, with TAP documented as the
alternative. It brings GLib (LGPL) into the build and the run. The machine
reaches only the internet by default, and the `local_access` setting opens
the user's computer and local network for a power user, with a warning from
the command and from Desk at every start. Cost: 15 to 29 agent hours for
stage 7, of which the network device is 6 to 10.

**C8. Debugging access in MegaPad's own server.** Options: (a) off unless
`--debug-access`, everywhere, with each launcher whose client reads guest
state passing the option: the harness's server command, the headless Grid
check and MegaPad's session tests; (b) on by default, off only when the
command starts the server. Recommended: (a), one rule for every launcher.
Cost: 2 to 3 hours, inside stage 2's closing, so no extra rerun.

**C9. LM1 in `run`.** Options: (a) attach LM1's chiplet module in every
configuration from Part 4, through a new server option, idle until Part 9a's
boot software uses it; (b) attach it only once 9a loads `chiplet.f` at boot.
Recommended: (a), which matches decision 24 and leaves 9a only its software.
Cost: 3 to 5 hours and one journey to check that the canonical Desktop's
steps and frames stay as they were.

**C10. The journey through the command.** Options: (a) the physical driver
gains a mode that builds and serves through `fantasy-engine run --no-viewer
--debug-access`, drives with its own viewer, and binds evidence to the lock
file's commits; (b) a `journey` subcommand, which puts test code into the
release's command. Recommended: (a). Cost: 4 to 6 hours. Since that mode runs
no `git`, it may also let journeys become test units later.

**C11. The clean-machine check.** Options: (a) on this machine, with a fresh
home folder in `/dev/shm`, Python from `uv`, shallow clones of the pushed
recorded commits from GitHub and packages from PyPI, while the compiler,
e2fsprogs and fonts stay this machine's; (b) a virtual machine or a WSL2
install on another computer; (c) a container, which this machine lacks.
Recommended: (a), with (b) as well if a spare machine is at hand. Cost: about
1 agent hour, 15 minutes of machine time and 150 MB of downloads, after the
recorded commits are pushed.

**C12. The Codex auth checkpoint.** The harness option writes OAuth tokens
into the boot volume, which decision 40 rules out for the product. Options:
(a) leave it out of the tool now and remove it from the harness when the
passphrase-sealed sign-ins land; (b) remove it now. Recommended: (a), which
stays clear of the round building those sign-ins. Cost: about 1 hour.

**C13. Where a configuration's files live.** Options: (a) one folder per
configuration under `~/.local/share/fantasy-engine/` holding everything; (b)
rebuildable volumes under `~/.cache` and the user volume under
`~/.local/share`. Recommended: (a), one folder to keep safe and back up.
Cost: none.

**C14. Splitting the harness's profiles now.** About 26,000 lines of profiles
stay in `akashic_tui.py`, so a change to any profile still reruns 163 units.
Options: split them by family in stage 2; or keep stage 2 a pure move and
decide after Part 1h's measurement of how much the harness reruns.
Recommended: keep the move pure. Cost of splitting now: 10 to 20 more hours.

**C15. Native build flags.** Options: (a) the command builds all three
native parts for x86-64-v2, as Part 11 will ship them; (b) keep
`-march=native` for `_mp64_accel` in the command's builds. Recommended: (a),
once the speed check of stage 6 shows no loss. Cost: about 2 hours.

**C16. The emulator in the command.** The Desktop fails on the emulator
today, a known failure from before this round. Options: (a) the simulator
only in Part 4, with `--backend emulator` once that failure is fixed; (b)
offer the emulator now for small configurations. Recommended: (a). Cost:
none.

## 5. Risks

- **Conflicts in the harness.** About one Akashic commit in seven touches
  `akashic_tui.py`, the vault round's tests among them. Stage 2 should start
  when no other round has open edits there and finish quickly.
- **Images that change unnoticed.** The byte-identity check covers it only
  at a fixed hash seed on one day, because one sample carries the date and
  guest steps vary with the seed.
- **Rerun cost.** Each closing that touches the harness or the tool's shared
  modules costs about 1.6 hours, and about 3 with the closure module. A
  change slipped into a later stage pays it again.
- **Networking that has never run on the simulator.** `networking.f` has run
  only on the emulator, and its timers and polling may behave differently on
  the simulator's real-time clock.
- **libslirp inside the simulator.** Its packet handling runs in the
  process that holds guest memory, so a flaw in it could reach the machine's
  secrets. The device limits what it turns on and filters local
  destinations itself, and MegaPad's builds track libslirp's security
  releases.
- **Secrets in host swap.** Guest memory lives in the server process, which
  the host may page to disk; this machine has 30.5 GB of swap on its drive.
  The command cannot lock 384 MiB of guest memory, so the guide recommends
  encrypted swap.
- **Callers of the debugging methods missed by the search.** Each would fail
  with a plain refusal rather than silently.
- **A display is required.** The viewer needs a desktop session, and WSL2
  needs WSLg; a host without one can only serve.
- **Fixed terminal size.** Resizing is an open qualification, so a run keeps
  the configuration's size, and a size that does not fit the screen needs a
  new run.
- **User volumes outlive releases.** A later change to the Practice head or
  record formats will need a migration, which Part 4 does not build.
- **Save cost grows with the user volume.** A Pad save took 5 s on a 64 MiB
  volume and writes reached 10 s at 1 GiB (2026-11-15), so a configuration
  that asks for a large volume pays for it until the writer gets faster.
- **Neighbouring work.** The TLS and vault round edits networking's trust
  store and the credential code, and Part 3's remaining simulator work edits
  simulator files; merge order matters for stages 2 and 7.

## 6. Checks behind this plan

- Read Part 4 and the parts and decisions it depends on in PLAN.md, the
  harness's image building, serving and parser, MegaPad's session server,
  client, viewer, launcher, simulator network words, runtime paths and NIC
  backends, Desk's settings files, LM1's chiplet build, and this repository's
  test tool.
- Queried the test record read-only,
  `~/.cache/fantasy-engine/testing/records.sqlite3`, for the units whose
  latest pass read each file in the table of section 1, and for the release
  set's totals.
- Built a 16 MiB user volume and a 32 MiB volume of 235 files with the pinned
  e2fsprogs 1.47.4 and this machine's 1.47.0, compared them byte by byte,
  and checked each with both versions' `e2fsck` and the ext4 profile's
  superblock checks.
- Built the three native parts and the canonical Desktop's shipping form from
  `git archive` copies in `/dev/shm`, timed with `/usr/bin/time`, and read
  the modes and allocated sizes of the files written.
- Checked this machine's packages and settings: Ubuntu 24.04.5, libslirp
  available but not installed, no container tools or `uv`, the
  user-namespace restriction, Yama's ptrace scope 1, and umask 0002.
- Read libslirp 4.7.0's `libslirp.h` for its configuration and its Debian
  copyright file for its licences, and Launchpad for e2fsprogs 1.47.0's
  update to Ubuntu 22.04, which was proposed and never released.
- No test unit and no journey ran for this plan.
