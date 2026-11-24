# Getting started

Fantasy Engine runs each configuration as a machine of its own on your
computer. `fantasy-engine run desktop` builds the Desktop's volumes and opens
it in a window; `fantasy-engine list` shows the configurations you have.

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
machine can reach services there that expect only local callers, and Desk
warns about it at every start.

The machine's memory lives in the server's process, and your computer may
write that memory to its swap space on the drive. Keys the machine holds can
then end up on the drive. Use encrypted swap, or no swap, on a computer where
that matters.
