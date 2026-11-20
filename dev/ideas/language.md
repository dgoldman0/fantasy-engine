# The language

Decisions 30 to 32 and 34 in [PLAN.md](../PLAN.md) settle that Leviathan
gets a language of its own, what shape it takes, that its quotations are
ordinary lists, and when work on it starts. The language names what code
needs, never a chip, and the toolchain decides where each task runs. The
release waits for the part of it that score-guided search needs (decision
32), and D12 decides whether Study's concept map is written in it. The
language is named Uroko. This file holds the thinking that is still open;
the items marked decided are settled. Part 9d's rules for objects are now
specified as a proposal, in MegaPad's `docs/managed-data.md` and LM1's
`spec/05-memory-gc.md` §12, and the section on objects below gives Uroko's
side of them.

## A sketch

The program is a piece of Study's concept map, which Part 9d names as the
first user of managed data. How kinds are written is settled, by the
checker's first two rounds and the decisions of 2026-11-20. A kind follows
its item's name after a colon, inside the stack comment. A slot that holds
execution tokens states their effect as `xt( ... )`. A named effect is
declared once, as `( kind: nio-io xt( ... ) )`, and used as
`( holds: nio-io )`. `port|0: nio-port` names a cell that holds a port or
zero, and `s': span` names part of an input span. Every other spelling here
is a guess: objects and records, tasks, windows and handles, kinds for tile
arrays, and kernels wait on the compiler and on Part 9d's rules, which the
section on objects below proposes.

```forth
RECORD concept  ( name: string  links: list )

: link  ( a: concept  b: concept -- )        \ a now links to b
    OVER concept.links CONS  SWAP concept.links! ;

: nearby  ( c: concept -- l: list )          \ one or two links away
    DUP concept.links
    DUP [ concept.links ] MAP CONCAT
    APPEND UNIQUE  SWAP REMOVE ;

: title  ( buf: span  c: concept -- n: u )   \ copy the name into a buffer
    concept.name SPAN-PUT ;

VARIABLE shown  ( holds: concept )           \ the concept on screen
VARIABLE near   ( holds: task )              \ nearby concepts, once ready

: ask  ( -- )                                \ start a task; returns at once
    shown @ [ nearby ] TASK  near ! ;
```

The kinds describe data. `span`, `u` and `task` are plain data, while
`concept`, `string` and `list` are objects, and `RECORD` defines field words
such as `concept.links` and `concept.links!`. `ask` starts a task and
returns at once. On Leviathan, the job service would probably run the
`nearby` task on LM1 and keep `title` beside the screen on MegaPad, but
nothing in the program says so. On a machine with one engine and a software
collector, all of it would run there. No window or handle appears in the
code, because the compiler inserts them (decision 31); the section on
objects below shows what it would make of `title` and `shown`.

Quotations are ordinary lists (decision 34), so the same code is also data:

```forth
3 [ DUP * ] CALL        \ runs the list: 9
[ DUP * ] LENGTH        \ treats it as data: 2

: adder  ( n -- quot )      [ + ] CONS ;   \ 5 adder gives [ 5 + ]
: twice  ( quot -- quot )   DUP APPEND ;   \ [ 1 + ] twice gives [ 1 + 1 + ]
```

`adder` captures a value by putting it into the list, which does a
closure's job. `twice` changes a program the way a Lisp macro does, working
on a flat list of words.

## Objects and the rules for them

Proposed on 2026-11-20. An object is data in LM1's tagged format that a
collector manages: a record, a list, a string, a vector or a bytevector
(decision 31). On Leviathan, objects that code on MegaPad can reach live in
the shared heap, in memory MegaPad lends LM1, and LM1's collector frees
whatever nothing uses. Code on LM1 uses objects as Lisp does. Code on
MegaPad follows Part 9d's four rules, which MegaPad's
`docs/managed-data.md` states as obligations, with the words they use (its
§14) and the conformance tests the chiplet modules pass (its §15). LM1's
`spec/05-memory-gc.md` §12 states the collector's side.

In brief, MegaPad code reads objects directly but writes them only through
store words, which log every reference they store so that LM1's write
barrier sees it. It uses references only inside a window, during which the
collector neither moves nor frees a shared object, and it keeps anything
past a window as a handle, which names a slot the collector treats as a
root and rewrites when the object moves. Every handle belongs to an owner,
and closing the owner releases them.

### Kinds of objects

| Kind | Stands for |
|------|------------|
| `ref` | A reference to an object, valid only inside the window in which it was read |
| `record` | A reference to a record; every record kind refines it, as `( kind: concept record )` declares |
| `list`, `list( k )` | Nil, or a reference to a cons cell; the second form says what kind the elements are |
| `string` | A reference to a string, whose bytes are UTF-8 |
| `vector` | A reference to a vector of tagged words |
| `bytes` | A reference to a bytevector |
| `tagged` | Any word in LM1's format, as a field holds it: a fixnum, nil, t, a character or a reference |
| `handle`, `handle( k )` | A handle, which code keeps past windows; the second form names objects of kind k |
| `struct` | A record in plain memory: the address of its fields, managed by hand |

`record`, `string`, `vector` and `bytes` refine `ref`, and every reference
kind refines `tagged`. A handle is neither a reference nor an address, and
the checker keeps the three apart.

`record` now names collected records, as decision 31 does, and Akashic's
records in plain memory, which the first checker round called records,
become `struct`. Two things recommend the name. Forth 2012 calls such
layouts structures, with `BEGIN-STRUCTURE`, `FIELD:` and `END-STRUCTURE`,
and C's `struct` is the same idea, so programmers coming from either read
it correctly. And the language then has one word for each side of decision
28: records are collected, structs are managed by hand. The rename touches
two declarations in Akashic's Forth, `net/io-port.f` and
`net/transports/kdos-tls-port.f`, besides the checker's own tables, tests
and notes. `ref` and `handle` keep the meanings the first round gave them.

### Record kinds

A record kind's declaration names each field with its kind:

```forth
RECORD concept  ( name: string  links: list( concept )  seen: u )
```

Fields of object kinds, `tagged`, `flag` and `char` become the record's
tagged fields. Fields of plain kinds, such as `cell`, `n`, `u` or `addr`,
become raw words, a `span` taking two. A raw word holds all 64 bits, and
the collector never reads it as a reference, so a cell that wraps is stored
whole.

The declaration registers the kind's shape with the collector when its
module loads. It defines a constructor, such as
`make-concept ( name: string links: list( concept ) seen: u -- c: concept )`;
a reader and a writer for each field, such as
`concept.name ( c: concept -- s: string )` and
`concept.name! ( s: string c: concept -- )`; and a check that turns a
reference of no known kind into a concept, failing otherwise. The spelling
of all of these waits on the compiler and on these rules.

### What the compiler inserts

For a word placed on MegaPad, the compiler:

1. opens a window around each stretch of code that uses objects, and closes
   it before anything that may wait, such as a task's result, a device, input
   or a yield, opening another after;
2. polls inside every loop in a window whose length it cannot bound, and
   after a poll that reopened the window reads the loop's objects again from
   their handles;
3. keeps an object as a handle wherever it outlives a window: an object
   stored in a variable or a struct is held through a handle owned by the
   owner of that memory, which for an applet's state is the applet instance,
   and a value held across a reopening takes a handle under a mark of the
   current owner, released when the word ends;
4. compiles a word that takes or returns objects twice: once taking
   references, to run inside its caller's window, for compiled callers; and
   once as a wrapper taking and returning handles, which opens the window,
   for plain Forth, where a handle it returns belongs to an owner the caller
   names;
5. writes objects only through the store words, and checks a value it reads
   from a field before it uses it as a reference or a number;
6. names a task's objects by handles when it starts one: its inputs, and a
   handle that will receive its result.

For a word placed on LM1 it inserts none of this, since code on LM1 needs no
windows or handles. With these rules, the sketch's `title` compiles for
MegaPad to two words, and `shown @` becomes a handle that `ask` lends to
its task:

```forth
\ title, to run inside its caller's window
: title  ( buf: span  c: concept -- n: u )
    concept.name SPAN-PUT ;

\ the wrapper plain Forth calls, holding a handle
: title/h  ( buf: span  h: handle( concept ) -- n: u )
    [: OBJ-GET THROW  title ;] OBJ-WITHIN ;
```

### Forth written by hand

Hand-written Forth keeps the same rules with the same words, and the
checker checks it as it checks compiled code: every window opened with
`OBJ-WITHIN`, every object kept past one as a handle, and every write made
through a store word. MegaPad's `docs/managed-data.md` §14 ends with such a
word. The record declarations serve hand-written code too, since their
generated words carry declared effects.

### The rules as the checker enforces them

Each rule becomes checks on kinds and on two facts the checker infers for
every word: whether it needs an open window, and whether it may wait. A word
needs a window when it uses a reference it did not read inside a window of
its own, or calls a word that needs one; it may wait when it calls a word
that may. The base words' facts are declared, and every other word's are
inferred from its body, never taken from a comment.

1. **Windows pair.** `OBJ-OPEN` and `OBJ-CLOSE` pair on every path of a
   definition, as `>R` and `R>` do, and `OBJ-WITHIN` runs its token one
   window deeper. A word that needs a window is called only inside one.
2. **References die with their window.** A reference is made only inside a
   window, and is dead after the window's outermost close, after a poll's
   true branch, and after a call to any word that may poll. A word returns a
   reference only if it needs a window, so no reference outlives the window
   that read it.
3. **References are never kept.** A reference is not stored with `!` or
   `2!`, kept by `TO` or in a `VALUE`, compiled with `,` or `LITERAL`, or
   passed to a word that starts a task, a job or work on another core. The
   first round's checks of rule 4 cover part of this already.
4. **Objects change only through the store words.** An address computed
   from a reference may be read with `@`, `C@` or `2@`, which is rule 1's
   direct read, and never written with `!`, `C!`, `2!`, `+!`, `MOVE`,
   `CMOVE`, `FILL` or `ERASE`.
5. **No waiting in a window.** A word that may wait is not called inside a
   window. Waiting words include those that yield, sleep, wait for input or
   a device, wait for another core, or wait for a reply from the chiplet,
   except the region request that making an object may send.
6. **Windows stay short.** Inside a window, every loop has a count the
   checker knows or polls on every pass, recursion polls, and no token
   whose effect is unknown runs.
7. **Values are checked before use.** A `tagged` word becomes a reference
   only through `OBJ>REF` and a number only through `OBJ>INT`; a reference
   becomes a record kind only through that kind's check, a typed field, a
   typed handle or a constructor; and a number stored into a tagged field is
   known to fit a fixnum or passes through `INT>OBJ`.
8. **Handles are only handles.** A handle comes only from `OBJ-HANDLE`, a
   slot declared to hold one, or a word that returns one. It is not an
   address, a number or a reference, and `OBJ-GET` of a `handle( k )` gives a
   `k`.

Only checks at run time catch the rest, and MegaPad's library makes them:

- a stale handle, an owner token that names no owner, or one released
  twice;
- whether an object LM1 wrote has the kind its field declares, which code
  checks once per object and window when it narrows a reference;
- the tag and range of every reference and number read from a field;
- indices, offsets and lengths computed while the program runs;
- how long a window stays open, which LM1 reports when a hold waits too
  long, and running out of memory;
- whether code that spawned a task writes the task's inputs while it runs
  (see the open questions);
- anything plain Forth does outside the checker. The library's checks catch
  a bad reference or a store outside an object when one reaches them, and
  the collector's checks catch some corruption, but a plain `!` into the
  shared heap goes unseen.

### One engine and two

A program means the same on one engine and on two (decision 31), because
the rules describe what code needs and never which chip serves it. On a
machine without LM1, MegaPad's own engine can serve managed data with the
same words and records: its collector runs on a MegaPad core and holds the
other cores out the same way. The simplest engine that conforms never frees
anything, so every rule holds and only memory use differs. Whether the
release builds a collector for MegaPad is open, since every release
configuration has LM1.

A task keeps four rules on either engine, which LM1's `spec/06-runtime.md`
§3.5 states for LM1:

1. its inputs are lent: the code that starts it names them by handles, and
   neither re-points nor releases those handles until the task ends;
2. its inputs are read-only to it, on LM1 by capability mode, and on
   MegaPad, which has no capability mode, by the checker;
3. its objects stay its own: a store that would put one into an object it
   did not make is refused, so nothing escapes but its result;
4. its result is copied out into a handle that the starting code lent it.

On one engine, a task's objects then live in a heap that lasts as long as
the task, as decision 32 has it, and the refusal in rule 3 is the check
that nothing else escapes. On two engines, the same refusal is LM1's trap
on such a store, so a program that passes on one engine passes on two with
the same result.

## Prior art

Each of these comes near part of what Leviathan needs, and none covers the
whole (decision 30). They are worth reading before the design goes further.

- **Factor.** A stack language with a collected heap, quotations, generic
  dispatch and checked stack effects. Its optimizing compiler turns stack
  code into register code, which is what LM1, a 32-register machine, needs.
- **Joy.** A functional stack language whose programs are lists, so code and
  data share one form, as in Lisp. Decision 34 adopts this.
- **HP's RPL** (Reverse Polish Lisp). Typed objects on a stack, with an
  unchecked System RPL beneath a checked User RPL, over one collected memory.
- **PostScript.** Typed objects on a stack. `save` and `restore` bound
  object lifetimes to regions, and access attributes mark objects read-only
  or execute-only.
- **PreScheme**, in Scheme 48. A manual-memory subset of Scheme, compiled
  ahead of time, used to write the VM that full Scheme runs on.
- **Rust.** Precise, checked lifetimes for references, with no collected
  side.
- **WebAssembly with garbage collection.** Raw linear memory beside managed
  references, which raw memory can hold only through tables. Part 9d keeps
  refs past a window only as handles in much the same way.
- **Pony.** Reference capabilities that state what may be shared between
  actors, which is close to the question of what may cross between engines.
- **Henry Baker, "Linear Logic and Permutation Stacks: The Forth Shall Be
  First"** (1994). It argues that a stack, where every copy and drop is
  written out, suits linear logic. That bears directly on tracking objects
  through stack code.
- **Halide.** It keeps an algorithm apart from the schedule that maps it to
  hardware, so the algorithm itself names no hardware.
- **Futhark.** It compiles one data-parallel program for either a CPU or a
  GPU, with no hardware named in the source.
- **Erlang.** Programs create processes, and the schedulers decide which
  core runs each one.
- **Java JIT compilers.** They insert a collector's barriers and safe points
  into compiled code. This language's compiler would insert Part 9d's
  windows and handles in the same spirit.

## Open questions

- **Name.** Uroko, the Japanese word for a scale, chosen on 2026-11-20 for
  Leviathan's scales. It is Uroko Forth instead if the checker and compiler
  show it to be a dialect of Forth rather than a language of its own.
- **How kinds are written** (decided 2026-11-20). A kind follows its item's
  name after a colon, inside the usual stack comment, as Factor writes
  stack effects: `( buf: span  c: concept -- n: u )`. A slot that holds an
  execution token states the token's effect as a nested comment,
  `( holds: xt( text: span -- ) )`, and a record's fields take kinds the
  same way. An item without a kind is a plain cell. The checker's first
  round found that names such as `addr` or `u` cannot carry kinds reliably,
  and Akashic already uses `ref` and `handle` for things other than 9d's
  managed references, so no kind is guessed from a name. The source stays
  plain Forth, which KDOS reads with the declarations as comments.
- **Spans are two cells.** A span is Forth's address and length, so a plain
  `SWAP` can split one. The checker has to know which shuffles keep a span
  whole.
- **The return stack.** Forth code parks values with `>R`, `R@` and `R>`,
  and inside a `DO` loop `R` is the loop counter. The checker has to follow
  kinds through the return stack as well, including objects parked there.
- **Tasks and their results.** The sketch's `TASK` takes a value and a
  quotation and returns at once, and Akashic already has futures
  (`docs/concurrency/future.md`). A result could be polled each frame or
  handed to a quotation that runs when the task ends. Its objects cross as
  handles either way (the section on objects above).
- **A task's inputs while it runs.** The task cannot write its inputs, but
  nothing yet stops the code that started it from writing them while it
  runs, which would let the result depend on timing and so on placement.
  The checker cannot see every alias of what a task can reach. The choices
  are a rule left to the programmer, which the checker enforces where it
  sees the object itself written between the start and the result; a mark
  on every object a task can reach, which the store words check at the cost
  of a load and which costs a walk of that graph to set; or copying the
  inputs, which costs their size. The first is cheap and leaves a hole that
  only testing finds; the concept map's search would keep it by cancelling a
  search when the map changes.
- **The machine description.** What it holds (the engines, which devices and
  kinds each serves, and what work costs on each), who writes it, and
  whether costs are declared or measured. Also whether a program may add
  placement hints, and if so whether they live outside the program, as
  Halide's schedules do.
- **Inserting windows and handles.** The section on objects says what the
  compiler inserts, but whether that insertion works well is untested
  (decision 31). D12 waits on that evidence: a draft of the concept map's
  view, compiled for MegaPad, shows whether the windows come out short and
  the handles few.
- **Authority and Akashic's words.** Authority reaches code as capability
  values (decision 31), but Akashic's existing words reach devices directly.
  Where that boundary sits is open.
- **Where the compiler runs.** The first version runs in the image builder
  on the host and emits Forth source (decision 32). Running lists built
  while a program runs needs a compiler on the machine as well. On Leviathan
  that could be Lisp on LM1, Forth on MegaPad, or the language itself,
  placed like any other program.
- **What a word is as a value.** Lists hold words themselves, not their
  names (decision 34), so a word needs an object form that every engine can
  read, leading to its definition and to whatever code each engine has
  compiled for it.
- **Compiling lists.** Whether a list is compiled when it is made, when it
  first runs, or when a task lands on an engine, and how long compiled code
  is kept.
- **Exact integers in plain data.** Integers are exact (decision 31), so a
  large one is an object. Whether plain-data code can hold integers, or only
  cells, is open.
- **Errors.** Forth throws numbered codes through `CATCH` and `THROW`, while
  Lisp signals conditions that handlers can resume. The language needs its
  own error form, and a rule for how an error crosses from a task to
  whatever waits for its result. Akashic's worker jobs report failure as a
  result code and never throw across cores, which is one model.
- **Names and case.** KDOS names ignore case, so a later definition hides an
  earlier one that differs only in case. The sandbox language is
  case-sensitive, with reserved words in uppercase. Words compiled to Forth
  inherit KDOS's rule.
- **Lisp data in the source.** How list literals and symbols are written in
  a stack language, and whether macros are words that transform quotation
  lists while compiling or Forth immediate words.
- **Microcore kernels.** A microcore kernel is a word in a restricted Forth
  subset that works only in caller-owned buffers and may not allocate,
  perform I/O or throw (Akashic `docs/concurrency/microcore-kernels.md`).
  Because placement follows what code needs, a task whose code keeps those
  rules could run on a microcore without the program saying so, and the
  checker could confirm that it keeps them.
- **The sandbox's artifacts.** Decision 31 allows that code with no plain
  memory, holding authority only as capabilities, could compile to the
  sandbox's artifact format. Whether that is worth doing, while the
  sandbox's own source language stays, is open.
- **Sandboxed code and built lists.** Whether sandboxed code may run lists
  it builds is open (decision 34). The sandbox's source language never
  evaluates anything, so one answer is that sandboxed code may build lists
  and hand them on but never run them.

## The first step

Decision 32 starts with the checker when release work begins, before any
syntax. Its core tracks kinds through stack shuffles and the return stack,
needs nothing from LM1, and is tried first on existing Akashic code. The
same tracking lets the compiler insert windows and handles (decision 31),
which needs 9d's rules in a form it can test: which words open and close a
window, which words write managed objects, and which words make and release
handles. MegaPad's `docs/managed-data.md` now gives those words, as a
proposal, and the section on objects above lists what a later round of the
checker enforces. Study's concept map is the first managed-data code it
would handle, and D12 decides, now that 9d's rules are specified, whether
that map is written in the language.

## In the Workshop

The Workshop teaches the system by building with it, in Forth on MegaPad and
Lisp on LM1 side by side (Part 7). Tools that show where the job service
placed each task would let a learner watch both engines at work in one
program.
