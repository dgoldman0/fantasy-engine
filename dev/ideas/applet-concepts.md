# Future Applet Concepts: Observatory and Worlds

**Status:** non-normative design note  
**Date:** 2026-07-18  
**Authority:** none; this document does not amend or supersede the
workspace's `DESK_ECOSYSTEM_CONTRACT.md`  
**Implementation effect:** none; this document authorizes no code, package,
capability, store, migration, manifest, or gate change

> **Since this note was written** (checked on 2026-10-27, when it moved here
> from the workspace root): Observatory and Worlds both exist in Akashic, in
> `akashic/tui/applets/observatory/` and `akashic/tui/applets/worlds/`, and
> their own documents in `docs/tui/applets/` describe them as built.
> Sections 3 to 5 here are the earlier concept. Section 6.2's Streams
> direction was adopted in July, as it says. Akashic still has SoundLab and
> nothing named MediaLab. The rest of sections 6 and 7 has not been checked
> against current work.

## 1. Purpose

This document is a persistent record of two prospective applet ideas developed
after the Desk ecosystem contract was written:

1. **Observatory**, a scientific data-processing and analysis applet; and
2. **Worlds** (working name), a runtime for bounded, evolving models.

It also records adjacent product directions that make those applets coherent,
especially the possible evolution of SoundLab into MediaLab and the decision
to treat Streams as bidirectional rather than create a separate publishing
applet.

These are product concepts, not additions to the authorized implementation
sequence. Before implementation, each idea still requires an explicit product
decision, owner contract, bounded first slice, durable formats, capability
surface, failure model, qualification plan, and place in the gate sequence.

## 2. Ecosystem guardrails

Observatory and Worlds are intended to become useful peers in the ecosystem,
not new centers through which every other applet must pass.

The following principles apply to both concepts:

- Each applet must be useful on its own and remain optional to every existing
  applet.
- Each applet owns only its semantic domain. It must not absorb Desk routing,
  Practice authority, Library retention, Streams transport, Pad authoring,
  Grid worksheets, Agent reasoning, or MediaLab artifacts.
- Existing owners remain authoritative. Acquiring an exact input creates a
  bounded working reference or snapshot; it does not transfer the source
  resource's identity or ownership.
- Cross-applet use must occur through exact, typed resources, projections,
  capabilities, and intents. It must never depend on a selected row, focused
  pane, current tab, or borrowed mutable state.
- Neither applet becomes a universal database, workflow system, scripting
  host, or ambient automation layer.
- Neither applet receives automatic external authority. Practice and Desk
  continue to determine who may invoke a facet and which effects require
  review. Streams and the relevant physical owner continue to mediate external
  I/O.
- A reusable facility should move into shared Akashic substrate only after
  materially independent consumers prove the common contract. An applet idea
  alone is not evidence of generality.

A useful shorthand is:

> **Library retains. Observatory analyzes. Worlds evolves. Practice
> authorizes. Desk hosts and routes.**

## 3. Observatory

### 3.1 Product identity

Observatory's characteristic question is:

> **What can be measured, derived, compared, or inferred from this exact
> dataset?**

Observatory is the home for rich local scientific and engineering data
processing. It gives the existing Akashic math stack and MegaPad tile engine a
coherent product surface rather than leaving computation hidden behind Grid's
scalar worksheet or SoundLab's audio-specific analysis.

The applet name is **Observatory**. A saved, named analysis recipe or pipeline
may be called an **instrument**. This preserves both useful terms: Observatory
is the place where data is inspected and compared; instruments are the exact
methods applied to it.

### 3.2 Owned domain

Observatory should own:

- typed scientific dataset identities and schemas;
- columns, series, dimensions, units, timestamps or coordinates;
- explicit missingness, calibration and uncertainty metadata;
- reproducible instrument definitions and parameters;
- analysis-run identity, state, history and receipts;
- fitted analytical models and derived datasets produced by a run;
- comparisons between exact runs; and
- scientific reports and bounded visual projections of results.

An Observatory run record should identify at least:

- every exact input owner, RID/revision and digest;
- the admitted input schema and units;
- the instrument and algorithm versions;
- deterministic parameters and recorded seed where applicable;
- working and output precision;
- execution mode and relevant hardware placement;
- result identity and digest; and
- completion, cancellation or failure state.

Observatory should not own:

- Library corpus organization or corpus-search policy;
- Grid workbooks, formulas or interactive cell editing;
- Streams source configuration, acquisition or delivery;
- MediaLab timelines, media artifacts, playback or media export;
- Pad source editing or arbitrary native-code execution;
- Worlds live state, transition rules, event journals or branches;
- a universal notebook/document system; or
- a general semantic/vector database.

The domain test is simple: a one-shot or reproducible operation over measured
or structured data may belong in Observatory. Ordinary applet state does not
become an Observatory dataset merely because it can be serialized.

### 3.3 Standalone experience

The central user journey should be:

1. Acquire an exact dataset or explicit projection from Library, Grid,
   Streams, MediaLab, Worlds, a VFS import, or a supported device owner.
2. Inspect and qualify its schema, units, missing values and precision.
3. Choose or compose a bounded instrument from named operations.
4. Run it locally, with progress, cancellation and honest placement/precision
   information.
5. Inspect tables and TUI-native plots.
6. Compare the result with another exact run or source series.
7. Export a derived dataset or report explicitly to Grid, Library or another
   typed consumer.

The TUI is not a limitation for this product. Existing character-cell tables,
sparklines and Braille canvas primitives can support line and scatter plots,
histograms, box summaries, spectra, residuals, confidence intervals and
heatmaps without introducing a second graphical shell.

### 3.4 Scientific scope

The intended long-term scientific surface includes:

- descriptive statistics, distributions and percentiles;
- inferential statistics, confidence intervals and hypothesis tests;
- linear and polynomial regression, residual analysis and model comparison;
- probability and random sampling with recorded seeds;
- time-series smoothing, differencing, detrending, resampling and anomaly
  detection;
- FFT, filtering, convolution, correlation, autocorrelation and spectral
  analysis;
- interpolation, sorting, normalization and outlier handling;
- matrix, vector and field operations;
- experiment matrices, repeated runs and branch comparison; and
- local nearest-neighbor/vector ranking when compatible vectors already
  exist.

Vector ranking does not make Observatory the owner of Library semantic search.
Observatory may supply qualified general vector computation. If Library later
adopts embeddings as a disposable corpus index, Library must still own the
indexing and corpus-query policy, and that separate direction would require an
explicit contract decision.

### 3.5 Ecosystem contribution

Observatory should expose a portable, bounded dataset envelope and exact run
records so the rest of the ecosystem can use scientific processing without
depending on its UI.

Examples include:

- Streams projecting monitored observations into a time series;
- Grid supplying clean parameter tables or receiving derived tables;
- MediaLab exporting PCM windows, spectral features or image measurements;
- Worlds emitting fields, events and run telemetry for comparison;
- Agent invoking a named, authorized instrument and receiving a bounded result
  with the exact method and inputs visible; and
- Library retaining source datasets, reports and explicit derived artifacts
  with provenance.

Observatory is not automatically inserted between these owners. Each
integration remains an explicit optional acquisition or export.

### 3.6 Hardware fit and enterprise direction

Observatory is the clearest product showcase for the currently underexposed
512-bit tile/SIMD engine, HBW math memory, reductions, dot products, FP16/BF16
lanes, FP32 accumulation, FFT, and multicore execution. It should show useful
execution facts such as elapsed cycles, tile packing, working precision and
worker placement without turning into a hardware debugger.

Existing routines are a foundation, not an enterprise-quality claim. Several
are bounded, FP16-oriented, approximate at their tails, module-scoped or
non-reentrant. Building Observatory would surface candidate requirements for
later, separately justified work in:

- durable FP32 or otherwise declared canonical numeric representations;
- chunking and streaming beyond current fixed call bounds;
- units, schemas, missing values and uncertainty;
- deterministic recipes and stable algorithm versions;
- worker isolation and qualified concurrency;
- reproducible fixtures and numerical tolerances; and
- explicit refusal when precision or capacity cannot support a requested run.

FP16 may be an excellent acceleration format. It must not silently become the
authoritative storage precision for enterprise scientific data.

### 3.7 Bounded first slice

A credible first slice would remain deliberately small:

- exact CSV/text-series input;
- typed columns with units and one time or coordinate axis;
- descriptive profiling;
- a small set of smooth/detrend, regression, FFT/correlation and anomaly
  instruments;
- table, line, histogram and spectrum projections;
- visible cycle/precision information; and
- explicit CSV plus machine-readable run-record export.

It should not begin as an arbitrary notebook, plugin host, BI dashboard,
general database, live monitoring service or visual programming environment.

## 4. Worlds

### 4.1 Working identity and scope

**Worlds** is the working applet name; **world runtime** is the framework term.
The final singular/plural product name remains open.

Worlds' characteristic question is:

> **Given this exact state, these rules, these accepted observations and
> actions, and this clock, what happens next?**

Worlds is a runtime for bounded, persistent, evolving models. It is not a game
engine generalized after the fact, and it must not assume entertainment,
players, NPCs, combat, quests, health or inventory. Fictional, scientific,
operational, mirrored-real and agent environments are peer applications of the
same neutral domain.

A game campaign may eventually be one world package. It does not define the
applet.

### 4.2 Neutral model

The core nouns should be:

- **model** — typed entity, relation and field schemas; optional topology;
  observation and action types; transition rules; invariants; clock modes; and
  declared projections;
- **scenario** — an exact model revision bound to initial state, parameters,
  mappings and a recorded seed;
- **run** — one authoritative evolving state with a clock, accepted inputs,
  transition journal and current revision;
- **entity** — a stable identity with typed components or attributes;
- **relation/location** — an optional graph, room, grid or coordinate
  relationship; spatiality is available but not mandatory;
- **field** — dense or sparse values over entities or a topology;
- **observation** — an admitted external or internal fact presented to the
  model;
- **action** — a requested intervention from a user, Agent, rule or reviewed
  external adapter;
- **transition** — the canonical accepted state change produced by applying
  rules;
- **checkpoint** — an exact restorable run state;
- **branch** — a new run derived from an exact checkpoint; and
- **projection** — a bounded read-only view over entities, regions, fields,
  actions or timeline state.

The conceptual transition is:

```text
new state = rules(
    old state,
    accepted observations,
    accepted actions,
    clock,
    recorded randomness
)
```

Every accepted transition advances one authoritative run revision and appends
enough ordered evidence for inspection and replay. External observations and
random choices must be recorded; replay must never invent them again.

### 4.3 Owned domain

Worlds should own:

- validated executable model semantics and their schemas;
- persistent world/run identities and branch ancestry;
- live entity, relation, field and clock state;
- the closed vocabulary of available in-world actions;
- canonical transition validation and commit;
- accepted observation/action records and the ordered transition journal;
- checkpoints, branching and deterministic replay; and
- exact projections over current or historical run state.

Worlds should not own:

- Library's retained source material, collections or corpus indexes;
- Practice membership, system authority or capability grants;
- Streams acquisition, provider state, publication or external delivery;
- Observatory datasets, statistical analysis or fitted analytical models;
- Grid workbooks or Pad source editing;
- MediaLab artifact creation, rendering or playback;
- Desk lifecycle, worker scheduling or physical I/O ownership;
- arbitrary native code supplied by a retained document; or
- every workflow or mutable record in the system.

The hard domain test is:

> If something is not a bounded evolving causal model with explicit state over
> time, it is not a World.

A document collection, conversation, worksheet, ordinary workflow, dashboard
or one-shot numeric transform must not be reclassified as a world.

### 4.4 Standalone experience

Worlds should be a real applet rather than a headless engine launcher. Its core
verbs are:

> **model, run, observe, intervene, checkpoint, branch and replay**

The central journey should be:

1. Create from a bounded template or load an exact validated model/scenario.
2. Inspect initial entities, relations, fields, rules, inputs and clock mode.
3. Run, pause, single-step or follow admitted external observations.
4. Inspect current state and the exact events that produced it.
5. Submit one permitted action against an expected run revision.
6. Checkpoint, branch, replay or compare a different course of events.
7. Export exact projections and telemetry to another owner.

The TUI may select among a map, graph, table/roster, field, inspector and
timeline view according to the model's declared projections. A map is one
possible lens, not the public ontology.

Worlds needs a bounded declarative composer for schemas, initial state,
parameters, mappings and installed rule modules. Advanced rule implementation
belongs in Pad or a later developer tool. A retained world package must not be
able to smuggle arbitrary native execution into the runtime.

### 4.5 Equal use cases

The abstraction is intentionally generic. Peer world types may include:

- facility, warehouse and supply-chain models;
- network-failure models and cyber ranges;
- emergency-response and operations exercises;
- ecology, population, epidemic and resource-flow models;
- digital twins fed by reviewed external observations;
- autonomous or multi-agent evaluation environments;
- historical, economic and educational interactive systems; and
- fictional societies, tactics, role-playing or settlement worlds.

No one category defines the core model.

Mirrored-real worlds require an especially clear distinction between
**observed**, **inferred**, **simulated** and **commanded** state. A world model
must never present its inference or prediction as physical ground truth.
Likewise, an in-world legal action is not system authority to produce a real
external effect.

### 4.6 Ecosystem contribution

Worlds becomes a reusable stateful-environment service without becoming the
ecosystem's orchestrator:

- **Library** may retain exact model packages, assets, exported checkpoints,
  journals or reports. Worlds still owns the authoritative live run.
- **Practice** may bind a world into an activity and attenuate which actor or
  action facets are available. Practice does not own the run.
- **Streams** may deliver a reviewed observation to a World adapter or carry
  an explicitly authorized proposed output. Worlds performs no provider I/O.
- **Observatory** may calibrate parameters, request an exact run matrix, and
  analyze fields, events and branch telemetry. Worlds owns every run and
  causal transition.
- **Agent** may inspect an exact projection or submit a typed proposed action.
  It never mutates world memory or becomes authoritative rule logic.
- **Grid** may supply snapshotted parameter tables and receive projections.
  Later Grid edits do not silently change an active run.
- **Pad** may author declarative definitions or trusted installed rule
  providers without becoming the live-state owner.
- **MediaLab** may provide exact media assets or render/sonify a projection.
  Worlds owns only semantic cues and state-to-view mappings.
- **Desk** hosts the applet and grants physical worker access. Worlds owns
  semantic time, not machine scheduling.

Other applets should be able to acquire exact entity, relation, field, region,
available-action, checkpoint and timeline projections without depending on the
Worlds UI.

### 4.7 Hardware fit and execution integrity

Worlds can use specialized hardware honestly where a model warrants it:

- tile/SIMD operations for dense fields, neighborhood rules, diffusion,
  occupancy, influence maps and population attributes;
- multicore execution for isolated systems, independent entities or parallel
  branches; and
- hashes and signatures for exact model/checkpoint identity where separately
  qualified.

One authoritative commit path must serialize accepted changes. Worker cores
may calculate proposals or independent runs, but they must never race to mutate
shared world state. Performance does not outrank deterministic history.

### 4.8 Bounded first slice

A first slice should prove the neutral runtime rather than a universal world
builder:

- deterministic discrete-event or fixed-step clocks;
- typed entities, relations and fields;
- explicit observation and action schemas;
- one canonical transition journal;
- checkpoint, branch and replay;
- table, graph and bounded grid projections; and
- two or three deliberately different small templates, such as an ecosystem,
  a facility/resource model and a multi-actor social model.

It should not begin with arbitrary plugins, continuous general physics,
multiplayer synchronization, unrestricted scripting, automatic real-world
effects or a full visual authoring IDE.

## 5. Observatory and Worlds together

These applets are complementary but not coupled.

| Question | Observatory | Worlds |
| --- | --- | --- |
| Primary object | Dataset and reproducible analysis run | Evolving causal state and transition run |
| Core operation | Measure, transform, fit, compare | Advance, observe, intervene, branch, replay |
| Time | A coordinate or analytical dimension | Part of authoritative model state |
| Rules/models | Analytical algorithms and fitted models | State-transition rules and invariants |
| Output | Derived data, fit, comparison, report | New state, event history, checkpoint, projection |
| Hardware emphasis | Tile/SIMD math, FFT, statistics, multicore runs | Dense fields, entity systems, parallel branches |

A typical optional loop is:

```text
Streams observations or Library datasets
                  |
                  v
        Observatory calibration
                  |
       exact parameters/model fit
                  |
                  v
             Worlds runs
                  |
       fields, events and telemetry
                  |
                  v
      Observatory comparison/report
```

Observatory does not gain authority to mutate a World, and Worlds does not
gain authority over the resulting scientific interpretation.

## 6. Adjacent ecosystem directions

### 6.1 SoundLab toward MediaLab

The agreed conceptual boundary is **artifact versus measurement**:

- **MediaLab** owns perceptual artifacts intended to be heard or seen. It
  creates, edits, synthesizes, sequences, mixes, renders, inspects, plays,
  transcodes and exports them.
- **Observatory** owns measured data and scientific analysis. It operates on
  typed quantities, units, coordinates, uncertainty and reproducible methods.

SoundLab's current bounded audio signal renderer and analyzer remains an
honest first slice. The product direction may expand it into **MediaLab** as
the audio surface grows into synthesis, sequencing, MIDI, mixing, effects,
timeline editing, playback and export, and as another media class becomes
real. A rename should follow actual product scope rather than precede it.

Raster media may later include image decode/encode, color, compositing and
TUI/Braille preview without requiring a complete graphical desktop. This
direction remains exploratory; MediaLab must not become the home for arbitrary
numeric data merely because media can be represented as arrays.

MediaLab may explicitly export PCM samples, spectral features, image
histograms or other measurements as an Observatory dataset. Observatory may
return fitted parameters or derived measurements. Ownership of the media
artifact remains with MediaLab.

### 6.2 Streams remains bidirectional

The 2026-07-25 Streams architectural reset (the workspace's
`prototype_archive/STREAMS_ARCHITECTURAL_RESET_HANDOFF.md`) promotes
this former prospective direction into the active product contract: avoid a
separate Courier or Publish applet and evolve Streams as a bidirectional
internet-data product. Acquisition was implemented first; no output runtime is
claimed to exist yet.

The Streams direction includes:

- destinations and provider-specific outbound adapters;
- a bounded outbox/delivery ledger;
- retries, cancellation and delivery receipts;
- reply/thread addressing and provider state; and
- honest accepted, delivered, failed and indeterminate outcomes.

Streams owns transport and provider delivery semantics. It does not own the
authored document, Library corpus, Pad editing, schedule policy or generic
workflow. Content should be authored by its semantic owner and handed to
Streams explicitly for delivery.

### 6.3 No separate Navigator or Studio now

A Navigator applet is not presently justified. Desk routing, Library query,
Explorer navigation, Practice bindings, intents and app-specific views already
make the ecosystem navigable. A separate Navigator would duplicate the shape
of the system rather than own a clear resource.

A general visual-composition Studio is also not presently justified. TUI-native
diagram, layout or structured composition should first become Pad capabilities
or reusable widgets. A future graphical shell may reopen that decision, but a
prospective graphics system is not grounds for a new applet now.

### 6.4 Library, Practice and rejected duplicate applets

Continuity/backup and Casebook/evidence workflows do not currently justify
separate applets. Library already owns retained material, exact revisions,
provenance, collections and lifecycle, while Practice binds resources and
authority around an activity. Future backup, export, structured-resource or
case-oriented affordances should first be tested against those existing
owners rather than create parallel stores.

This note does not broaden Library into a workflow engine, claim graph or
automatic backup service. It records only that a separate applet has not shown
a distinct enough owner boundary.

### 6.5 Library embeddings and local vector use

Embedding generation and vector querying remain separable operations. Vectors
generated externally or by a later local model can be stored locally and
ranked locally without a live embedding service. That can materially help an
Agent search an already-indexed corpus.

No vector database is authorized by this note. If Library later receives a
derived embedding index, Library should own corpus admission, index lifecycle
and query policy. Observatory may provide qualified vector math, and Agent may
consume bounded results, but neither becomes the corpus owner.

### 6.6 Campaign becomes content, not the generic applet

Campaign remains an interesting possible fictional world type: a persistent
tactics, role-playing, settlement or social scenario. Under the generalized
direction, it would be a validated Worlds model/scenario package rather than a
separate applet or the defining public ontology.

Existing ECS, systems, pathfinding, fog, behavior-tree, tile-map, dialog,
inventory and save libraries may support such a package. Their game-specific
nouns should not leak into the neutral Worlds contract.

## 7. Ideas not decided here

The following remain open and are not implied decisions:

- the final **World** versus **Worlds** product name;
- Observatory's durable dataset and run-record formats;
- canonical numeric precision and chunking limits;
- which inferential methods meet qualification standards;
- Worlds rule packaging, declarative language and sandbox boundary;
- authoritative checkpoint and journal storage formats;
- whether Worlds begins with two or three reference templates;
- the exact milestone at which SoundLab earns the MediaLab name;
- whether raster media belongs in MediaLab's nearer product horizon;
- whether a later Workbench has a distinct owner boundary; and
- any implementation order relative to the ratified master contract.

## 8. Explicit non-authorization

This document is deliberately separate from the master contract. It records a
direction worth preserving so it does not have to be reconstructed from
conversation, but it does not:

- add Observatory, Worlds or MediaLab to the active app catalog;
- authorize a new package directory or shared abstraction;
- change an existing owner, capability, durable format or VFS path;
- authorize Library embeddings or vector indexing;
- alter a gate, exit condition or implementation priority;
- authorize retirement or renaming of SoundLab; or
- justify modifying an established document.

Any of those actions requires a later explicit decision and the same bounded,
evidence-driven design discipline applied to the existing ecosystem.
