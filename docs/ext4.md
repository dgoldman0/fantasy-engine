# The ext4 driver

ext4 is a standard Linux disk format, the one many Linux computers keep their
files in. Fantasy Engine's ext4 driver reads and writes volumes in that format
from inside the machine. It runs on MegaPad under KDOS, as part of Akashic's
filesystem library, and it is written in Forth, about 32,000 lines of it. With
it, a program on the machine can mount a volume made on a Linux PC, read its
files, change them, and hand the volume back to the PC, whose own ext4 tools
open it and check it.

The driver mounts a volume in one of two ways. Its read-only binding,
`EXT4-BINDING`, reads volumes with 1, 2 or 4 KiB blocks and 128- or 256-byte
inodes. Its staged write binding, `EXT4-STAGED-WRITE-BINDING`, also changes
volumes with 1 KiB blocks and 256-byte inodes, through the operations listed
under [What the writer changes](#what-the-writer-changes). The writer serves
one trusted program at a time: it needs the volume to itself, and it applies
no permission checks. Desk and its applets keep their own files on MP64FS,
KDOS's native filesystem, and the ext4 driver serves the programs that mount
an ext4 volume themselves.

## What sets it apart

An ext4 volume contains two records of its blocks. Each file's map lists the
blocks that hold the file's data, and the block bitmaps mark, one bit per
block, which blocks are in use. Linux's ext4 code allocates from the bitmaps
as they stand, and e2fsck, run from time to time, cross-checks them against
the files. This driver performs that cross-check itself whenever it writes. At
a mount's first write it walks every file and every fixed structure on the
volume and proves that the bitmaps mark exactly the blocks those owners hold,
each block held once. If it finds a mismatch anywhere, it refuses every write
to the volume until a remount's proof succeeds.

Once the proof holds, the driver checks each transaction's own changes: a
block the transaction frees must be marked in use and mapped once by the
file's old map, a block it allocates must be marked free, and every map it
changes must differ from the old map by exactly the blocks allocated and
freed. The driver therefore refuses, before commit, any transaction that would
map a block by mistake, map one twice, or drop a block from a map while
leaving it marked in use.

Before acting on any structure it reads, the driver also verifies it. Each
piece of ext4 metadata has a CRC32C checksum. At mount the driver verifies the
superblock, every group descriptor, every bitmap in use, every backup copy of
the superblock and descriptors, and the journal, and it verifies inodes,
folder blocks, extent-tree nodes and extended-attribute blocks as it reads
them. Before it uses a block for a file's data or map, it also checks that the
bitmap marks the block in use. MegaPad's CRC32C hardware computes every one of
these checksums, and the driver checks for that hardware before it reads the
volume.

One exact format, the profile `akashic-ext4-rw-v1`, covers every volume the
driver mounts, and its features are listed under
[Making a volume](#making-a-volume). The driver reads a volume's feature flags
first and refuses a volume with any feature outside the profile, with
`VFS-R-UNSUPPORTED` and the detail `EXT4-D-FEATURE`, before it writes
anything. The rule covers even the features ext4 marks compatible, which the
format lets an older driver ignore.

Each change the driver makes is a transaction in the volume's journal, kept in
JBD2, the journal format Linux's ext4 uses. The driver stages a whole
transaction in memory and proves it before it writes any of it, so the volume
stays as it was when the driver refuses a transaction. Then it writes the file
data in place, writes the metadata to the journal with a commit block, and
copies the metadata home. At the next mount after a crash, the driver replays
every committed transaction and finishes the work the volume's orphan file
records, such as a truncation that spans several transactions or the deletion
of a file that was still open. It completes a truncation that Linux left
unfinished in the same way. Because the journal follows the standard format,
e2fsck on the PC replays it too.

All of the driver's working memory comes from arenas the program provides, and
the driver sizes it from the volume: the ownership proof needs one bit per
block, and the journal map needs a table sized to the journal. A program that
provides too small an arena receives `VFS-E-NOMEM` and can mount again with a
larger one.

## Making a volume

On a Linux PC, mke2fs from the e2fsprogs package makes a volume that both
bindings mount, with 1 KiB blocks, 256-byte inodes and the profile's exact
features, in an image file:

```sh
mke2fs -t ext4 -b 1024 -I 256 -o linux \
  -O none,has_journal,ext_attr,resize_inode,dir_index,orphan_file,sparse_super,large_file,huge_file,dir_nlink,extra_isize,metadata_csum,filetype,extent,64bit,flex_bg,metadata_csum_seed \
  -E lazy_itable_init=0,lazy_journal_init=0,root_owner=0:0 \
  volume.img 64M
```

`-O none,` clears whatever features a distribution's mke2fs configuration
would add, so the list sets the profile exactly, and `-o linux` records Linux
as the volume's creator, which the driver requires. `root_owner=0:0` gives the
root folder the owner the writer requires of each parent folder it changes,
and the two `lazy_` options have mke2fs write out the inode tables and the
journal in full. The command matches the volumes the driver is checked
against, made with e2fsprogs 1.47.4, and mke2fs creates the orphan file the
profile requires from version 1.47.0 onward. debugfs, from the same package,
adds files to an image directly:

```sh
debugfs -w -R "write notes.txt notes.txt" volume.img
```

## Mounting a volume and reading it

The driver mounts a KDOS volume. KDOS's `BD-OPEN-UNIT` opens a storage unit as
a block device, `VOL-RAW` makes a volume of the whole device, and `VOL-SLICE`
makes one of part of it. KDOS requires both descriptors to start zero-filled.
The program below mounts the volume on unit 1 read-only, lists its root folder
and reads the start of a file:

```forth
REQUIRE utils/fs/drivers/vfs-ext4.f

CREATE bd  /BLOCK-DEVICE ALLOT   bd  /BLOCK-DEVICE 0 FILL
CREATE vol /VOLUME ALLOT         vol /VOLUME 0 FILL
bd SETTINGS-UNIT BD-OPEN-UNIT THROW
bd vol VOL-RAW THROW

524288 A-XMEM ARENA-NEW THROW CONSTANT fs-arena
fs-arena vol EXT4-NEW THROW CONSTANT fs
fs VFS-USE
fs VFS-DIR

S" notes.txt" VFS-FF-READ fs VFS-OPEN? THROW CONSTANT fd
CREATE buf 1024 ALLOT
buf 1024 fd VFS-READ? THROW .
fd VFS-CLOSE? THROW
0 fs VFS-UNMOUNT THROW
```

On MegaPad's emulator, each storage unit holds a disk image file from the PC.
`cli.py --settings-storage volume.img` attaches an image as unit 1, the
settings disk, which the emulator write-protects, so the volume there mounts
read-only through either binding, as in the example.

`EXT4-NEW` verifies the volume before it returns. The read-only binding then
reads linear and indexed folders, files mapped by extent trees or by ext4's
older block maps, sparse files, whose holes read as zeros, symbolic links,
extended attributes including POSIX ACLs, and the metadata of FIFOs and device
files, and `VFS-STATFS` reports the volume's size and free space.

## Writing files

Writing needs the volume on a writable unit, and on the emulator that is unit
0, the system disk, which `cli.py --storage` attaches at start. The monitor's
`storage swap volume.img` command replaces the system disk's image in the same
session. KDOS's existing descriptors stay bound to the image they were opened
on, so after the swap their reads and writes return a stale error. A program
therefore loads the driver and the datetime library while the system disk
still holds them, and after the swap it opens the new image with `BD-OPEN` and
mounts it through the staged binding.

The staged mount needs two more things before its first change: an arena for
its journal writer, and a clock for file times. The writer's arena follows
from a profile of three numbers, the most metadata blocks, data blocks and
revoke records one transaction may hold. `EXT4-WRITER-WORKSPACE-BYTES?` checks
that the profile fits the volume's journal and reports the arena size it
needs. The clock is any word with the stack effect
`( clock-context -- epoch-ms ior )`, and the one below reads the time through
Akashic's datetime library:

```forth
REQUIRE utils/fs/drivers/vfs-ext4.f
REQUIRE utils/datetime.f
\ The monitor's storage swap volume.img runs here.

CREATE bd  /BLOCK-DEVICE ALLOT   bd  /BLOCK-DEVICE 0 FILL
CREATE vol /VOLUME ALLOT         vol /VOLUME 0 FILL
bd BD-OPEN THROW
bd vol VOL-RAW THROW

524288 A-XMEM ARENA-NEW THROW CONSTANT fs-arena
fs-arena vol EXT4-STAGED-WRITE-NEW THROW CONSTANT fs

16 16 8 fs EXT4-WRITER-WORKSPACE-BYTES? THROW
A-XMEM ARENA-NEW THROW CONSTANT writer-arena
writer-arena 16 16 8 fs EXT4-BIND-WRITER-ARENA? THROW

: now-ms  ( clock-context -- epoch-ms ior )  DROP DT-NOW-MS 0 ;
' now-ms 0 fs EXT4-BIND-WRITE-CLOCK? THROW

fs VFS-USE
S" log.txt" fs VFS-MKFILE? THROW DROP
S" log.txt" VFS-FF-WRITE VFS-FF-APPEND OR fs VFS-OPEN? THROW CONSTANT log
S" first entry" log VFS-WRITE-EXACT THROW
log VFS-CLOSE? THROW
0 fs VFS-UNMOUNT THROW
```

Each `VFS-WRITE?` call commits as much of its span as one transaction holds
and returns the bytes it committed, and `VFS-WRITE-EXACT` repeats the call
until the whole span is written, each part committed on its own. A larger
profile lets one transaction hold more of a write, and the profile must cover
what each operation needs. An overwrite needs the inode's block plus one data
block for each block written, and an allocation adds the bitmap and descriptor
block of each group it draws from, and the superblock. Making a folder needs
up to nine metadata blocks, growing an indexed folder's root needs eleven, and
removing a folder needs one revoke record. The driver refuses an operation
that needs more than the profile holds with `VFS-E-NOSPC`, the error it also
returns when the volume is full. Unmounting empties the journal, marks the
volume clean and releases the writer's arena.

## What the writer changes

The writer's operations are the nine below, each within the shapes it
describes, and the driver refuses a request outside them before it writes
anything. Each parent folder whose names an operation changes must belong to
root, user 0, and have its setgid bit clear. While a deleted file stays open,
the writer refuses other changes until the driver frees that file at its last
close.

- **Write** (`VFS-WRITE?`, `VFS-WRITE-EXACT`): overwrites a file, grows it
  from any end, and writes past its end, leaving a hole between. The file's
  only inode flag is `EXTENTS`, and its extent tree may have any depth. A
  write that reaches a preallocated, unwritten extent commits the blocks
  before it and stops there.
- **Truncate** (`VFS-TRUNCATE`): sets a file to any size. A growth leaves a
  hole, and a shrink too large for one transaction continues over several,
  recorded in the orphan file.
- **Create** (`VFS-MKFILE?`, `VFS-CREATE`): makes an empty file. A one-block
  folder that fills becomes an indexed folder, whose full leaves split and
  whose index can grow one level; beyond that, a new name goes where a leaf
  has room.
- **Make a folder** (`VFS-MKDIR`): makes an empty one-block folder, in a
  one-block parent or an indexed parent's leaf that has room for the name.
- **Link** (`VFS-LINK`): gives a file a second name, in a folder block or
  indexed leaf that has room.
- **Remove a name** (`VFS-RM` on a file): removes one name. When that was the
  file's last name, the driver deletes the file at once, or at its last close
  if it is open. A deleted file's extent tree may be at most one level deep.
- **Remove a folder** (`VFS-RM` on a folder): removes an empty folder that has
  stayed within one block.
- **Rename** (`VFS-RENAME`, `VFS-RENAME-AT`): moves a file within a folder or
  between folders, or an empty folder between folders, to a free name in a
  folder block or indexed leaf that has room for it.
- **Set attributes** (`VFS-SETATTR`): sets a file's mode, owner, group, and
  access, modification and change times.

## After a crash

At the next mount after a crash, the driver finds each transaction in one of
two states: committed, which it replays, or uncommitted, whose old records the
volume still holds. What a program then sees in a file follows from that. A
write that allocates blocks or changes a file's size reports its bytes only
once its commit is on the disk, so the file afterwards shows its old size and
contents or the committed ones, and an append that a single `VFS-WRITE?` call
commits whole lands all at once. A write that only overwrites blocks inside a
file puts its bytes straight onto those blocks, so a crash in the middle can
leave it partly written, down to single 512-byte sectors. A record that must
land whole is therefore best appended.

The driver performs this recovery, and the orphan file's work, while it mounts
the volume through either binding, so mounting writes to a volume that needs
recovery. On a write-protected unit, the driver refuses such a mount with a
read-only error. When a failure follows a transaction's commit, the driver
keeps the mount read-only for the rest of the session, and the next mount
replays the transaction.

## Checking a volume on the PC

On the emulator, each flush the driver issues makes the emulator write the
changed sectors to the image file, so once the program has unmounted the
volume, the file on the PC holds every change. e2fsprogs then reads the image
directly. `e2fsck -f -n volume.img` checks every structure and leaves the
image unchanged, exiting with status 0 when the volume is clean, and
`debugfs -R "cat log.txt" volume.img` prints a file. For the image of a
session that crashed, `e2fsck -E journal_only -y` run on a copy replays just
the journal, and its result can be compared with the volume the driver's next
mount produces.

## Notes

This page describes the driver in Akashic at commit
[`6ebed51d`](https://github.com/dgoldman0/akashic/commit/6ebed51dc892319448a50786d7115f891c8dacfd)
of 5 November 2026. Akashic's documentation of
[the driver](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md)
and of
[the format profile](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/ext4-compatibility-profile.md)
is the full reference. The statements above rest on these places in that
commit:

- The ownership proof and each transaction's map check:
  [Block ownership](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#block-ownership),
  and the proof in
  [`vfs-ext4.f`](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/akashic/utils/fs/drivers/vfs-ext4.f#L11663).
- Checksums in MegaPad's CRC32C hardware:
  [the driver document](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md?plain=1#L773).
- The exact feature profile:
  [Exact primary feature set](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/ext4-compatibility-profile.md#exact-primary-feature-set),
  checked in
  [`vfs-ext4-admission.f`](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/akashic/utils/fs/drivers/ext4/vfs-ext4-admission.f#L929-L956).
- Mounting, the writer's profile and its clock:
  [Mounting](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#mounting).
- Writes, and what a crash leaves:
  [General regular-file write](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#general-regular-file-write)
  and
  [Progress and crash boundaries](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#progress-and-crash-boundaries).
- Truncation across transactions:
  [General TRUNCATE](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#general-truncate).
- The writer's operations and their shapes:
  [Current staged writes](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#current-staged-writes)
  and
  [Deliberate remaining limits](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#deliberate-remaining-limits).
- What the read-only binding reads:
  [Read and inspection behavior](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/docs/utils/fs/drivers/vfs-ext4.md#read-and-inspection-behavior).
- The mke2fs options of the volumes the driver is checked against:
  [the fixture manifest](https://github.com/dgoldman0/akashic/blob/6ebed51dc892319448a50786d7115f891c8dacfd/local_testing/fixtures/ext4-profile/manifest.json#L38-L72).
- KDOS's block devices and volumes: MegaPad's
  [block-volume contract](https://github.com/dgoldman0/megapad/blob/c3e8ef5f5e2c89c8f99f9919476fdbd31b89ef7e/docs/block-volume-contract.md).
