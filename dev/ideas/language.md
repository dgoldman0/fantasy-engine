# A language for both chips

Decisions 30 to 32 in [PLAN.md](../PLAN.md) settle that Leviathan gets a
language of its own, what shape it takes, and when work on it starts. D12
asks whether the first release waits for it. This file holds the thinking
that is still open. Nothing here is decided.

## Prior art

Each of these comes near part of what Leviathan needs, and none covers the
whole (decision 30). They are worth reading before the design goes further.

- **Factor.** A stack language with a collected heap, quotations, generic
  dispatch and checked stack effects. Its optimizing compiler turns stack
  code into register code, which is what LM1, a 32-register machine, needs.
- **Joy.** A functional stack language whose programs are lists, so code and
  data share one form, as in Lisp.
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
  actors, which is close to the question of what may cross between chips.
- **Henry Baker, "Linear Logic and Permutation Stacks: The Forth Shall Be
  First"** (1994). It argues that a stack, where every copy and drop is
  written out, suits linear logic. That bears directly on checking refs and
  handles.

## Open questions

- **Name.** None is chosen.
- **How kinds are written.** Akashic's stack comments already use informal
  names such as `addr`, `u`, `n`, `flag` and `xt`. A checker could start by
  reading those and add `ref`, `handle` and `span`, or the language could
  bring its own notation.
- **The return stack.** Forth code parks values with `>R`, `R@` and `R>`,
  and inside a `DO` loop `R` is the loop counter. The checker has to follow
  kinds through the return stack as well, including refs parked there inside
  a window.
- **Where the compiler runs.** LM1 is in every configuration (decision 24),
  so the compiler could be Lisp on LM1 that emits Forth for MegaPad and LM1
  code for LM1. It could also be Forth on MegaPad, or exist on both. The
  choice decides which chip must be running for a word to compile.
- **What raw-side quotations capture.** Decision 31 says they can't outlive
  the word that made them. Forth 2012's `[: ;]` captures nothing; the
  language could allow capturing values from the caller's frame.
- **Exact integers on MegaPad.** Integers are exact (decision 31), which on
  LM1 means fixnums that grow into bignums. Whether MegaPad words can hold
  exact integers, or only LM1 words can, is open.
- **Errors.** Forth throws numbered codes through `CATCH` and `THROW`, while
  Lisp signals conditions that handlers can resume. The language needs its
  own error form, and a rule for how an error crosses a job hand-off between
  the chips.
- **Names and case.** KDOS names ignore case, so a later definition hides an
  earlier one that differs only in case. The sandbox language is
  case-sensitive, with reserved words in uppercase. Raw words compiled to
  Forth inherit KDOS's rule.
- **Lisp data in the source.** How list literals and symbols are written in
  a stack language, and whether its macros are Lisp macros run on LM1 or
  Forth immediate words.
- **Microcore kernels.** A microcore kernel is a word in a restricted Forth
  subset that works only in caller-owned buffers and may not allocate,
  perform I/O or throw (Akashic `docs/concurrency/microcore-kernels.md`).
  The span kind and the checker could also confirm that a kernel word stays
  within those rules.
- **The sandbox's artifacts.** Decision 31 allows that the subset with no
  raw memory could compile to the sandbox's artifact format. Whether that is
  worth doing, while the sandbox's own source language stays, is open.

## The first step

Decision 32 starts with a checker for Part 9d's rules, before any syntax.
The checker needs those rules in a form it can test: which words open and
close a window, which words write managed objects, and which words make and
release handles. Its first real input could be the Forth code that uses
managed data, beginning with Study's concept map, the first user Part 9d
names.

## In the Workshop

The Workshop teaches the system by building with it, in Forth on MegaPad and
Lisp on LM1 side by side (Part 7). A language that shows which chip runs
each word would let a learner see both engines working in one program.
