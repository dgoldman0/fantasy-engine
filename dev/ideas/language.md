# The language

Decisions 30 to 32 and 34 in [PLAN.md](../PLAN.md) settle that Leviathan
gets a language of its own, what shape it takes, that its quotations are
ordinary lists, and when work on it starts. The language names what code
needs, never a chip, and the toolchain decides where each task runs. D12
asks whether the first release waits for it. This file holds the thinking
that is still open. Nothing here is decided.

## A sketch

Every spelling here is a guess, since the syntax waits for the checker
(decision 32). The program is a piece of Study's concept map, which Part 9d
names as the first user of managed data.

```forth
RECORD concept  name links  END-RECORD

: link  ( concept concept -- )       \ the first concept now links to the second
    OVER concept.links CONS  SWAP concept.links! ;

: nearby  ( concept -- list )        \ concepts one or two links away
    DUP concept.links
    DUP [ concept.links ] MAP CONCAT
    APPEND UNIQUE  SWAP REMOVE ;

: title  ( span concept -- cell )    \ copy the name into a line buffer
    concept.name SPAN-PUT ;

VARIABLE shown                       \ the concept on screen
VARIABLE near                        \ nearby concepts, once ready

: ask  ( -- )                        \ start a task; returns at once
    shown @ [ nearby ] TASK  near ! ;
```

The kinds describe data. `span` and `cell` are plain data, while `concept`
and `list` are objects, and `RECORD` defines field words such as
`concept.links` and `concept.links!`. `ask` starts a task and returns at
once. On Leviathan, the job service would probably run the `nearby` task on
LM1 and keep `title` beside the screen on MegaPad, but nothing in the
program says so. On a machine with one engine and a software collector, all
of it would run there. No window or handle appears in the code, because the
compiler inserts them (decision 31).

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

- **Name.** None is chosen.
- **How kinds are written.** Akashic's stack comments already use informal
  names such as `addr`, `u`, `n`, `flag` and `xt`, and the sketch names
  objects after their records, such as `concept`. The checker for
  hand-written Forth also needs `ref` and `handle`, the kinds 9d's rules are
  about.
- **Spans are two cells.** A span is Forth's address and length, so a plain
  `SWAP` can split one. The checker has to know which shuffles keep a span
  whole.
- **The return stack.** Forth code parks values with `>R`, `R@` and `R>`,
  and inside a `DO` loop `R` is the loop counter. The checker has to follow
  kinds through the return stack as well, including objects parked there.
- **Tasks and their results.** The sketch's `TASK` takes a value and a
  quotation and returns at once, and Akashic already has futures
  (`docs/concurrency/future.md`). A result could be polled each frame or
  handed to a quotation that runs when the task ends.
- **The machine description.** What it holds (the engines, which devices and
  kinds each serves, and what work costs on each), who writes it, and
  whether costs are declared or measured. Also whether a program may add
  placement hints, and if so whether they live outside the program, as
  Halide's schedules do.
- **Automatic windows and handles.** The collector waits for open windows,
  so the compiler has to keep them short, probably by closing and reopening
  them inside long loops and holding objects across the gap as handles. Each
  automatic handle needs an owner: an object kept in a variable could belong
  to whatever owns the variable, such as an applet. Plain Forth that calls a
  word taking an object would presumably pass a handle.
- **Authority and Akashic's words.** Authority reaches code as capability
  values (decision 31), but Akashic's existing words reach devices directly.
  Where that boundary sits is open.
- **Where the compiler runs.** LM1 is in every configuration (decision 24),
  so on Leviathan the compiler could be Lisp on LM1 that emits code for both
  engines, Forth on MegaPad, or both. Written in the language itself, it
  would be placed like any other program.
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

Decision 32 starts with a checker for Part 9d's rules, before any syntax.
Tracking kinds through stack shuffles and quotations is the hard part, and
the same tracking is what lets the compiler insert windows and handles
(decision 31). The checker needs 9d's rules in a form it can test: which
words open and close a window, which words write managed objects, and which
words make and release handles. Its first real input could be the Forth code
that uses managed data, beginning with Study's concept map.

## In the Workshop

The Workshop teaches the system by building with it, in Forth on MegaPad and
Lisp on LM1 side by side (Part 7). Tools that show where the job service
placed each task would let a learner watch both engines at work in one
program.
