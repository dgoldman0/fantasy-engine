# Future Filesystem Concepts: an ext4-derived native filesystem

**Status:** selected long-term architectural direction; format not yet
ratified  
**Date:** 2026-07-18  
**Authority:** none; this document does not amend or supersede the
workspace's `DESK_ECOSYSTEM_CONTRACT.md`  
**Implementation effect:** none beyond preserving the direction; active work
remains governed by the workspace's `FILESYSTEM_HANDOFF.md`

> **Since this note was written** (checked on 2026-10-27, when it moved here
> from the workspace root): ext4 is now the first release's filesystem,
> supported to the degree an alpha tester needs ([PLAN.md](../PLAN.md),
> decision 9 and Part 2). Akashic's ext4 binding reads ext4, and its staged
> write mode is a preview, so the standard-ext4 work in section 11 is under
> way. The ext4-derived native filesystem described here is not part of the
> plan for the first release.

## 1. Purpose

This document preserves the filesystem conclusion reached during the Megapad,
Akashic, Desk, and Practices storage discussion so that a later session does
not have to derive it again.

The selected long-term direction is a filesystem derived from ext4's mature
foundation and extended with the most valuable BFS-inspired capabilities,
co-designed with Akashic's VFS. Working labels such as **Ext4e**, **Ext5**, or
**Akashic filesystem** are placeholders only. The exact name, feature-bit
assignments, and on-disk format are not decided here.

This is more specific than “consider a modified ext4.” The architectural
judgment is that an ext4-derived native filesystem is the best current route
to the desired combination of mature general-purpose storage, ecosystem-native
metadata, queries, observation, and transactions. Standard ext4 must be
implemented first so that the project gains a correct baseline, real-image
interoperability, and direct evidence about which extensions are actually
needed. The successor must then be designed at full intended scope before its
implementation begins, even though implementation will be phased.

## 2. The conclusion in one statement

> Build and qualify standard ext4 first, then design a coherent ext4-derived
> native filesystem that retains ext4's proven storage machinery while adding
> BFS-inspired typed metadata, persistent indices, queries, observation, and
> ecosystem-relevant transactional/history capabilities through explicit VFS
> contracts.

This direction is preferred over three alternatives:

- standard ext4 forever, because it does not natively provide typed indexed
  attributes, filesystem queries, live query behavior, or the complete
  transaction/history surface the ecosystem may need;
- BFS proper, because BFS has the semantic features but not ext4's depth of
  integrity engineering, repair tooling, interoperability, feature evolution,
  and implementation ecosystem; and
- a filesystem invented from a blank page, because that would require the
  project to create allocation, directories, large-file mapping, journaling,
  recovery, checksums, tooling, and semantic features simultaneously.

This is a direction, not permission to fork ext4 casually. If full design
later uncovers a foundational contradiction, return to the user with the
evidence. Do not silently replace the conclusion with BFS, Btrfs, ZFS, a
minimal embedded filesystem, or a from-scratch format.

## 3. Why ext4 is the foundation

Ext4 already solves much of the difficult, non-distinctive work that any
serious Desk filesystem would otherwise have to rediscover:

- 64-bit-capable volumes and large files;
- stable inode identities and generations;
- scalable extent-based allocation, sparse files, and unwritten extents;
- linear and hash-indexed directories;
- hard links, symbolic links, modes, owners, timestamps, ACLs, and extended
  attributes;
- multiple block groups and mature free-space/inode accounting;
- JBD2 metadata transactions, replay, revocation, ordered-data behavior, and
  orphan recovery;
- metadata checksums and explicit compatible, read-only-compatible, and
  incompatible feature negotiation; and
- mature independent tools for format, inspection, checking, repair, resize,
  debugging, and interoperability testing.

These are not merely a list of disk structures. Ext4's value lies in its
documented invariants, accumulated failure knowledge, real images in the
world, and independent tools capable of rejecting or repairing damage. A new
filesystem would begin with none of that evidence.

Implementing an Akashic binding on the Megapad storage stack does not
automatically inherit the correctness of Linux ext4. It does, however,
provide a known format, observable reference behavior, external oracles, and
a vast adversarial test surface. That is a substantially stronger basis for
extension than either MP64FS or a new blank format.

## 4. What BFS contributes

BFS is not ext4 with extra features, and ext4 is not BFS with better tooling.
They specialize differently. The BFS ideas worth carrying forward are:

- attributes with explicit data types rather than only opaque byte values;
- persistent volume-wide indices keyed by selected attribute values;
- queries that resolve through those indices instead of requiring a separate
  application database or whole-volume scan;
- live queries that report when committed filesystem changes add or remove
  matching objects; and
- a desktop model in which files can be rich resources rather than byte
  streams whose meaningful metadata lives elsewhere.

Those ideas align naturally with Akashic resources, Desk discovery and
projections, and Practices' need to work with exact identified material. They
can reduce duplicated side databases and polling while allowing a file to
remain the durable physical object.

BFS proper is not the selected destination because it is not a superset of
ext4. Its journal primarily protects metadata structure, its integrity and
repair ecosystem is thinner, outside read/write interoperability is limited,
and it lacks the modern snapshot/data-integrity direction the ecosystem may
eventually want. Adopting BFS unchanged would also import BeOS-specific API
and format decisions instead of letting the existing Akashic VFS define the
right capability boundaries.

## 5. What the existing VFS contributes

Akashic's VFS is not an unfinished imitation of the BeOS filesystem API. It
already provides a broader framework around filesystem backends:

- independent VFS instances and binding-private state;
- mount routing and the ability to host different formats;
- a stable backend identity field on in-memory inodes;
- lazy directory materialization and bounded inode/descriptor pools;
- portable read, write, create, delete, truncate, rename, and sync concepts;
- checked replacement and fixed snapshot workflows above basic filesystems;
  and
- separation between physical filesystem operations and the semantic owners
  in Akashic, Desk, Library, Practices, and other domains.

That framework is one reason an ecosystem-native ext4 derivative is preferable
to BFS proper. The new filesystem should supply durable mechanisms that make
VFS promises real; it should not replace the VFS's multi-backend architecture
or absorb every domain above it.

The implemented VFS now uses one validated ABI-1 binding descriptor with a
capability-described 27-operation prefix; the former raw ten-slot table is no
longer a runtime interface. Same-major minor revisions may add a descriptor or
operation-table suffix while preserving that prefix. A future native binding
should keep ordinary filesystems usable through this portable surface while
adding explicitly negotiated richer facilities. Likely capability families
include:

- stable object identity and generation;
- binding-level atomic rename and namespace transactions;
- typed attribute enumeration, read, write, removal, and compare/update;
- persistent index definition and lifecycle;
- bounded query preparation and execution;
- committed change and live-query subscriptions;
- file, transaction, and volume durability boundaries;
- snapshots, revisions, clones, or checkpoint roots; and
- integrity, scrub, repair-status, quota, and space-reporting facilities.

FAT32 and MP64FS can continue implementing the portable core or explicit
fallbacks. They must not pretend to supply capabilities they cannot guarantee.

## 6. The intended natural fit

With FAT32, the VFS must synthesize publication and recovery conventions from
cluster-chain mutations and separately ordered directory writes. With the
native filesystem, important VFS concepts should correspond to actual durable
primitives:

- a VFS binding identity maps to a stable on-disk object and generation;
- a VFS transaction maps to one defined commit unit rather than a sequence of
  temporary-file conventions;
- `VFS-SYNC` maps to a journal/checkpoint commit followed by the real block
  durability boundary;
- rename and multi-object publication preserve stable identity and commit
  atomically within documented limits;
- typed attributes and file data can be committed coherently;
- a query consumes persistent index state bound to the same committed
  filesystem generation;
- live observation consumes a committed change sequence rather than polling
  an in-memory directory cache; and
- a snapshot or revision capability names a stable historical root instead of
  copying an arbitrary set of files one by one.

That relationship would be materially different from putting the same VFS
facade over FAT32. It is the principal reason to create an ecosystem-native
filesystem rather than stop after ext4 compatibility.

## 7. Candidate complete capability envelope

The full design must consider the complete destination before selecting a
first implementation slice. At minimum the design study must resolve the
following groups.

### 7.1 Proven general-purpose storage

Retain or deliberately replace ext4's 64-bit addressing, inode generations,
extent trees, sparse/unwritten ranges, indexed directories, allocation groups,
links, permissions, timestamps, ACLs, xattrs, quotas, journaling, orphan
recovery, feature negotiation, checksums, and host inspection/repair story.
No semantic feature justifies weakening basic filesystem reliability.

### 7.2 Typed resource metadata

Define canonical attribute types, encoding, comparison and collation,
namespaces, size limits, ownership, access control, update semantics, and
schema/version behavior. Types must be useful to indices and queries without
turning the filesystem into the authority for Akashic domain schemas.

### 7.3 Persistent indices and queries

Define which intrinsic fields and typed attributes may be indexed, index
creation/removal/rebuild semantics, uniqueness or multiplicity, ordering,
collation, query predicates, bounded result pages, cursor generation,
cross-volume behavior, query planning, and behavior under index damage.

An index should normally be derived and rebuildable from authoritative inodes
and attributes, even if it is transactionally maintained. Damage must not
change domain facts or manufacture an empty corpus. The design must specify
when a query refuses, rebuilds, or falls back to a scan.

### 7.4 Observation and committed change

Separate ephemeral node watches from a durable committed change sequence.
Define which namespace, data, metadata, attribute, index, snapshot, mount, and
recovery events exist; ordering and coalescing; cursor persistence; overflow;
access control; replay bounds; and how live queries consume the stream.

Live notification must follow committed state. A listener must never observe
an index result that can disappear because the corresponding transaction did
not reach its commit point.

### 7.5 Transactions and durability

Define whether application-visible transactions can group file data,
attributes, namespace changes, index updates, and change records. Specify
credit/reservation limits, nesting policy, concurrency, deadlock rules,
failure and cancellation, commit identifiers, fsync interaction, and the exact
old-or-new states permitted after power loss.

JBD2 is a valuable foundation but its existing internal transaction model is
not automatically a safe public transaction API. Exposing transactions may
require new reservations, limits, and recovery invariants rather than merely
making a journal handle visible.

### 7.6 History, snapshots, and integrity

Decide whether the native format needs filesystem snapshots, per-resource
revisions, reflinks/clones, send/receive, or only transaction checkpoints.
Also decide whether mutable file data receives checksums, how checksums interact
with repair and redundancy, and how scrubbing reports damage.

Ext4's predominantly in-place update model makes cheap general snapshots and
mutable-data checksums the most architecturally difficult candidates. They
must be designed consciously; adding them late could convert the format to
copy-on-write indirectly and destabilize every earlier assumption.

### 7.7 Repair and interoperability

Specify formatting, checking, debugging, index rebuilding, journal inspection,
scrubbing, migration, downgrade/read-only access, backup/restore, and damaged
volume export from the beginning. The format is not complete if only its
kernel/VFS driver understands it.

## 8. Keep semantic authority above the filesystem

Filesystem-native typed metadata and queries do not authorize the filesystem
to become Akashic's universal semantic database. The filesystem should own
physical objects, names, bytes, attributes, indices, transactions, integrity,
and committed change. Domain owners must continue to own resource kinds,
schemas, revisions, retention, principals, policies, receipts, and legal or
workflow meaning.

For example, an indexed attribute may efficiently locate candidate Library
resources, but Library remains responsible for corpus admission and exact
candidate validation. A durable change record may wake a Practice, but
Practice remains responsible for authority and effect policy. A filesystem
snapshot may protect physical state, but it does not replace a domain's
revision or retention rules.

This boundary preserves portability. Standard ext4, FAT, network mounts, and
future filesystems can still participate through the base VFS, while the
native filesystem accelerates and strengthens operations that opt into its
capabilities.

## 9. Compatibility posture to design explicitly

The ext4-derived format should use ext4's feature-negotiation philosophy, but
the exact compatibility posture is not yet ratified. The full specification
must choose deliberately among mechanisms such as:

- ordinary ext4 xattrs and hidden files for rebuildable semantic state;
- a new `RO_COMPAT` feature when standard ext4 readers can safely expose base
  files but must not write without maintaining the added structures;
- a new `INCOMPAT` feature when ignoring the extension could expose incorrect
  data or corrupt the volume; and
- extended host tools that understand, rebuild, inspect, and repair the new
  metadata while retaining standard ext4 structures where safe.

Permitting an unaware ext4 writer while treating semantic indices as
authoritative would be incorrect: the writer could change an inode or xattr
without updating the new index. Either indices must be explicitly rebuildable
and invalidated after an unaware mount, or unaware writers must be refused.
This decision belongs in the format design, not in a driver-specific
workaround.

The desired recovery property is graceful access to ordinary file data with
standard tooling wherever it can be made safe. It is not worth weakening
transactional/index correctness merely to claim that every standard ext4
writer can modify the volume.

## 10. Why the full design must come first

Typed attributes alone could be encoded in existing xattrs. Queries could be
implemented over hidden B-trees. Watches could be an in-memory VFS service.
Snapshots could be deferred. Doing each locally attractive change in sequence
would nevertheless risk contradictory durability, identity, index, and
compatibility rules.

Before any Ext4e on-disk code is written, one coherent design must include:

- goals, non-goals, scale targets, and resource budgets;
- the VFS capability ABI and fallback behavior;
- object, namespace, attribute, index, query, change, transaction, and
  snapshot models;
- complete on-disk layouts, endianness, checksums, ownership, and feature
  flags;
- allocation and cache interactions;
- lock order, concurrency, transaction credits, and commit state machines;
- mount, replay, clean/dirty, orphan, detach, and power-loss behavior;
- corruption detection, bounded traversal, repair, and index rebuild rules;
- standard-ext4 read/write/refusal compatibility;
- format, check, debug, migrate, import, export, and recovery tooling;
- upgrade and downgrade paths;
- a fault-injection and external interoperability matrix; and
- the phased implementation plan against this stable destination.

The design need not claim perfect foresight. It must make the intended whole
and its invariants visible before implementation choices create accidental
format commitments.

## 11. Ordered relationship to active work

The selected direction does not change the immediate sequence in
`FILESYSTEM_HANDOFF.md`:

1. Correct the controller's completion, error, ordering, capacity, and flush
   contract and introduce explicit block-device/volume objects.
2. Extend the VFS binding contract honestly and keep MP64FS working through
   the new block boundary.
3. Pin the standard ext4 compatibility profile and its external fixture
   toolchain without claiming a driver.
4. Implement and qualify the standard ext4-compatible Akashic binding through
   ordered admission, recovery, and journaled-write landings, bidirectional
   real-image checks, journal replay, damage, and power-cut fixtures.
5. Use the completed binding and measurements to write and ratify the full
   ext4-derived native-filesystem specification described here.
6. Implement that already-designed specification in ordered phases, retaining
   standard ext4 access or explicit refusal exactly as the specification
   defines.

Standard ext4 is therefore not the final conceptual destination and not
throwaway work. It is the reliable baseline, compatibility implementation,
test oracle, migration source, and empirical foundation for the chosen native
filesystem.

## 12. Questions intentionally left for full design

The direction is selected, but these details remain open:

- the filesystem's final name;
- whether the first native format is a strict ext4 feature extension, a
  recognizable ext4-derived fork, or supports both modes;
- which BFS attribute types and query operators are appropriate;
- whether indices are always rebuildable or can enforce authoritative
  constraints;
- whether the durable change stream is mandatory or optional;
- the public transaction size and nesting model;
- whether snapshots/revisions require copy-on-write allocation;
- whether data checksums and repair require redundancy;
- the safe standard-ext4 read-only fallback boundary;
- which capabilities belong in the base VFS versus optional tables; and
- the migration path from MP64FS, FAT, and standard ext4 volumes.

These open details do not reopen the basic conclusion without new evidence.

## 13. Explicit non-authorization

This document preserves a selected future direction, but it does not:

- authorize implementation before the controller and standard ext4 goals;
- ratify an Ext4e name, magic value, UUID, feature bit, or disk structure;
- authorize an ad hoc ext4 fork or a hidden incompatible image;
- authorize copying Linux, Haiku, or `lwext4` code or changing the runtime
  toolchain/license posture;
- amend the VFS, MP64FS, FAT, Akashic, Desk, or Practices contracts;
- make filesystem metadata authoritative for every ecosystem domain;
- authorize retirement of MP64FS or removal of standard ext4 compatibility;
  or
- permit staged implementation to substitute for a complete prior design.

Any implementation authorization requires the standard ext4 milestone and a
later reviewed full-format specification with explicit invariants, tooling,
failure semantics, compatibility, and qualification.
