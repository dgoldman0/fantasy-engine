# What the first release includes

Section 1 of [PLAN.md](../PLAN.md) says what the release is, and the plan
records what it waits for. This file is for working out what else belongs
in it, or what should leave it, before those questions become decisions.
Nothing here is decided.

## Questions the plan already holds open

- What managed data keeps after an LM1 failure (D13): lost, or taken back
  by a restarted LM1. MegaPad's `docs/managed-data.md` §11 says what a
  failure does today.
- Whether MegaPad's and LM1's hardware designs ship with it, at the same
  recorded commits as the software (Section 1, Proposed).
- Everything about running it on a Linux PC beyond the platform itself, such
  as the rich-terminal viewer and the emulator as a second backend
  (Section 1, Proposed).
