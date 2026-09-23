# CG-001 — Assistant and graph architecture investigation

**Scope:** Static inspection of the checked-out CodeGraph application on 2026-09-23. No application code or database data was changed. Runtime behavior that depends on a live Neo4j, model response, or browser session is identified as an inference from source, not an observed integration run.

## Executive finding

The assistant and graph share the `App` React component and the active `owner/repository` string, but they have no entity-level communication. Chat sends the current prompt and repository to a JSON FastAPI endpoint; its Markdown response has no graph references. React Flow loads a separate graph response whose node IDs are Neo4j `elementId` values. Those IDs work for the current graph and source-code request, but are not durable across deletion and re-ingestion. More seriously, ingestion merges functions on **repository + simple name**, collapsing same named functions across files and within a file. Reliable assistant-to-graph navigation requires fixing graph identity and agent tool outputs before adding clickable UI references.

## 1. Current architecture and data flow

```text
GitHub URL
  -> App.submitRepository -> api.ingestRepository -> POST /api/ingest-repo
  -> download -> Tree-sitter parse -> repository-relative file paths
  -> Neo4j Repository / File / Function / Community nodes and relationships
  -> NDJSON progress -> activeRepo -> GET /api/graph
  -> serialize Neo4j elementIds -> normalizeGraph -> D3 force layout
  -> React Flow nodes and edges

Chat textarea -> App.sendMessage -> api.requestChat -> POST /api/chat
  -> LangGraph ReAct agent -> repository-scoped Neo4j tool queries
  -> Claude Markdown answer -> JSON {response, metrics}
  -> App.messages -> ReactMarkdown

Graph node click -> selectedNodeId -> CodePanel
  -> GET /api/node/{elementId}/code?repo_name=...
  -> Neo4j raw_code -> syntax-highlighted source
```

### Frontend

| Concern | Location and behavior |
| --- | --- |
| Composition/state | [`frontend/src/App.jsx`](frontend/src/App.jsx), lines 585–613: one component owns `nodes`, `edges`, `focusedNodeId`, `selectedNodeId`, `messages`, `activeRepo`, ingestion state, cluster state, and the React Flow instance ref. No external store/context/router is used; [`frontend/src/main.jsx`](frontend/src/main.jsx), lines 1–10, mounts `App` directly. Shared parent state exists, but no chat-to-node action exists. |
| Conversation | [`frontend/src/App.jsx`](frontend/src/App.jsx), lines 51–58, 547–583, 1191–1252: local starter message, chat history, Markdown via `ReactMarkdown` + GFM, input, send/stop controls. Message objects carry `id`, `role`, `content` only. |
| Chat request/rendering | [`frontend/src/api.js`](frontend/src/api.js), lines 166–188, posts `{message, repo_name}`. [`frontend/src/App.jsx`](frontend/src/App.jsx), lines 971–1062, appends user and empty assistant messages, reads JSON `response`, and updates the assistant message. It contains an SSE parser for a possible non-JSON response, but **the current `/api/chat` returns JSON**, so token-by-token streaming is not active. The JSON `metrics` field is ignored. |
| Repository lifecycle | [`frontend/src/App.jsx`](frontend/src/App.jsx), lines 878–969, resets graph/chat on ingest or delete, sets `activeRepo` from final ingestion progress, then loads graph. Refresh button calls `loadGraph(activeRepo)` (lines 1350–1358). [`frontend/src/api.js`](frontend/src/api.js), lines 26–107, parses NDJSON ingestion progress and requests a scoped graph. |
| Graph conversion/layout | [`frontend/src/App.jsx`](frontend/src/App.jsx), lines 143–515: `normalizeNodes`/`normalizeEdges`, D3 force layout, nearest directional handles, initial center based on highest-degree non-external node. Backend grid positions are overwritten. `File` nodes become `fileHub`; functions become `graphNode`. |
| Graph interactions | [`frontend/src/App.jsx`](frontend/src/App.jsx), lines 638–806 and 1402–1458: hover sets `focusedNodeId`; adjacency highlights both incoming and outgoing neighbors/edges without distinguishing direction. Cluster selection dims nodes/edges but does not remove them (lines 698–788). Click on a Function sets `selectedNodeId` to its React Flow ID, opening `CodePanel`. GraphControls uses `fitView` on expansion (lines 100–140). React Flow instance `setCenter` centers the initial graph (lines 835–851). |
| Details/source | [`frontend/src/components/CodePanel.tsx`](frontend/src/components/CodePanel.tsx), lines 49–105, 143–193: fetches source on `{nodeId, repoName}`, handles cancellation, shows file path/name and syntax-highlighted raw code. [`frontend/src/api.js`](frontend/src/api.js), lines 110–133, requests the scoped source endpoint. |
| Modules/communities | [`frontend/src/utils/communities.js`](frontend/src/utils/communities.js), lines 13–46, builds legend from node community metadata; [`frontend/src/components/GraphLegend.tsx`](frontend/src/components/GraphLegend.tsx), lines 18–175, toggles community filters. The UI calls file hubs “Module hub”; it does not render `Community` nodes. |

The graph section is `hidden ... lg:block` ([`App.jsx`](frontend/src/App.jsx), line 1255), so a chat-to-graph navigation feature also needs a small-screen presentation decision. Chat and graph are fetched independently; changing `messages` does not change graph focus, and graph interaction does not provide entity context to `/api/chat`.

### Backend and ingestion

| Concern | Location and behavior |
| --- | --- |
| API/repository scope | [`backend/app/main.py`](backend/app/main.py), lines 72–150, validates `owner/repository`; lines 202–239 expose `GET /api/graph`; lines 241–291 expose scoped function source; lines 342–360 expose `POST /api/chat`. |
| Full ingest | [`backend/app/main.py`](backend/app/main.py), lines 369–458, downloads and parses supported source files, converts paths to repository-relative POSIX paths (lines 169–181), replaces existing repository graph, and emits NDJSON progress. [`backend/app/services/parser_service.py`](backend/app/services/parser_service.py), lines 20–28 and 369–438, parses Python, JS/TS, Go, and Java into simple function names, raw code, classes, and a **file-wide** call-name list. |
| Neo4j writes | [`backend/app/db/graph_ops.py`](backend/app/db/graph_ops.py), lines 17–89 and 123–200, creates `Repository`, `File`, `Function`/`ExternalFunction`, `Community` and `CONTAINS`, `DEFINES`, `CALLS`, `IN_COMMUNITY`. It groups parsed functions by `(file_path, name)` only temporarily, then merges persisted functions by `(repo_name, name)`. Calls are joined by simple name. |
| Clusters | [`backend/app/db/gds_ops.py`](backend/app/db/gds_ops.py), lines 12–44, writes Leiden IDs on Function nodes; [`backend/app/services/community_summarizer.py`](backend/app/services/community_summarizer.py), lines 24–49 and 110–168, stores labeled `Community` nodes. Community IDs describe a clustering run, not durable module identity. |
| Graph response | [`backend/app/db/__init__.py`](backend/app/db/__init__.py), lines 12–32 and 88–210, fetches repo-scoped File/Function nodes and `DEFINES`/`CALLS` edges, serializes node and relationship `element_id`, removes raw code and embeddings, includes community and file metadata. `GRAPH_QUERY` has `LIMIT 200` on result records, without pagination or a stable order. |
| Code response | [`backend/app/db/__init__.py`](backend/app/db/__init__.py), lines 34–41 and 213–232, finds Function by both `repo_name` and `elementId(function)`, then returns `{code,file_path,name}`. |
| Alternate ingest | [`backend/app/api/webhooks.py`](backend/app/api/webhooks.py), lines 18–61, schedules [`backend/app/services/pipeline.py`](backend/app/services/pipeline.py), lines 111–235, for GitHub events. It calls the same save path without `replace_existing=True`, so entity-key changes must cover both full and incremental ingest. Its LangGraph step is currently a placeholder. |
| Indexes | [`backend/app/db/neo4j_client.py`](backend/app/db/neo4j_client.py), lines 20–39: lookup indexes include `(repo_name,path)` for File and `(repo_name,name)` for Function. These are indexes, **not uniqueness constraints**. |

The backend also has root-level [`agent.py`](agent.py) and [`database.py`](database.py), an older CLI/Python graph path. The running frontend calls `backend/app/main.py` and `backend/app/agent/graph.py`; the root-level agent is not the assistant API pipeline.

## 2. Entity identity and relationship accuracy

| Entity | Current identity and payload | Reliability |
| --- | --- | --- |
| Repository | `repo_name` string, validated as `owner/repository`; `Repository` node merged on it. | Scopes current requests. The validator does not case-fold or include a commit/revision, so case and version semantics are unspecified. |
| File | Neo4j merge key `(repo_name, path)`, where full ingest uses repository-relative POSIX path. Graph node `id` is `elementId`; `data.path`/`data.file_path` carry path. | Path is a usable logical key for unchanged file location; `elementId` is ephemeral. |
| Function | Neo4j merge key **`(repo_name, name)`**; `file_path` is a mutable property and `file` is set only when absent. The parser stores simple names and raw source, not qualified scope, signature, or persisted source span. | **Not sufficient.** Same named functions in separate files merge. Same named methods, nested functions, and overloads can merge. `DEFINES` may connect several files to one node; `file_path` and `raw_code` can reflect the last processed definition while `file` can reflect the first. |
| Unresolved/external call | `Function` created from `(repo_name, target_name)` and later tagged `ExternalFunction` when no `DEFINES` edge exists. | A name only; can conflate different packages or call sites, and a same-named internal definition may absorb an external call. |
| Call relationship | `CALLS` between name-matched Function nodes, with `inferred_from_file_scope=true` and `source_files` list. [`graph_ops.py`](backend/app/db/graph_ops.py), lines 173–198, attaches **every file-wide outgoing call name to every function in that file**. | Direction is stored, but caller-to-call-site attribution is approximate and name resolution is ambiguous. A dependency view must label these edges as inferred until parser/resolution changes. |
| Community/module | Function `leiden_community` integer, plus `Community` node keyed by `(repo_name, community_id)` with generated title/description. File nodes are rendered as “module hubs.” | Cluster numbers and labels can change after re-ingest; there is no stable source module identity beyond a file path. |
| React Flow node/edge | [`db/__init__.py`](backend/app/db/__init__.py), lines 95 and 141–163, emits Neo4j `element_id` as `id`; [`App.jsx`](frontend/src/App.jsx), lines 276–347, stringifies it as React Flow `id` and edge endpoints. | Exact identity within a loaded Neo4j graph; unsafe for stored links across delete/re-ingest. Fallback index IDs in frontend would be unstable if a backend ID were missing. |

**Duplicate-name example:** `src/a.py::run` and `src/b.py::run` are two parsed records but both target `MERGE (fn:Function {name:'run', repo_name:'owner/repo'})`. They become one node, not two selectable functions. Even a future reference containing `repo_name + file_path + name` cannot map reliably until the database schema and call resolution preserve that distinction.

**Across transformations:** Hover and cluster filters preserve node IDs because they copy/style the existing node array. A simple graph refresh from unchanged Neo4j data should preserve `elementId` for existing nodes, but the code provides no identity guarantee if data is rewritten. Full ingestion uses `replace_existing=True` ([`main.py`](backend/app/main.py), lines 441–445), deletes repo nodes, and recreates them, so old `elementId` links and source requests become stale. Backend startup deletes all repository graphs ([`main.py`](backend/app/main.py), lines 59–69), while the browser attempts deletion on unload ([`App.jsx`](frontend/src/App.jsx), lines 861–872). Thus neither graph nor chat survives a normal refresh as an application feature. `GRAPH_QUERY LIMIT 200` can omit an otherwise valid entity from the current viewport; absence from React Flow cannot be treated as nonexistence in Neo4j.

## 3. Complete assistant response pipeline

1. `App.sendMessage` sends only the latest prompt and `activeRepo`; it does not send conversation history, selected node, graph snapshot, or interaction state ([`App.jsx`](frontend/src/App.jsx), lines 971–999; [`api.js`](frontend/src/api.js), lines 166–183).
2. `POST /api/chat` validates scope, calls `ask_code_agent_with_metrics`, and returns only `{response, metrics}` ([`main.py`](backend/app/main.py), lines 342–360). There is no response-model field for references, tool trace, conversation ID, or structured message parts.
3. [`backend/app/agent/graph.py`](backend/app/agent/graph.py), lines 335–352, creates a cached Claude `ChatAnthropic` LangGraph ReAct agent with seven tools. The model chooses tools from a repository-scoped system prompt, and LangGraph executes them. `_run_code_agent` calls `ainvoke` with a fresh system/user message pair on each request (lines 384–415); no checkpointer or prior messages are supplied.
4. Tool queries and formatting are in [`backend/app/agent/graph.py`](backend/app/agent/graph.py), lines 21–82 and 103–332. Blast radius returns JSON with name, caller names, file-path arrays, and external flag. Structure returns path lines; functions in file returns name lines; outgoing dependencies returns name/file lines; external dependencies returns names; semantic search returns name/path/score lines; architectural subsystems returns community ID/title/description/count JSON. **None returns a stable Function or File entity key or Neo4j elementId.** Several use simple function-name inputs and can be ambiguous even before formatting.
5. The final model message is reduced to plain text by `_message_text`; tool messages are joined only to count context tokens for metrics ([`graph.py`](backend/app/agent/graph.py), lines 355–467). Tool outputs and any potential model/tool metadata are not included in the API response. Assistant output is instructed to use Markdown; the frontend renders it as generic Markdown, with no entity-aware component mapping.
6. Chat history is React state only. The server receives one prompt per request, does not persist messages, and the frontend reconstructs only the starter message after reload ([`App.jsx`](frontend/src/App.jsx), lines 51–58 and 594–599). Ingest replaces the visible history; delete resets it.

**Structured references are feasible but not present.** LangGraph already returns the execution message trace to `_run_code_agent`, and some tools already produce JSON. A backend change can emit typed entity references from authoritative tool results, let the answer cite opaque reference IDs, validate every cited ID against the tool trace, and return the validated references as a separate JSON field. A prompt asking the model to write function names as Markdown links by itself would still be ungrounded and ambiguous.

## 4. Existing interaction capability and reuse

| Capability | Current implementation | Reuse boundary |
| --- | --- | --- |
| Programmatic select/focus | `focusedNodeId` and `selectedNodeId` are writable state in `App`; React Flow receives controlled nodes. Hover currently changes focus, click changes `selectedNodeId` for functions. | Add one navigation action that resolves a stable entity key, sets a persistent focus/selection, and optionally opens code. Keep hover focus separate so mouse leave does not erase assistant navigation. Native `selected` node state is not currently coordinated with these IDs. |
| Center viewport | `flowInstanceRef.current.setCenter(...)` on initial load, `fitView(...)` on resize, React Flow Controls/MiniMap ([`App.jsx`](frontend/src/App.jsx), lines 100–140, 835–851, 1402–1448). | Reuse `setCenter` with resolved node position plus dimensions; wait for graph load/layout and container readiness. |
| Highlight neighbors/edges | `adjacencyIndex` and `visibleNodes`/`visibleEdges` ([`App.jsx`](frontend/src/App.jsx), lines 638–788). | Reuse styling pipeline, but maintain separate inbound/outbound edge sets using `edge.source`/`edge.target`. Current focus is undirected and dims non-neighbors; it does not filter them out. |
| Filter dependencies | No true function dependency subgraph/filter. Cluster selection dims unrelated nodes; hover dims non-neighbors. | Add explicit dependency mode using stable keys/edge direction and distinguish direct from transitive scope. |
| Details/source | Function click opens `CodePanel`; scoped source API uses `elementId` ([`App.jsx`](frontend/src/App.jsx), lines 801–806, 1454–1458; [`CodePanel.tsx`](frontend/src/components/CodePanel.tsx), lines 58–89). | Reuse panel UI and lazy loading; migrate source lookup to a stable function key or resolve the current `elementId` just before opening. |
| Backend metadata | Serialized `node.data` retains most Neo4j properties, including `repo_name`, `name`, `file_path`/`path`, external flag, and community metadata; raw code and embeddings are deliberately removed ([`db/__init__.py`](backend/app/db/__init__.py), lines 88–138). | Build a lookup map over base `nodes`, not styled copies; add explicit `entity_ref` rather than inferring from label. |

## 5. Architectural limits to address

1. **Identity corruption is the first blocker.** Function merge and call lookup by simple name mean duplicate names are neither distinct in Neo4j nor the UI. Parser output lacks lexical scope and signature/source-span data needed for overloads and nested definitions. Do not claim `repo + path + name` is universally unique.
2. **Current IDs are storage handles.** Neo4j `elementId` matches React Flow ID and source lookup today, but is not an application-level, re-ingest-stable key. Indexes do not enforce proposed uniqueness.
3. **Agent results cannot be resolved precisely.** Tools return display text or name-only JSON. The API strips the tool trace and exposes no structured references. Text matching would mis-link duplicate names and references absent from the capped graph.
4. **Graph coverage is incomplete.** The 200-record query limit has no pagination/targeted fetch; an entity may exist in Neo4j but not in `nodes`. External Functions without a `DEFINES` edge may not appear unless reached as an `m` from a visible node. Community nodes and `CONTAINS`/`IN_COMMUNITY` edges are not rendered.
5. **State and lifecycle are ephemeral.** Assistant history and selected entity are in memory. Full ingest replaces the graph; startup/unload cleanup removes graphs. Refresh or re-ingest needs explicit stale-reference handling, and optional persistence must be designed deliberately.
6. **Interaction state has competing meanings.** Hover focus, code-panel selection, cluster dimming, and native React Flow selection are not a single navigation state. Hover leave currently clears focus. Cluster filters can visually suppress the node a chat reference targets.
7. **Call data is approximate.** Current parser collects calls per file, and ingestion connects each file function to every collected target name. A dependency filter built on existing edges should disclose that provenance or first improve call-site resolution.

## 6. Recommended integration architecture and data contract

### Durable identity model

Introduce a versioned, typed `EntityRef` as the shared contract. Make `entity_id` a deterministic application key stored on Neo4j entities and included in graph/tool/chat responses. Never use display `name`, cluster number, or Neo4j `elementId` as the cross-panel identity. Keep `elementId` as an optional current-snapshot storage handle while migrating source requests.

```json
{
  "schema_version": 1,
  "repo_name": "owner/repository",
  "kind": "function",
  "entity_id": "fn:v1:<deterministic-hash-of-canonical-key>",
  "file_path": "src/payments.py",
  "symbol": "PaymentService.charge",
  "discriminator": "(self, amount: Decimal)",
  "display_name": "charge",
  "source_range": { "start_line": 42, "end_line": 58 },
  "snapshot_id": "<ingestion-generation-or-commit>"
}
```

**Canonical-key rules:**

- Function key: repository + normalized repository-relative file path + language + lexical qualified symbol + a definition discriminator. The discriminator must distinguish overloads and repeated definitions in one scope; normalized signature is preferable where available, with a documented source-position/occurrence fallback. Persist both the canonical fields and `entity_id`; define one shared backend encoder/validator and a database uniqueness constraint for `(repo_name, entity_id)`. A source line is useful for display and fallback resolution but should not be the sole long-lived identity: edits can shift it. A rename, move, or signature change may intentionally produce a new key; `snapshot_id` lets the UI detect stale references.
- File key: repository + normalized relative path. A file has no `symbol` or `discriminator`. A source-language package/module can receive its own kind later if the parser actually models one.
- Community key: repository + snapshot/cluster-run + community ID. Treat this as a snapshot-scoped grouping, not a durable module reference. `display_name` is never a key.
- External/unresolved call: represent as an explicitly unresolved reference with call-site/namespace information and resolution status. Do not pretend that a bare target name identifies a unique function.
- Relationship: `kind` such as `CALLS` or `DEFINES`, typed `source_entity_id` and `target_entity_id`, repository/snapshot, and provenance (`resolved` versus `inferred_file_scope`, call-site range if known). Deterministic edge identity can be derived from those fields when needed.

`schema_version`, `repo_name`, `kind`, and `entity_id` are required. The other fields aid display, validation, and stale-link handling. The backend must validate that `entity_id` resolves to exactly one entity in the requested repository/snapshot; `file_path` and `symbol` are explicit evidence, not trusted client selectors. On missing or ambiguous resolution, return a typed status and candidate refs rather than picking the first name match.

### Graph and chat API shape

Add `entity_ref` to each graph node while preserving the present `id` temporarily for React Flow and source-panel compatibility. Build `Map<entity_id, flowNodeId>` from the loaded graph. For complete coverage, add either paginated graph loading or a focused `GET /api/entities/{entity_id}/neighborhood?repo_name=...` that can insert a missing target and its edges into the view. Resolve navigation by `entity_ref` and confirm `repo_name`/`snapshot_id` before focusing. A stable `entity_id` could eventually become the React Flow node ID, but that is a separate migration.

Extend chat JSON compatibly:

```json
{
  "response": "## Call path\nThe payment handler calls the validator.",
  "references": [
    {
      "ref_id": "r1",
      "entity": { "schema_version": 1, "repo_name": "owner/repository", "kind": "function", "entity_id": "fn:v1:...", "file_path": "src/payments.py", "symbol": "PaymentService.charge", "discriminator": "(self, amount: Decimal)", "display_name": "charge", "snapshot_id": "..." },
      "role": "subject"
    }
  ],
  "metrics": { "full_repo_tokens": 0, "context_tokens": 0, "tokens_saved": 0, "efficiency_percentage": 0 }
}
```

Tool responses should carry the exact same `EntityRef` objects for subjects and result entities. The agent may cite `ref_id`s in its answer or supply structured answer parts; the backend should accept only references present in actual tool results and matching the request scope. The frontend can first render validated references as chips/cards adjacent to Markdown, avoiding fragile regex over prose. If inline links are required, use explicit reference tokens or structured spans, never match human-readable names. Retain the current JSON response path; the frontend SSE branch is only a parser stub and a future stream needs a defined event contract, including a final references event.

### State/navigation behavior

Keep repository, graph data, selected reference, and navigation intent in the common `App` owner initially; no global store is needed yet. Implement a single `navigateToEntity(ref, options)` action: validate current repository/snapshot; resolve `entity_id` in a map; fetch a focused neighborhood if absent; clear or override incompatible cluster dimming; set persistent selection; center via React Flow instance; optionally open source for a Function. Hover remains a temporary overlay. Base the details panel on `EntityRef` or a resolved current storage handle. On graph refresh, rebuild the map and re-resolve selection; on re-ingest/repository switch, invalidate stale selections and chat references. If conversation persistence is later required, persist chat with repository and snapshot metadata and avoid deleting its graph on browser unload/startup.

## 7. Implementation recommendations for CG-002 through CG-006

The repository contains no specifications for these ticket IDs. The assignments below are a proposed dependency sequence, not a claim about their official titles or scope.

| Ticket | Recommended scope | Acceptance checks |
| --- | --- | --- |
| **CG-002** | Fix parser/Neo4j identity and call attribution. Capture qualified lexical names, signature or occurrence discriminator, source range, repository-relative path; persist deterministic `entity_id`; replace name-only MERGE/MATCH and add uniqueness constraints/migration. Update full and webhook ingest. | Two same-named functions in different files and two same-named methods/overloads in one file remain distinct; `DEFINES`, `CALLS`, source code, and agent queries resolve the intended node. Explicitly mark unresolved calls. |
| **CG-003** | Expose typed `EntityRef` in graph, entity/source lookup, and agent tool results. Validate repo/snapshot. Add focused entity/neighborhood endpoint or pagination to bypass the 200-record cap. | Graph and tool response for one function contain the same `entity_id`; missing, stale, and ambiguous refs have explicit outcomes; re-ingest preserves a logical key for unchanged definitions while storage `elementId` can change. |
| **CG-004** | Return structured assistant references from grounded tool results alongside Markdown/metrics. Define reference IDs and optional inline spans; keep JSON compatibility or design a complete SSE contract if streaming is desired. | Each returned reference is traceable to a tool result and current repo/snapshot; no name-string matching; multiple same-named functions produce separate refs. Conversation-history support, if desired, has an explicit persistence/checkpoint design. |
| **CG-005** | Build frontend resolver and navigation action: reference chip/link -> entity lookup -> React Flow focus/center -> source panel. Separate hover from persistent selection; handle load, cluster dimming, repository change, small screens, missing graph nodes. | Click selects exactly one function even with duplicate display names; focus survives hover leave and graph refresh; stale or absent refs show a clear recovery path. |
| **CG-006** | Add directional dependency exploration and polish: incoming/outgoing edge styling and optional subgraph, relation provenance, tests across cross-panel paths and re-ingest/refresh. | Direction and direct/transitive scope are accurate; inferred file-scope calls are labeled; filters do not silently hide a navigated target; duplicate-name, large-graph, and stale-reference flows pass. |

The ordering matters: CG-005 cannot make duplicate-name navigation reliable until CG-002/003 preserve and expose distinct function identities. If the official CG-002–CG-006 scopes differ, retain these technical dependencies while assigning the work.

## Investigation verification

All conclusions above were derived from the checked-out source and cited code paths. No production code was edited, no repository was ingested, and no live Neo4j/model/browser integration test was run. Static review is sufficient to establish the current contracts and identity failure; downstream tickets should add focused tests and run an end-to-end duplicate-name fixture against a disposable graph.
