## Cryptographic Detective Box

### Overview

The Cryptographic Detective Box is a local, high-throughput evidence and reasoning appliance designed to turn messy digital reality into structured, verifiable conclusions that AI systems can safely rely on. It ingests heterogeneous corpora—logs, files, emails, source trees, packet captures, telemetry, and database extracts—then produces:

* A normalized event stream with stable identities (people/hosts/processes/files/keys/transactions)
* A continuously updated knowledge graph of relationships and causality candidates
* Fast similarity and clustering over very large datasets
* Tamper-evident provenance and replayable query traces
* Machine-usable “facts with receipts” for AI agents, auditors, and investigators

It is not intended to run large neural models. It is intended to be a dependable “ground-truth engine” that AI agents call to retrieve, verify, and explain.

---

### Primary Use Cases

#### 1) Incident Response and Threat Hunting

* Build an end-to-end timeline across systems (identity, endpoints, network, SaaS, CI/CD, cloud)
* Identify initial access vectors, lateral movement chains, privilege escalation, data staging, and exfiltration attempts
* Link artifacts across sources (same file seen via EDR + email attachment + object storage)
* Cluster suspicious behaviors into campaigns and operator playbooks
* Generate defensible reports with immutable evidence references

#### 2) Compliance, Audit, and Forensics

* Demonstrate chain-of-custody for evidence snapshots and derived findings
* Produce “why this conclusion” traces that are stable under re-run
* Verify retention rules, access policy conformance, segregation-of-duty violations
* Detect hidden policy drift by comparing declared controls vs observed actions

#### 3) Large-Scale Corpus Intelligence

* Deduplicate, fingerprint, and map huge datasets quickly (multi-terabyte corpora)
* Discover near-duplicate documents, code, binaries, configs, and templates
* Build entity-centric views (everything associated with a user/device/key/service)
* Answer cross-domain questions with strict provenance requirements

---

### Core Concept: Facts With Receipts

The system maintains a strict separation between:

* **Evidence**: immutable snapshots of raw inputs and normalized records
* **Derived artifacts**: indexes, sketches, clusters, scores, and graphs
* **Claims**: human-readable or AI-readable statements that always reference evidence

Every claim is accompanied by:

* Content hashes of referenced evidence items
* Time boundaries and scope of search
* Query plan version and rule set identifiers
* Deterministic replay instructions

This makes outputs suitable for high-stakes environments where an AI agent must be able to cite and defend conclusions.

---

### Data Sources and Ingestion

#### Supported Inputs

* Host and endpoint logs (process events, file events, authentication, kernel telemetry)
* Network telemetry (NetFlow, DNS, HTTP logs, packet captures)
* Identity and SaaS logs (SSO, MFA, admin actions, email metadata)
* Source repositories and build artifacts (commits, diffs, release bundles)
* Object stores and file shares (documents, binaries, archives)
* Databases and exports (CSV, Parquet, relational dumps)
* Security tooling outputs (EDR alerts, IDS, vulnerability scanners)

#### Ingestion Pipeline

1. **Acquisition**

   * Pull from connectors or receive via offline import
   * Snapshot metadata (source identity, time, transport details)
2. **Normalization**

   * Parse into a canonical schema: events, objects, actors, relationships
   * Resolve timestamps, time zones, and ordering ambiguities
3. **Identity Resolution**

   * Map aliases to stable IDs (usernames, emails, SIDs, service principals)
   * Correlate hosts across DHCP, cloud IDs, certificates, hardware IDs
4. **Content Fingerprinting**

   * Produce strong cryptographic digests and fast locality-sensitive fingerprints
   * Extract structural features (e.g., code symbol sets, doc shingle sets)
5. **Indexing**

   * Build searchable indices and summary sketches
   * Update knowledge graph edges incrementally
6. **Evidence Sealing**

   * Write evidence blocks into an append-only store with integrity manifests

---

### Evidence Store and Provenance

#### Evidence Blocks

Evidence is stored as immutable blocks containing:

* Raw bytes (or a chunk reference)
* Normalized record representations
* Source metadata (origin, capture method, timestamps)
* Integrity fields: cryptographic hashes, block sequence numbers, manifests

Blocks are appended and never rewritten. Derived artifacts are rebuildable from evidence.

#### Tamper-Evident Log

A rolling integrity ledger maintains:

* A hash chain over evidence blocks
* Periodic checkpoint manifests
* Optional external anchoring (e.g., periodic signed checkpoints)

This supports proof that:

* the evidence was not altered after ingestion
* a given finding came from a specific snapshot
* re-running with the same snapshot yields the same result

---

### Knowledge Representation

#### Canonical Schema

The system uses a small set of primitives:

* **Entities**: users, hosts, processes, files, keys, services, sessions, addresses
* **Events**: authentication, process spawn, file write, network connection, admin change
* **Relations**: “spawned”, “wrote”, “connected-to”, “belongs-to”, “used-key”, “derived-from”
* **Attributes**: time, location, confidence, labels, source references

#### Knowledge Graph

The graph is a continuously updated structure where:

* nodes are stable entities and artifacts
* edges are evidence-backed relationships with timestamps and weights
* subgraphs can be extracted deterministically for any scope window

The graph supports:

* shortest-path queries (“how did this host connect to that credential?”)
* neighborhood queries (“everything linked to this API key”)
* temporal slicing (“links that appeared after this deployment”)
* anomaly scoring over graph motifs

---

### Reasoning and Detection

#### Rule-Based Semantic Layer

A declarative rule engine expresses “meaning” patterns such as:

* suspicious authentication chains
* privilege escalation sequences
* credential access patterns
* unusual service-to-service call flows
* policy violations and forbidden transitions

Rules compile into deterministic query plans that operate on normalized events and graph edges.

#### Statistical and Similarity Layer

For large corpora, the system computes:

* approximate set similarities (documents, binaries, code)
* clustering over behavior signatures and artifact fingerprints
* outlier detection on event rates, sequences, and graph motifs
* compressed summaries suitable for AI consumption

This layer produces scores and cluster assignments that are always backed by evidence pointers and reproducible parameters.

---

### AI Integration Model

#### The Device as an “AI Tool”

AI agents call the device via a structured API. The device returns:

* verified facts
* graphs/timelines
* ranked hypotheses and counterexamples
* receipts and replay instructions

The AI agent uses the box to:

* ask high-level questions and receive grounded results
* generate narratives from verified structures
* plan next investigative steps based on what is known and unknown

#### Example AI Queries

* “Build the incident timeline for user U across all sources from T1 to T2.”
* “Show the causal chain linking this phishing email to this database export.”
* “Cluster all binaries similar to this sample; identify shared lineage and first-seen.”
* “Which hosts share the same credential use pattern as host H in the last 30 days?”
* “List all policy violations involving privileged role grants with weak MFA signals.”
* “Provide evidence-backed reasons why hypothesis A is weaker than hypothesis B.”

#### Returned Output Shapes

* **Timeline bundle**: ordered events, grouped by entity, with cross-links
* **Graph bundle**: nodes, edges, weights, timestamps, evidence references
* **Finding bundle**: claim statements + supporting evidence pointers + replay plan
* **Cluster bundle**: cluster IDs, exemplars, similarity stats, evidence pointers

Each bundle includes:

* snapshot identifiers and integrity hashes
* rule set version and compilation hash
* deterministic query plan signature

---

### Operational Workflow

#### Ingestion Phase

* Choose sources and define scope
* Import and seal evidence snapshot
* Build indexes and initial graph

#### Investigation Phase

* Run semantic rules and similarity jobs
* Ask targeted questions through the AI agent
* Refine hypotheses with additional searches and counterexample queries

#### Reporting Phase

* Produce a case file: timeline + graph + findings + receipts
* Export replay instructions for third-party verification
* Generate an executive narrative that links to specific evidence items

---

### Performance Philosophy

The system is built to be fast where it matters:

* bulk parsing and normalization
* cryptographic hashing and integrity sealing
* similarity search and clustering over massive corpora
* deterministic graph extraction and pattern matching

It is built to be dependable where it must be:

* strict provenance
* repeatability and deterministic replay
* explicit separation of evidence and derived artifacts
* stable identifiers for entities across sources

---

### Security and Isolation

* Per-tenant or per-case compartmentalization of evidence snapshots
* Access control over raw evidence vs derived artifacts vs claims
* Cryptographic sealing of case exports
* Optional air-gapped operation for high-sensitivity environments

---

### Outputs and Artifacts

#### Case Artifact

A portable, verifiable “case bundle” contains:

* snapshot manifest(s) and integrity ledger
* derived indexes (optional) or rebuild recipe
* findings with evidence references
* replay scripts/plans to regenerate timelines and graphs

#### Continuous Monitoring Mode

When used as an appliance in a live environment:

* incremental ingestion and sealing
* rolling window timelines and graphs
* alert generation with receipts
* AI-assisted triage with strict grounding and provenance
