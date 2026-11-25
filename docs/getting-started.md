# Getting started

Fantasy Engine runs each configuration as a machine of its own on your
computer. A configuration is one file that says what the machine runs: the
applications Desk opens, the machine's memory, the size of its disks, and its
network. The `fantasy-engine` command builds a configuration's volumes, the
disks the machine keeps its system and your files on, starts the machine and
opens the viewer, the window you use it through. This guide installs the
command, runs the Desktop, makes a configuration of your own, and explains
how to keep a machine's files safe.

## Installing

Fantasy Engine installs from source for now, on Linux on a 64-bit Intel or
AMD PC, or on Windows under WSL2, whose WSLg shows the viewer's window. The
[README](../README.md#installing) gives the four steps:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/),
   which needs no administrator rights and brings Python 3.13.
2. Install git, make, a C++17 compiler, pkg-config with libslirp's and GLib's
   development files, and e2fsprogs 1.47.0 or later. On Ubuntu 24.04 and
   Debian 12 that is `sudo apt install git build-essential pkg-config
   libslirp-dev libglib2.0-dev`.
3. Clone this repository and run `uv tool install --python 3.13 --editable .`
   in it.
4. Run `fantasy-engine doctor`.

`doctor` checks each thing the command needs and prints one line for each:
`ok` with what it found, `missing` with what to do about it, or `advice` for
something the machine runs without but works better with, such as the fonts
the viewer falls back to for scripts its own font lacks. It ends with an
error status while anything is missing, so run it again after you install
what it names.

## Running a machine

```
fantasy-engine list
fantasy-engine run desktop
```

`list` shows each configuration, whether it ships with Fantasy Engine or is
your own, and whether it has been built:

```
desktop  (shipped, not built)
```

`run desktop` builds the Desktop and starts it. The first time, the command
fetches the machine's three parts at the commits this repository records and
builds their native code, which takes about a minute; later runs reuse them.
Building the Desktop's volumes takes about ten seconds more, and the machine
then starts and the viewer opens. Closing the viewer stops the machine.

A machine keeps its documents between runs. Its user volume holds your
documents, your Practice and its records, and the command builds that volume
once and never replaces it. The other volumes hold the system, and `run`
builds them again when what they were built from changes: the commits this
repository records, the configuration file, or the documents it names.
`fantasy-engine build desktop` builds without starting the machine.

Each configuration keeps its machine in one folder,
`~/.local/share/fantasy-engine/configurations/NAME/`, and the command keeps
the machine's parts in `~/.cache/fantasy-engine/`. `--data-dir` and
`--cache-dir` move those trees.

## Making your own configuration

```
fantasy-engine new mine desktop
```

`new` copies the Desktop's configuration under the name `mine` and prints
where the copy is. Edit the copy, then run it with `fantasy-engine run mine`.
The new configuration gets a user volume of its own the first time it is
built, so your machines' documents stay apart.

The file is in TOML, the format Desk's own settings use. Its tables say:

- `[configuration]`: the format, which is `format = 1`, the `title`, and a
  `description`.
- `[[practice.entry]]`: an application Desk opens in a tile, one table per
  application, in order: `pad`, `file-explorer`, `daybook`, `grid`, `agent`,
  `streams` and others. `[practice] offer` lists applications Desk offers on
  its launcher without opening them.
- `[agent] provider`: the Agent's provider, which a configuration that opens
  or offers the Agent needs.
- `[machine]`: the machine's memory, `memory-mib`, and its full cores,
  `cores`, one to four.
- `[volumes.user]`: the user volume's size, `size-mib`, and a `documents`
  folder whose files the volume starts with. The folder is copied when the
  volume is made, and never again. A plain path is relative to the
  configuration file.
- `[viewer]`: the terminal's size, `cols` and `rows`, and the viewer's
  `font-size`.
- `[network]`: `enabled` lets the machine reach the internet, and
  `local-access` also lets it reach your computer and your local network.
- `[desk.rich-terminal]` and the other `desk` tables: values for Desk's
  system settings.

The command refuses a table or setting it does not know and names it, so a
misspelt setting never passes unnoticed. Akashic's
[configuration reference](https://github.com/dgoldman0/akashic/blob/main/docs/image/configuration.md)
describes every setting and its default.

## Keep your machine's files safe

Each configuration keeps its machine in one folder:
`~/.local/share/fantasy-engine/configurations/NAME/`. The folder holds the
machine's volumes. The user volume among them holds your documents, your
Practice and records, and any sign-in the Agent or Streams keeps. The machine
has no accounts or passwords of its own. Whoever can read the folder can read
everything the machine holds, and whoever can write to it can change what the
machine runs. Treat the folder as you would a file of passwords.

fantasy-engine makes the folder and its files readable by your account alone,
and `run` refuses to start a machine whose files another account could read or
write. Keep them that way. Back the folder up as you would back up passwords,
and keep any copy somewhere as private as the folder itself. A shared or
synced folder gives the machine to everyone who can read that folder.

While a machine runs, its server listens in your private runtime folder, and
the viewer talks only to a server that runs as you. Everything else a run
writes, its temporary files included, stays inside the configuration's
folder.

`fantasy-engine run --debug-access` lets any program that runs as you read
the machine's memory, keys included, and pause, step or reset it. Use it only
while you develop. Without it, the server also keeps its memory out of crash
dumps and closed to other programs.

A machine reaches the internet only when its configuration turns the network
on, and it never reaches your computer or your local network unless the
configuration sets `local-access`. With local access on, any program on the
machine can reach services there that expect only local callers, and both
the command and Desk warn about it at every start.

The machine's memory lives in the server's process, and your computer may
write that memory to its swap space on the drive. Keys the machine holds can
then end up on the drive. Use encrypted swap, or no swap, on a computer where
that matters.
