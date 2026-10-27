# Development material

This folder holds everything about building Fantasy Engine that isn't
documentation of its use and function: the plan for the first release, ideas
still being worked out, and notes for later releases. The release leaves it
out. It is cut on a release branch that removes `dev/`, while main keeps the
folder for the next release ([PLAN.md](PLAN.md), decision 33).

[PLAN.md](PLAN.md) is the plan for the first release. It records the
decisions taken and the decisions still open, and it sets out the work in
parts.

`ideas/` holds one file per topic. Nothing in it is decided. Once an idea is
decided, it moves into the plan as a decision or a step, and its ideas file
keeps only what is still open. A dropped idea is deleted, and its reasoning
stays in the commit message that removes it.

The repository is public, so everything here is public once pushed. Material
that must stay private goes elsewhere.

The topic files so far:

- [language.md](ideas/language.md): the language that spans both chips,
  beyond what decisions 30 to 32 settle.
- [use-cases.md](ideas/use-cases.md): what people might do with Fantasy
  Engine beyond the plan's Practices.
- [release-scope.md](ideas/release-scope.md): what the first release should
  include or leave out.
- [future-releases.md](ideas/future-releases.md): what comes after the first
  release.
- [applet-concepts.md](ideas/applet-concepts.md): Observatory, Worlds and
  the directions around them, a July 2026 note that predates both applets.
- [native-filesystem.md](ideas/native-filesystem.md): the filesystem derived
  from ext4 that would follow standard ext4, a July 2026 note.
