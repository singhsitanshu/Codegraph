# CG-002B: graph identity and migration handoff

## Legacy migration

The old writer merged `Function` by `(repo_name, name)`, attached a `DEFINES` edge from every file with that name, copied every file-wide `outgoing_calls` name to every function in the file, and merged named call targets as `Function` nodes. Duplicate names could collapse definitions, source, ownership, and edges. Stored legacy nodes have insufficient data to reverse that collapse. **Do not backfill `entity_id` from a legacy node's name or path.**

Full ingest calls `save_parsed_ast_to_neo4j_with_progress(..., replace_existing=True)`. It deletes only nodes with that repository's `repo_name`, then recreates the graph from parsed source. This is the migration path. Incremental writes require `Repository.graph_state='ready'` and reject legacy Function nodes missing `entity_id`. Failed builds remain `building` and need a full rebuild. The graph API only reads `ready` repositories.

## Persisted contract

| Entity | Identity | Stored data and links |
| --- | --- | --- |
| `Repository` | `repo_name` | `graph_state`, `graph_updated_at`, full source token baseline |
| `File` | `(repo_name, path)` | normalized repository-relative path, `Repository-[:CONTAINS]->File` |
| `Function` | `(repo_name, entity_id)` | display `name`, `qualified_name`, `file_path` and compatibility `file`, `language`, `signature`, `definition_discriminator`, source line/column, `has_body`, `raw_code`, `embedding`; `File-[:DEFINES]->Function` |
| `CALLS` edge | caller ID, target ID, `call_id` | written name/syntax, source location, `resolution_status='inferred'`, provenance |
| `UnresolvedCall:ExternalFunction` | `(repo_name, call_id)` | written name/syntax, source location, caller ID if known, `resolution_status` and provenance; caller Function or File `-[:HAS_UNRESOLVED_CALL]->` call site |

The `ExternalFunction` label is retained for older graph consumers; it does **not** establish that a call is external. `UnresolvedCall` has no `Function` label. `call_id` is `call:v1:` plus compact JSON of source path, caller ID, and call coordinates. It identifies a syntactic occurrence, not a callee. Database initialization creates composite uniqueness constraints for `(repo_name, entity_id)` on Function and `(repo_name, call_id)` on UnresolvedCall. The `(repo_name, name)` index remains a search index, not identity. No simple-name fallback exists.

The writer validates every parser ID with the **same** CG-002A utility, rejecting missing/mismatched IDs, wrong repository/path, and conflicting records. It persists TypeScript declaration-only overloads as individual Function nodes (`has_body=false`) but excludes them as executable call targets. Repeated writes `MERGE` by ID. Body-only edits preserve IDs; moves, signature changes, and some repeated-definition reorderings change IDs.

## Call evidence and resolution

`functions[].calls` identifies the enclosing caller; `unattributed_calls` remains linked to File. File-wide `outgoing_calls` is compatibility data only. An unqualified call is linked to exactly one same-file immediate nested definition or exactly one same-file top-level body. Such a link is explicitly **inferred** (`lexical_nested` or `same_file_top_level` provenance): parsing does not prove runtime binding. Repeated definitions, overloads, cross-file imports, receiver-qualified/dynamic calls, and unknown bindings remain separate ambiguous or unresolved call-site nodes. They never create an arbitrary `CALLS` edge. An unresolved name may refer to an internal, external, standard-library, or dynamic target.

## Ingestion and limits

Full GitHub ingest relativizes extracted paths, attaches IDs, and replaces the repository graph. Local helpers do likewise. The webhook pipeline accepts only bounded non-forced push events with explicit added/modified/removed lists. It fetches changed files at the event's immutable `after` SHA, attaches IDs, and passes deleted paths to the writer. A fetch or parse failure aborts before any database write; incomplete events are skipped and logged. Incremental persistence removes affected Functions, UnresolvedCalls, and Files, including obsolete call edges, before recreating changed files. Partial file token counts do not overwrite the full repository baseline.

**Operational limits:** The stored full graph has no Git source revision. A webhook cannot prove its `before` revision matches the graph, so out-of-order or concurrent events can apply an older change set. The `building`/`ready` marker hides an incomplete single build but is not a cross-process transaction or revision lock. Production incremental sequencing needs a stored revision, compare-and-set on `before`/`after`, and repository-scoped write serialization. Run a full rebuild after a missed or out-of-order event. Full rebuild recreates Neo4j element IDs. Graph output currently has a 200-row limit; large graphs need pagination or complete traversal.

The existing FastAPI lifespan in `app/main.py` deletes all repository-scoped graphs on startup. CG-002B leaves that lifecycle unchanged; deployments that restart must re-ingest repositories. Reconsider this policy alongside durable graph revisions in a separate lifecycle change.

## Existing feature compatibility

The graph API still serializes Neo4j `elementId` as React Flow node `id` and edge endpoints; Function `data.entity_id` now carries the application identity. The source endpoint still looks up `elementId(function)` within the selected repository and returns that exact node's source/path/name, with no name fallback. Graph, source, and agent reads require a ready repository. The graph includes `CALLS` and `HAS_UNRESOLVED_CALL`. Community detection and GDS still operate on repository-scoped Function/CALLS nodes, and embeddings remain on Functions. Agent file/structure tools operate on the new graph. Name-based blast-radius and outgoing-dependency tools now report ambiguity when multiple function IDs match, rather than combine callers or dependencies. The unresolved-call tool displays uncertainty rather than claiming every call is external.

## CG-003 handoff

- Use `{repo_name, entity_id}` for stable assistant/graph function references. Add a graph revision before persisting references across rebuilds. Add entity-ID source lookup; keep elementId compatibility until React Flow migrates.
- Replace name-only agent inputs for unique-function operations with an entity reference. Return structured candidate references, paths, qualified names, locations, and resolution status. Never parse assistant prose to reconstruct IDs.
- `UnresolvedCall` and `HAS_UNRESOLVED_CALL` need a distinct visual treatment. Expose `CALLS.resolution_status` and `CALLS.provenance` when explaining dependency confidence.
- Keep name search for candidate discovery, but require disambiguation before navigation. Treat `has_body=false` TypeScript declarations separately from implementations.
- Address pagination, revision-aware webhook sequencing, and stronger language-specific binding analysis in follow-up work.

## Verification

Pure and mocked tests cover duplicate names, classes, Java/TypeScript overloads, repeated definitions, call attribution, ambiguity, unresolved calls, full/incremental query ordering, legacy rejection, source endpoint compatibility, and agent ambiguity. `tests/test_graph_identity_integration.py` starts a uniquely named disposable Neo4j Docker container **only** when a daemon is available; Docker may pull `neo4j:5.26`. It verifies real constraints, persisted definitions, `DEFINES`/`CALLS`, unresolved nodes, graph serialization, source lookup, repeated writes, incremental removal, and full replacement. It never connects to configured developer Neo4j. If skipped, database behavior remains unverified in that environment.
