# Applications of the ext4 driver

Ways the ext4 driver's mechanisms could serve work beyond storing files.
[docs/ext4.md](../../docs/ext4.md) describes what the driver does today. Each
application here needs new interfaces, protocols or code, which its section
names. Nothing here is decided.

These uses build on three of the driver's mechanisms. Its ownership check
accounts for every block a transaction claims or releases: a claim needs an
unclaimed block, a release needs a claimed one, and a check that passes leaves
its claim map clear for the next. Before it stages a namespace operation, such
as a create, rename or unlink, the driver seals a record of every block the
transaction will write, each with its role, and it proves every transaction
complete before any of it reaches the disk. Its orphan file carries an
operation that spans several transactions across a crash, so that recovery
finishes what the operation began.

## Watching a save in the Workshop

In the Workshop, the Practice for learning the machine by building with it
(Part 7 of [the plan](../PLAN.md)), a tool could pause a storage operation
after the driver has staged and proved it, before anything reaches the disk,
and show what the operation is about to do. A developer following a file's
growth would see the blocks the allocator chose, the extent-tree nodes the
insertion edits, the bitmap, descriptor and superblock updates, and the
journal blocks that will describe the transaction. From a recorded run, the
developer could then pick one write or flush, repeat the operation with the
disk failing at that point, and watch the next mount recover. A learner could
change an allocation choice on a scratch volume and see either the accepted
transaction or the exact check that refused it. Either way, the explanation
would come from the driver that writes real volumes, working on standard ext4.

The pause point exists already. The driver stages and proves each transaction
in full before it emits any of it, and on a clean mount it stages a dry pass
before it activates the journal. Namespace operations hold their plan in the
sealed record, while writes and truncation stage their blocks in the journal
writer's tables. On the host side, MegaPad's model of its storage controller
can fail a given command at a given sector or byte, and the ext4 tests use it,
with a trace of every write and flush, to cut operations at the points they
pick.

The tool needs:

- a read-only view of a staged transaction, covering the sealed record and the
  writer's tables, kept after the operation returns, since the driver clears
  both on return;
- a bounded trace of the checks the driver runs, naming the one that refused;
- a way to request a storage fault from inside the machine, since today's
  fault injection is a host-side call that the tests make;
- the Workshop's Forth console, which Part 7 adds.

## A workbench for storage algorithms

The same view could grow into a workbench for comparing allocation and
compaction strategies. Several Forth words would each propose a way to extend
the same file, and the workbench would stage every proposal against the same
starting image, run the driver's checks on it, and compare fragmentation,
memory use and journal space, along with the guest steps each strategy took to
propose and the driver took to check.

The driver's checks test a transaction's result, whatever chose its blocks, so
they would apply unchanged to another strategy's choices. Allocation
accounting proves every new block free in the bitmaps and outside the fixed
metadata, the map check proves that the staged maps differ from the old ones
by exactly the blocks allocated and freed, and the home-set proof accounts for
every block the transaction writes. Today's allocator follows the kernel's
rule: it aims to continue the extent before the new blocks, searching from
that goal through its group and then the following groups in turn. A
transformation that moves data needs one further check: a defragmenter, for
one, must also prove that each file it moves reads back byte for byte as
before.

Strategies from outside the trusted code, an assistant's among them, would run
as generators that return a proposal for the driver to check. The sandbox is
the project's boundary for untrusted code: it runs verified plans within set
limits, and a plan reaches only what it is handed. The driver keeps its
working state in global Forth variables inside its trusted implementation, so
a strategy would run apart from it, in the sandbox, and hand back data alone.

The workbench needs:

- a proposal format naming the runs a strategy chooses, by file and logical
  range;
- an entry point that stages a transaction from a proposal and runs the
  existing checks on it;
- a byte-equivalence check for transformations that move data;
- a runner that restores the starting image between candidates and records the
  comparison;
- a sandbox profile whose output is a proposal, for strategies from outside
  the trusted code.

## Storage experiments others can replay

Developers of other ext4 implementations could use Fantasy Engine to build
precise storage experiments and exchange them. A Forth program could make a
fragmented file, truncate it over several transactions and cut the power at a
chosen write. The saved experiment would name the starting image, the
component commits, the volume's geometry, the writer's profile and the cut
point, and it would hold the image the cut left and what each recovery made of
it. Another developer could then examine the same cut image, or replay the
operations on a different implementation. The comparison would cover the
recovered contents and the consistency of names and allocation within the
shared profile, while each implementation keeps its own valid choice of
blocks.

Akashic's ext4 test suite already does most of this within its own runs. It
builds its volumes with pinned e2fsprogs 1.47.4 from fixed parameters and
records their hashes, runs each operation on a simulated MegaPad with the
driver loaded from source, cuts writes through the storage controller's fault
injection, checks every result with e2fsck, and reads files back with debugfs.
For journal replay, it recovers the same crash image with both e2fsck and the
driver and checks that both restore the same blocks.

Two pieces would turn those runs into experiments others can use: an export
format for an experiment and its results, and a runner outside the test suite
that rebuilds the starting image, replays the operations, applies the fault
and records the outcome. With them, developers could study disagreements
between recoveries and contribute regression cases to projects beyond Fantasy
Engine.

## Checking buffer hand-offs between cores and chips

The same claim-and-release accounting could check shared buffers. Each buffer
would move through defined states, such as held by one core or chip, lent to a
job and returned, and a checker would verify each proposed change against the
state before it, as the map check verifies each transaction's blocks. Its
trace would locate a duplicate claim, an unmatched release, or a hand-off that
the two sides record differently.

Part of this exists on MegaPad today. Akashic's worker jobs hand caller-owned
input, output and scratch spans to another core and give them back when the
owner reaps the job. The plan has LM1 take sandbox jobs the way worker cores
do (Part 9c), and the two chips share memory (decision 29), so a hand-off
between them moves ownership of data that stays where it is.

The checker needs the hand-off states defined, and between the chips they
belong in the link specification that Part 8c writes. It also needs each
side's transitions observed, in the chiplet module and in MegaPad's system
module for the chiplet, and a Forth vocabulary for resource transitions, with
an adapter for each kind of resource, such as job spans or the storage
controller's transfer buffers. The ext4 check holds because the driver is the
volume's only writer. Two chips acting at once remove that condition, so every
ownership change would pass through a protocol the checker sees. Its first use
would be diagnostic: record a failing hand-off, replay it, and find the first
transition that breaks the rules. Enforcing the rules in ordinary operation
would need the checker on every path that reaches the buffers.

## Jobs that resume after a restart

Durable jobs could follow the pattern of the driver's truncation across
transactions. A shrink too large for one transaction first commits the new
size and an orphan record, then frees blocks in passes, and mount recovery
finishes the passes from the durable inode and the record. A bulk import, a
reorganization of a collection or a document conversion could keep progress
records of its own in ordinary files, each naming the job's code version, its
inputs, the work done and the next step, as explicit state with rules for
resolving references when the job resumes. After a restart, Akashic's job
service would rebuild the next step from the latest record. The orphan file
would stay the filesystem's own, and applications would keep their records
through the ordinary file interface.

The driver already gives such records one guarantee. An append that a single
`VFS-WRITE?` call commits whole lands entirely or leaves the old size, because
the file's new size commits with its data, so a progress log of one record per
append keeps every record whole across a crash. An overwrite in place can tear
at a sector boundary, and the usual atomic replacement, renaming a new file
over the old one, becomes available with the writer's rename over an existing
file, which Part 2 adds.

A job library needs a commit protocol that ties each step's result to its
progress record, rules for retrying a step, handling for changes to the job's
code or inputs, and a way for the job service to find and resume the job after
a restart.

## A first experiment

The Workshop view is the closest extension of the driver, and its first
prototype could run on the host before the Workshop exists. It would expose
one sealed namespace record and the writer's tables from one operation on a
scratch image, and record the checks, writes and flushes. A developer would
then pick a cut point from the record and compare the recovery with the
intended result. The ext4 tests already trace writes and flushes, so the
prototype adds mainly the record view and the check trace. It would show
whether the existing records hold enough detail for a useful explanation, and
what a later workbench would need to keep.

## Notes

The references below are to Akashic at commit
[`6ebed51d`](https://github.com/dgoldman0/akashic/commit/6ebed51dc892319448a50786d7115f891c8dacfd)
and MegaPad at commit
[`c3e8ef5f`](https://github.com/dgoldman0/megapad/commit/c3e8ef5f5e2c89c8f99f9919476fdbd31b89ef7e).

- The sealed record of a namespace operation, and its clearing on return:
  [the driver document](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md?plain=1#L206).
- The ownership proof and each transaction's map check:
  [Block ownership](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#block-ownership),
  and the proof in
  [`vfs-ext4.f`](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/akashic/utils/fs/drivers/vfs-ext4.f#L11663).
- The allocator and the home-set proof:
  [Run allocation](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#run-allocation)
  and
  [Home-set proof](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#home-set-proof).
- Staging and proof before emission, and what a crash leaves:
  [General regular-file write](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#general-regular-file-write)
  and
  [Progress and crash boundaries](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#progress-and-crash-boundaries).
- Truncation across transactions through the orphan file:
  [General TRUNCATE](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#general-truncate).
- The storage controller's fault injection:
  [`inject_fault`](https://github.com/dgoldman0/megapad/blob/c3e8ef5f5e2c89c8f99f9919476fdbd31b89ef7e/emulator/devices.py#L912),
  and the tests' use of it, with the write and flush trace, in
  [`test_vfs_ext4.py`](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/local_testing/test_vfs_ext4.py#L4489-L4515).
- The tests' checks with e2fsck and their e2fsck recovery:
  [`test_vfs_ext4.py`](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/local_testing/test_vfs_ext4.py#L4132-L4167),
  and the pinned volume recipe in
  [the fixture manifest](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/local_testing/fixtures/ext4-profile/manifest.json).
- Worker jobs and their spans:
  [`worker-job.md`](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/concurrency/worker-job.md).
- The sandbox and its job service:
  [`sandbox.md`](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/sandbox/sandbox.md).
