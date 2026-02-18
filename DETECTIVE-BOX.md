# Cryptographic Detective Box — Implementation on Chimera-1

## 1. System Identity

The Cryptographic Detective Box is a local, high-throughput evidence and
reasoning appliance.  It runs on the Chimera-1 unified SoC (MP64 + LM-1)
under the KDOS kernel with Lispos services.

```
┌──────────────────────────────────────────────────────────────────┐
│                   Cryptographic Detective Box                     │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Operator Interface (KDOS TUI + API)                         │  │
│  └──────────┬──────────────────────────────────────────────────┘  │
│             │                                                      │
│  ┌──────────▼──────────────────────────────────────────────────┐  │
│  │ Investigation Engine                                         │  │
│  │                                                               │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│  │  │ Ingest   │→ │ Normalize│→ │ Index    │→ │ Seal       │  │  │
│  │  │ (MP64)   │  │ (MP64)   │  │ (MP64+   │  │ (MP64      │  │  │
│  │  │          │  │          │  │  LM-1)   │  │  SHA3+CRC) │  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │  │
│  │                                                               │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│  │  │ Graph    │  │ Rules    │  │ Similar  │  │ Report     │  │  │
│  │  │ Engine   │  │ Engine   │  │ Engine   │  │ Generator  │  │  │
│  │  │ (LM-1)  │  │ (LM-1)  │  │ (MP64    │  │ (KDOS +    │  │  │
│  │  │          │  │          │  │  SIMD)   │  │  LM-1)     │  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Evidence Store (KDOS — append-only, hash-chained)           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │ DRAM (DDR5)  │  │ NVMe Storage │  │ Network (100GbE)     │    │
│  │ 32–128 GiB   │  │ Case Files   │  │ Evidence Ingestion   │    │
│  └──────────────┘  └──────────────┘  └──────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Hardware ↔ IDEA.md Mapping

Every capability described in IDEA.md maps to a specific hardware
component of the Chimera-1 SoC:

### 2.1 Data Ingestion

| IDEA.md Requirement | Hardware Component | Implementation |
|---------------------|-------------------|----------------|
| Pull from connectors or offline import | 100GbE NIC + NVMe via PCIe | KDOS data ports (`PORT!`, `POLL`, `INGEST`) |
| Snapshot metadata | MP64 timer + SysInfo | Timestamp + source ID captured at port level |
| Parse into canonical schema | MP64 full cores | KDOS kernel pipeline: parser stage |
| Resolve timestamps/ordering | MP64 cores | KDOS kernel: time normalization |

**KDOS Pipeline Definition:**

```forth
6 PIPELINE ingest-pipe
' acquire      ingest-pipe P.ADD    \ Stage 1: read from data port
' normalize    ingest-pipe P.ADD    \ Stage 2: parse to canonical schema
' resolve-id   ingest-pipe P.ADD    \ Stage 3: identity resolution
' fingerprint  ingest-pipe P.ADD    \ Stage 4: crypto fingerprinting
' index-update ingest-pipe P.ADD    \ Stage 5: update indexes
' evidence-seal ingest-pipe P.ADD   \ Stage 6: seal evidence block
```

### 2.2 Identity Resolution

| IDEA.md Requirement | Hardware Component | Implementation |
|---------------------|-------------------|----------------|
| Map aliases to stable IDs | LM-1 tiles (graph lookup) | Lisp actor: `identity-resolver` |
| Correlate hosts across DHCP, certs, HW IDs | LM-1 knowledge graph | Graph query: find connected identities |

Identity resolution runs as an actor on LM-1.  During ingestion, KDOS
sends a `WORK_REQ` to the identity-resolver actor with the entity's
attributes.  The actor queries the knowledge graph, returns a stable ID
or creates a new one.

### 2.3 Content Fingerprinting

| IDEA.md Requirement | Hardware | Implementation |
|---------------------|----------|----------------|
| Cryptographic digests | SHA-3 accelerator | `SHA3-INIT / SHA3-UPDATE / SHA3-FINAL` |
| CRC checksums | CRC accelerator | `CRC-RESET / CRC-FEED / CRC-RESULT` |
| Locality-sensitive fingerprints | SIMD tile engine | MinHash/SimHash via MEX tile ops |
| Structural features (shingles) | MP64 cores + SIMD | Shingle extraction in Forth, hashing via tile engine |

**Crypto fingerprinting kernel:**

```forth
: fingerprint ( evidence-buf -- )
    \ Step 1: Strong hash (SHA-3-256)
    DUP B.DATA OVER B.BYTES SHA3-256    \ result in SHA3 output register

    \ Step 2: CRC-32 for fast dedup
    DUP B.DATA OVER B.BYTES CRC-DMA    \ result in CRC register

    \ Step 3: SimHash via tile engine (LSH for similarity search)
    DUP simhash-tile-kernel             \ dispatches to SIMD tile engine
;
1 0 2 1 KERNEL fingerprint-desc        \ 1 in, 0 out, 2-tile footprint, tile-accel
```

### 2.4 Evidence Store

| IDEA.md Requirement | Hardware | Implementation |
|---------------------|----------|----------------|
| Immutable blocks with hashes | DRAM + SHA-3 | KDOS evidence-store library |
| Block sequence numbers | MP64 core (counter) | Monotonic evidence counter |
| Append-only, never rewritten | DRAM allocator (write-once region) | `EVIDENCE-SEAL` marks region read-only |
| Hash chain | SHA-3 accelerator | Each block includes hash of previous block |
| Periodic checkpoints | NVMe disk | `EVIDENCE-CHECKPOINT` flushes to disk |

**Evidence block layout in DRAM:**

```
Offset  Size    Field
  0      32     sha3_hash          (SHA-3-256 of this block's payload)
 32      32     prev_hash          (SHA-3-256 of previous block — chain link)
 64       8     sequence_number    (monotonic counter)
 72       8     timestamp          (MP64 timer cycles)
 80       8     source_id          (data port / import ID)
 88       8     payload_length     (bytes of actual content)
 96       8     schema_version     (canonical schema version)
104       8     flags              (sealed, verified, exported, ...)
112      16     reserved
128       *     payload            (normalized records, raw bytes, or chunk ref)
```

**Integrity verification:**

```forth
: EVIDENCE-VERIFY ( idx -- flag )
    DUP evidence-block@            \ get block address
    DUP 128 +                      \ payload start
    OVER 88 + @                    \ payload length
    SHA3-256                       \ compute hash
    SWAP 0 + 32 COMPARE            \ compare with stored sha3_hash
    0= IF
        \ Also verify chain link
        DUP 32 + 32                \ prev_hash from this block
        OVER 1- evidence-block@    \ previous block
        0 + 32 COMPARE             \ compare with previous block's hash
        0=
    ELSE FALSE THEN ;
```

### 2.5 Knowledge Graph

| IDEA.md Requirement | Hardware | Implementation |
|---------------------|----------|----------------|
| Nodes = entities and artifacts | LM-1 tile SRAM + DRAM | Lisp objects: `(make-entity :type :user :id "U42")` |
| Edges = evidence-backed relationships | LM-1 tile SRAM + DRAM | Lisp objects: `(make-edge src dst :type :spawned :evidence-ref 1234)` |
| Shortest-path queries | LM-1 tiles (parallel BFS) | Actor-parallel graph traversal across tiles |
| Neighborhood queries | LM-1 tile-local SRAM | Each tile holds a graph partition; local scan + cross-tile messages |
| Temporal slicing | LM-1 graph query engine | Filter edges by timestamp range |
| Anomaly scoring | LM-1 + MP64 SIMD | Graph motif counting in Lisp, vector scoring via SIMD dispatch |

**Graph Engine Architecture (Lispos):**

```lisp
;; Core graph primitives
(defstruct entity
  id type attributes evidence-refs)

(defstruct edge
  source target type weight timestamp evidence-ref)

(defstruct graph
  entities         ;; hash-table: id → entity
  adjacency        ;; hash-table: id → list of edges
  temporal-index)  ;; sorted by timestamp for slicing

;; Query API (called from KDOS via cross-domain message)
(defun query-path (graph from-id to-id &key max-depth)
  "BFS shortest path between two entities.")

(defun query-neighborhood (graph entity-id &key depth time-range)
  "Return subgraph within N hops of entity, optionally time-filtered.")

(defun query-timeline (graph entity-id t1 t2)
  "All edges involving entity between timestamps t1 and t2.")

(defun score-anomalies (graph pattern-set)
  "Score all subgraph motifs matching patterns, return ranked list.")
```

**Parallelism:** The graph is partitioned across LM-1 tiles by entity ID
hash.  Each tile owns a partition of the adjacency structure in its 256 KiB
SRAM (hot subgraph) with overflow to cluster shared SRAM and DRAM.

Parallel BFS: each tile explores its local partition.  Cross-partition
edges generate `SEND` messages to the owning tile.  The actor model
naturally handles this — each graph partition is an actor.

### 2.6 Rule-Based Semantic Layer

| IDEA.md Requirement | Hardware | Implementation |
|---------------------|----------|----------------|
| Declarative rule engine | LM-1 tiles | Lisp DSL compiled to graph query plans |
| Suspicious auth chains | LM-1 graph query | Pattern: path of auth events with anomalous timing |
| Privilege escalation sequences | LM-1 graph query | Pattern: role-grant edges followed by admin-action edges |
| Policy violations | LM-1 rule matcher | Set of forbidden transition patterns |
| Deterministic query plans | LM-1 compiler | Rules compile to fixed query DAGs |

**Rule DSL (Lisp):**

```lisp
(defrule suspicious-lateral-movement
  :description "User authenticates to >3 hosts within 5 minutes"
  :pattern
    (match-sequence
      (auth-event ?user ?host1 ?t1)
      (auth-event ?user ?host2 ?t2 :where (< (- ?t2 ?t1) 300))
      (auth-event ?user ?host3 ?t3 :where (< (- ?t3 ?t1) 300))
      :constraint (distinct ?host1 ?host2 ?host3))
  :action
    (create-finding :type :lateral-movement
                    :entities (?user ?host1 ?host2 ?host3)
                    :evidence (?t1-event ?t2-event ?t3-event)
                    :severity :high))
```

Rules compile to graph traversal plans.  The compiler runs on LM-1 and
produces actor programs that execute the traversal in parallel.

### 2.7 Statistical and Similarity Layer

| IDEA.md Requirement | Hardware | Implementation |
|---------------------|----------|----------------|
| Approximate set similarities | MP64 SIMD tile engine | MinHash over 64-byte tiles: `TELEMENT`, `TMIN`, `TMUL` |
| Clustering | MP64 SIMD + LM-1 | Distance matrix via SIMD, cluster assignment in Lisp |
| Outlier detection | MP64 SIMD | Statistical kernel: `krms`, `kstats`, `kpeak`, `kavg` |
| Compressed summaries | MP64 buffers | KDOS buffer descriptors with summary statistics |

**Similarity search pipeline:**

```forth
\ MinHash fingerprint computation (SIMD tile engine)
: minhash ( doc-buf -- hash-buf )
    \ Shingle extraction into tile buffer
    DUP shingle-extract              \ produce shingle set as tile data
    \ N hash functions via tile multiply + accumulate
    128 0 DO
        hash-seeds I CELLS + @       \ load hash seed
        TSRC1!                       \ broadcast to tile
        TMUL                         \ multiply all shingles by seed
        TEMIN                        \ find minimum (= MinHash for this function)
        ACC@ minhash-buf I 8 * + !   \ store result
    LOOP
    minhash-buf ;

\ Jaccard similarity estimate
: jaccard ( hash-a hash-b -- similarity )
    0 128 0 DO                       \ count matching minhash values
        OVER I 8 * + @
        OVER I 8 * + @
        = IF 1+ THEN
    LOOP
    NIP NIP
    128 */                           \ matches / total
;
```

### 2.8 AI Integration (API Layer)

| IDEA.md Requirement | Hardware | Implementation |
|---------------------|----------|----------------|
| Structured API | 100GbE NIC | KDOS network stack: JSON-envelope over TLS 1.3 |
| Verified facts | Evidence store | Every response includes evidence block refs |
| Graphs/timelines | LM-1 graph engine | Query result serialized to JSON |
| Replay instructions | Evidence store | Query plan hash + snapshot ID |

**API dispatch (KDOS):**

```forth
: api-dispatch ( request-buf -- response-buf )
    DUP api-parse-type                  \ determine query type
    CASE
        API-TIMELINE OF
            DUP api-extract-params      \ get entity, T1, T2
            S" (query-timeline graph entity t1 t2)" LM1-EVAL
            api-format-timeline-response
        ENDOF
        API-PATH OF
            DUP api-extract-params
            S" (query-path graph from to)" LM1-EVAL
            api-format-path-response
        ENDOF
        API-SIMILAR OF
            DUP api-extract-sample
            minhash                     \ SIMD fingerprint
            similarity-search           \ scan index
            api-format-cluster-response
        ENDOF
        API-RULE-RUN OF
            DUP api-extract-rule
            S" (run-rule rule-name)" LM1-EVAL
            api-format-finding-response
        ENDOF
    ENDCASE
    \ Attach evidence receipts to every response
    DUP attach-evidence-receipts ;
```

**Response envelope:**

```json
{
  "type": "timeline_bundle",
  "snapshot_id": "sha3:abc123...",
  "rule_set_version": "v2.1.0",
  "query_plan_hash": "sha3:def456...",
  "events": [...],
  "evidence_refs": ["block:1234", "block:1235", ...],
  "replay_instructions": {
    "snapshot": "sha3:abc123...",
    "query": "(query-timeline graph \"U42\" 1700000000 1700003600)",
    "deterministic": true
  }
}
```

---

## 3. End-to-End Pipeline Walkthrough

### 3.1 Incident Response Scenario

**Setup:** An operator suspects lateral movement from a phishing email.

```
Step 1: Ingest Evidence
─────────────────────────────────────────
  Operator → KDOS:
    > S" /case/phish-2024/" MKFILE
    > sensor-buf 1 PORT!             \ bind NIC source 1
    > ingest-pipe P.RUN              \ run 6-stage ingest pipeline

  Hardware flow:
    NIC → MP64 Core 0 (parse/normalize)
    → MP64 Core 1 (identity resolution via LM1-SEND)
    → SHA-3 accel (fingerprint)
    → SIMD tile engine (SimHash)
    → DRAM evidence store (seal)

  Result: 50,000 evidence blocks sealed in DRAM


Step 2: Build Knowledge Graph
─────────────────────────────────────────
  KDOS → Lispos (via cross-domain message):
    > S" (build-graph-from-evidence evidence-store)" LM1-EVAL

  LM-1 tiles:
    256 tiles partition the evidence blocks
    Each tile builds local subgraph from its partition
    Cross-tile entity merging via actor messages
    Graph stored across tile SRAMs + DRAM overflow

  Result: Knowledge graph with ~200K entities, ~1.2M edges


Step 3: Run Detection Rules
─────────────────────────────────────────
  KDOS → Lispos:
    > S" (run-ruleset incident-response-rules)" LM1-EVAL

  LM-1 tiles:
    Rule compiler generates graph traversal actors
    Actors fan out across tiles
    Each finding includes evidence block references

  Result: 47 findings, 3 high-severity


Step 4: Investigate Findings
─────────────────────────────────────────
  Operator (or AI agent via API):
    > S" (query-path graph phish-email-id db-export-id)" LM1-EVAL

  Result: Causal chain:
    phishing-email → user-U42 → host-H7 → lateral-move → host-H12
    → privilege-escalation → admin-session → database-export
    (each edge backed by evidence block refs)


Step 5: Generate Report
─────────────────────────────────────────
  KDOS:
    > report-pipe P.RUN

  Pipeline:
    1. Extract timeline from graph (LM-1)
    2. Gather evidence receipts (KDOS evidence store)
    3. Compute integrity manifest (SHA-3 over all referenced blocks)
    4. Generate case bundle (KDOS buffer → NVMe)

  Result: Case file with:
    - 50,000 sealed evidence blocks
    - Knowledge graph export (JSON)
    - 47 findings with evidence chains
    - Integrity manifest (hash tree)
    - Replay instructions
```

---

## 4. Performance Budget

### 4.1 Ingestion Throughput

| Stage | Hardware | Throughput Target |
|-------|----------|------------------|
| Network receive | 100GbE NIC | 12.5 GB/s wire speed |
| Parse/normalize | 4 MP64 cores | ~2 GB/s (conservative) |
| SHA-3 hash | SHA-3 accelerator | ~10 GB/s (dedicated DMA path) |
| SimHash (LSH) | SIMD tile engine (512-bit) | ~4 GB/s |
| Evidence seal | DRAM controller | ~51.2 GB/s (not bottleneck) |
| **Pipeline bottleneck** | **Parse/normalize** | **~2 GB/s** |

At ~2 GB/s sustained ingestion, a 1 TB corpus is ingested in ~8 minutes.

### 4.2 Graph Operations

| Operation | Hardware | Latency Target |
|-----------|----------|---------------|
| Point query (neighborhood) | 1 LM-1 tile | < 10 µs |
| BFS (depth 3, ~10K nodes) | 8 LM-1 tiles (1 cluster) | < 1 ms |
| Full rule scan (200K entities) | 128+ LM-1 tiles | < 10 s |
| Timeline extraction | 1–4 LM-1 tiles | < 100 ms |

### 4.3 Crypto Operations

| Operation | Hardware | Throughput |
|-----------|----------|-----------|
| SHA-3-256 | SHA-3 accelerator with DMA | ~10 GB/s |
| AES-256-GCM encrypt | AES accelerator | ~5 GB/s |
| CRC-32 | CRC accelerator with DMA | ~20 GB/s |
| Random bytes | TRNG | ~100 MB/s |
| KEM keygen | KEM accelerator | ~1000 ops/s |
| NTT (polynomial multiply) | NTT accelerator | ~500M coefficients/s |

---

## 5. Security Architecture

### 5.1 Case Compartmentalization

Each investigation case gets:

* A dedicated DRAM region (allocated by `DRAM-ALLOT`)
* A separate evidence chain (independent hash chains)
* Isolated graph partition on LM-1 (actor group with capability tokens)

The MP64 SRAM bank affinity CSR can pin case data to specific banks,
preventing cross-case data leakage through shared caches (there are no
caches — SRAM is directly addressed).

### 5.2 Evidence Integrity

* Evidence blocks in DRAM are marked write-once by the DRAM controller
  (the address region is locked after seal).
* Hash chains are verified periodically by a background KDOS task.
* Checkpoint manifests are written to NVMe and optionally signed
  with the KEM accelerator (post-quantum signatures).

### 5.3 Crypto Transport

* All API communication over TLS 1.3 (KDOS TLS stack, existing).
* Post-quantum key exchange via KEM accelerator (ML-KEM / Kyber).
* Evidence exports are AES-256-GCM encrypted with case-specific keys.

### 5.4 Air-Gap Mode

The NIC can be disabled via KDOS:

```forth
: AIR-GAP ( -- )
    0 NET-TX-EN!        \ disable transmit
    0 NET-RX-EN!        \ disable receive
    ." Network isolated." CR ;
```

In air-gap mode, evidence is imported via NVMe (removable media) and
exported the same way.

---

## 6. KDOS Dashboard Extensions

### 6.1 New Screens

| Screen | Purpose |
|--------|---------|
| S8: Evidence | Evidence chain status: block count, chain integrity, storage used |
| S9: LM-1 | LM-1 subsystem: tile count, actor count, GC stats, graph size |

### 6.2 New Forth Words (Detective Box Vocabulary)

```
--- EVIDENCE ---
  EVIDENCE-SEAL  ( buf -- )         Seal buffer as evidence block
  EVIDENCE-VERIFY ( idx -- f )      Verify block integrity
  EVIDENCE-CHAIN ( -- addr n )      Chain head + length
  EVIDENCE-STATS ( -- )             Print chain statistics
  EVIDENCE-EXPORT ( case -- )       Export case to NVMe

--- GRAPH (via LM-1) ---
  GRAPH-ADD-ENTITY ( type id -- )   Add entity to knowledge graph
  GRAPH-ADD-EDGE ( src dst type -- ) Add relationship edge
  GRAPH-QUERY ( query-str len -- )  Send graph query to LM-1
  GRAPH-PATH ( from to -- )         Find shortest path
  GRAPH-TIMELINE ( entity t1 t2 -- ) Extract timeline

--- RULES ---
  RULE-LOAD ( name len -- )         Load rule set from disk
  RULE-RUN ( name len -- )          Execute rule set on current graph
  RULE-LIST ( -- )                  List loaded rule sets
  FINDINGS ( -- )                   Display current findings

--- CASE MANAGEMENT ---
  CASE-NEW ( name len -- )          Create new investigation case
  CASE-OPEN ( name len -- )         Open existing case
  CASE-CLOSE ( -- )                 Close current case
  CASE-EXPORT ( -- )                Export case bundle to NVMe
  CASE-VERIFY ( -- )                Verify full case integrity
```

---

## 7. Implementation Phases

| Phase | Milestone | Components | Depends On |
|-------|-----------|-----------|-----------|
| DB-1 | Evidence ingestion pipeline | KDOS pipeline + SHA-3 + CRC + DRAM store | OS-5 |
| DB-2 | Single-source timeline | Parse logs → normalize → seal → display | DB-1 |
| DB-3 | Identity resolution | LM-1 actor for entity merging | OS-7 |
| DB-4 | Knowledge graph (single tile) | Lisp graph engine, basic queries | OS-6 |
| DB-5 | Knowledge graph (multi-tile) | Partitioned graph, parallel BFS | OS-8 |
| DB-6 | Rule engine | Lisp DSL, rule compiler, pattern matching | DB-5 |
| DB-7 | Similarity engine | MinHash via SIMD, clustering in Lisp | DB-5 |
| DB-8 | API layer | TLS 1.3 JSON API, evidence receipts | DB-6 + DB-7 |
| DB-9 | Case management | Case isolation, export, verification | DB-8 |
| DB-10 | AI integration | Agent query protocol, hypothesis engine | DB-9 |

---

## 8. Bill of Materials Summary

| Component | Source | Status |
|-----------|--------|--------|
| MP64 cores + µ-clusters | megapad RTL | ✅ Done (25K lines) |
| KDOS kernel | megapad kdos.f | ✅ Done (8,300 lines) |
| KDOS crypto bindings | megapad kdos.f | ✅ Done |
| KDOS network + TLS 1.3 | megapad kdos.f | ✅ Done |
| KDOS pipeline engine | megapad kdos.f | ✅ Done |
| KDOS dashboard/TUI | megapad kdos.f | ✅ Done |
| AES-256-GCM accelerator | megapad RTL | ✅ Done |
| SHA-3/SHAKE accelerator | megapad RTL | ✅ Done |
| CRC accelerator | megapad RTL | ✅ Done |
| TRNG | megapad RTL | ✅ Done |
| NTT + KEM accelerators | megapad RTL | ✅ Done |
| SIMD tile engine (512-bit) | megapad RTL | ✅ Done |
| LM-1 tile RTL | New (from LM-1 specs) | ❌ To build |
| LM-1 cluster + NoC | New (from LM-1 specs) | ❌ To build |
| Unified DRAM controller | New | ❌ To build |
| Bridge unit (MP64 ↔ LM-1) | New | ❌ To build |
| KDOS extensions (~800 lines) | New Forth | ❌ To build |
| Lispos runtime | New Lisp (from design docs) | ❌ To build |
| Knowledge graph engine | New Lisp | ❌ To build |
| Rule compiler | New Lisp | ❌ To build |
| Evidence store library | New Forth | ❌ To build |
| API layer | New Forth + Lisp | ❌ To build |

**Reuse ratio:** Of the Chimera-1 Detective Box, approximately 60% of the
software stack (by line count) and 40% of the hardware (by module count)
already exist in the megapad repository.  The major new work is LM-1 RTL,
the bridge, and the Lisp-side intelligence engines.
