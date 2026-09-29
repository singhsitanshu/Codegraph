# Parts 29–32 — Decision defense and active recall

[Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](03_QUESTION_BANK.md) · [Next](05_MOCK_INTERVIEWS.md)

## Contents

- [29. Engineering decision defense](#29-engineering-decision-defense)
- [Graph storage](#graph-storage)
- [Syntax parsing](#syntax-parsing)
- [Canonical parser identity](#canonical-parser-identity)
- [Bounded tasks and micro-batches](#bounded-tasks-and-micro-batches)
- [Agentic tool selection](#agentic-tool-selection)
- [Metadata vectors](#metadata-vectors)
- [Leiden and generated labels](#leiden-and-generated-labels)
- [Streaming and separate source lookup](#streaming-and-separate-source-lookup)
- [30. Resume claim defense cards](#30-resume-claim-defense-cards)
- [31. Guided source reading: 25 targets](#31-guided-source-reading-25-targets)
- [Fourteen execution traces](#fourteen-execution-traces)
- [32. Active-recall learning system](#32-active-recall-learning-system)
- [The 50 facts to recall without notes](#the-50-facts-to-recall-without-notes)
- [Glossary tied to CodeGraph](#glossary-tied-to-codegraph)
- [Exercises — attempt before opening the key](#exercises--attempt-before-opening-the-key)
- [Separate answer key](#separate-answer-key)

---

## 29. Engineering decision defense

The following are defensible explanations of the current design. Where history does not establish intent, say “this approach is useful because…” rather than “I considered every alternative and chose…”. The [comparative matrix](02_APPLICATION_AND_AUDIT.md#26-architectural-trade-off-matrix) covers performance, reliability and maintenance trade-offs; these scripts turn that analysis into interview speech.

### Graph storage

**Problem/requirements:** answer relationship questions and support visualization, vectors and community algorithms from one indexed repository representation. **Choice/evidence:** Neo4j async queries, vector index and GDS (`db/__init__.py`, `neo4j_client.py`, `gds_ops.py`). **Rationale:** keeping graph and enrichment together reduces application-side joins between independent stores. **Cost:** a service/plugin/version dependency and an identity schema that must be designed carefully. **Alternative/exit condition:** PostgreSQL can handle direct calls with joins and recursive CTEs; prefer it if transactional tenancy dominates and graph algorithms add little evaluated value. **Say:** “Neo4j fits the relationship-oriented interface and integrated GDS/vector workflow. It is not necessary merely because the data has edges, and I would revisit it based on measured query and operational needs.”

### Syntax parsing

**Problem/requirements:** extract useful structure without building or executing arbitrary repositories, across several languages. **Choice/evidence:** grammar wheels and queries in `parser_service.py`. **Rationale:** syntax-aware spans support source extraction and named definitions better than broad regex. **Cost:** no compiler-level symbols/types; query coverage and grammar compatibility require tests. **Alternative/exit condition:** LSP/compiler integration when precise resolution matters more than language-agnostic simplicity. **Say:** “Tree-sitter gives syntax evidence, not runtime dispatch. HEAD improves lexical ownership, but persistence still needs migration.”

### Canonical parser identity

**Problem/requirements:** distinguish same names, lexical scopes and overloads while avoiding IDs tied only to moving line numbers. **Choice/evidence:** SHA-256 over canonical fields, `entity_identity.py:37`; occurrence fallback in `parser_service.py:508`. **Rationale:** deterministic keys survive body-only edits and encode known distinctions. **Cost:** moves/signature changes and repeated-definition ordering can change IDs; hashes do not solve unresolved semantics. **Alternative/exit condition:** compiler symbol IDs or richer revision-aware identity matching if cross-refactor continuity becomes a requirement. **Say:** “I would migrate storage and consumers together and include snapshot identity; the new parser ID is not yet an exposed durable graph key.”

### Bounded tasks and micro-batches

**Problem/requirements:** overlap reads without unbounded active work, and avoid enormous database transactions. **Choice/evidence:** 32-slot semaphore and per-language locks; 100-record ETL batches. **Rationale:** responsive event loop and finite write units. **Cost:** all tasks/results still allocated, same-language serialization, visible partial commits. **Alternative/exit condition:** a fixed worker queue/process pool for measured CPU bottlenecks; snapshot publication for reliability. **Say:** “The bounds are implementation facts, not a 32x speed claim or a total-memory guarantee.”

### Agentic tool selection

**Problem/requirements:** support diverse repository questions without a single fixed retrieval order. **Choice/evidence:** cached prebuilt ReAct graph with seven tools in `agent/graph.py:335`. **Rationale:** reuse orchestration and allow different evidence sequences. **Cost:** wrong tools, variable rounds, framework defaults and unsupported final claims. **Alternative/exit condition:** deterministic routes for exact requests, direct retrieval+generation for predictable tasks, custom loop for strict control. **Say:** “An agent is useful for exploration; exact caller queries do not intrinsically need one.”

### Metadata vectors

**Problem/requirements:** suggest functions when users know intent but not names. **Choice/evidence:** name/path embedding template, OpenAI vector service and cosine index. **Rationale:** small inputs and straightforward integration. **Cost:** names can hide behavior; no result cache; external service dependency and global top-k post-filter. **Alternative/exit condition:** lexical hybrid or code-aware/local embeddings if quality/privacy evidence supports them. **Say:** “I would compare candidate recall before increasing input size or changing the model.”

### Leiden and generated labels

**Problem/requirements:** give a high-level overview beyond a dense function map. **Choice/evidence:** undirected Function/CALLS projection, Leiden property write, sampled metadata labels. **Rationale:** connectivity groups can provide exploratory organizing units. **Cost:** graph errors propagate, direction lost, labels sampled/generated, no demonstrated retrieval gain. **Alternative/exit condition:** components/traversal/ranking if the actual user question is connectivity or local relevance. **Say:** “These are generated interpretations of graph communities, not validated software modules.”

### Streaming and separate source lookup

**Problem/requirements:** show progress during long ingestion and keep graph payload small. **Choice/evidence:** NDJSON generator/reader and separate source endpoint (`main.py:370`, `api.js:32`, `db/__init__.py:34`). **Rationale:** simple POST-compatible progress plus lazy code transfer. **Cost:** stream success semantics are custom, no resumable job ID, source IDs can become stale. **Alternative/exit condition:** persisted polling/SSE jobs or bidirectional channel if needed. **Say:** “Transport framing solves incremental delivery, while durable execution and snapshot identity require separate designs.”

## 30. Resume claim defense cards

Each card gives the technical meaning, implementation evidence, qualification, concise phrasing, deeper explanation and the likely challenge. Historical numerical achievements need their own artifacts; do not manufacture results from code structure.

| Claim | Meaning and evidence | Concise interview wording | Deep defense, challenge and qualification |
|---|---|---|---|
| Full-stack application | React UI connects to active FastAPI graph/source/chat/ingestion/deletion APIs; `App.jsx`, `api.js`, `main.py` | “Built a repository exploration UI and API spanning ingestion, visualization and AI questions.” | Trace NDJSON→activeRepo→graph load and node click→source. Challenge: do chat and graph share entity links? They share scope only; no validated references/navigation. |
| FastAPI | Pydantic requests, async handlers, StreamingResponse, dependency-based HMAC, lifespan | “Implemented typed repository APIs and streamed ingestion progress.” | Explain 422 before stream versus error records after HTTP 200. Challenge: production-ready? No auth/durable jobs; startup deletes data. |
| React/React Flow | Custom nodes, directed edges, D3 layout, legend, source drawer | “Created an interactive function graph with source inspection and cluster emphasis.” | Explain controlled arrays, 300 ticks, degree sizing and hover adjacency. Challenge: large-graph scale? Capped rows, no pagination, dimming is not pruning. |
| GitHub ingestion | Fixed API zipball URL/default branch, optional token, safe extraction and suffix discovery | “Implemented default-branch GitHub archive ingestion.” | Explain path checks/temporary ownership. Challenge: arbitrary branches/private repositories? No branch field; private access depends on server token and is not per-user authorization. |
| Tree-sitter | Seven suffixes, definition/call captures, raw code and lexical metadata | “Extracted syntax-level function metadata across Python, JS/TS, Go and Java.” | Distinguish CST/semantic analysis and grammar coverage. Challenge: polymorphism/imports? Unresolved; no import model. |
| Parallel ingestion | 32-slot async semaphore with thread offload and per-language locks | “Added bounded file processing with completion-based progress.” | Explain default executor and serialized grammar reuse. Challenge: 32x speedup? No benchmark; no such guarantee. |
| Graph construction | Three passes, 100-record batches, scoped MERGEs and provenance | “Implemented batched repository-scoped graph persistence.” | Explain transaction order and partial state. Challenge: accurate call graph? File-wide approximation and name collisions remain. |
| Neo4j | Property graph, ordinary indexes, vector index, fixed Cypher tools | “Integrated Neo4j for graph queries, semantic candidates and GDS.” | Explain no uniqueness constraints and scope versus ACL. Challenge: why not SQL? Direct traversals are feasible in SQL; integrated graph features are the rationale. |
| LangGraph | Prebuilt ReAct compiled/cached, async invocation | “Orchestrated model tool calls over repository data.” | Trace messages→tool calls→ToolMessages→model. Challenge: memory/budgets? No persistent history or explicit product spend policy. |
| ReAct | Model chooses actions based on prior observations | “Enabled adaptive multi-tool exploration.” | Explain potential wrong-tool recovery and failure propagation. Challenge: necessary for every request? No; deterministic exact routes could be simpler. |
| Seven tools | Exact registration list at `graph.py:343` | “Registered seven graph-analysis/retrieval tools.” | Name all seven. Challenge: source tool/transitive impact? Neither exists; browser source endpoint is separate and blast radius is direct callers. |
| Vector embeddings | `text-embedding-3-small`, shape 1536, name/path inputs, cosine index | “Added metadata-based semantic function search.” | Explain response ordering and global top-k post-filter. Challenge: code understanding? Bodies not embedded; ANN/relevance unbenchmarked. |
| Leiden Graph-RAG | Ingestion-time topology clusters + generated labels + architecture tool | “Added Leiden-based architectural grouping for graph exploration and agent summaries.” | Explain unweighted undirected projection and sampling. Challenge: query-specific subgraph? Not implemented; no ablation establishes quality improvement. |
| Context reduction | tiktoken baseline versus concatenated tool text | “Implemented per-answer selected-context accounting.” | Explain exclusions, zero/no-tool and negative cases. Challenge: 97.5% guarantee? Unsupported by stored benchmark artifacts; exact supplied arithmetic 97.56%. |
| HMAC-SHA256 | Raw body digest with shared secret, compare_digest, 401 rejection | “Verified webhook body authenticity with HMAC-SHA256.” | Explain signed bytes before JSON parsing. Challenge: replay? No freshness/delivery dedup; body authenticity is not user/repository authorization. |
| API testing | Mocked TestClient and optional live graph integration cases | “Tested request contracts, graph scoping and failure behavior.” | Explain mock versus integration assertions. Challenge: live current verification? Four DB cases were skipped in this audit. |
| Postman automation | Collection v2.1, 23 requests, 7-step workflow, dynamic values and 6 HMAC cases | “Created a chained repository API workflow and negative/security contract checks.” | Explain NDJSON error semantics, source capture, metrics arithmetic and cleanup. Challenge: AI quality/CI? Neither is established by these scripts; no live run here. |
| Pytest suite | 96 current active cases, 19 new identity cases | “Current offline audit passed 92 cases, with four database integrations skipped.” | Differentiate historical README 77 passes and supplied 82 claim. Challenge: test quality? Name actual assertions and gaps instead of relying on count. |
| Parser identity foundation | deterministic keys, scopes, ranges and lexical call ownership, HEAD | “Added a tested parser contract preparing a graph-identity migration.” | Explain body-only stability and overload handling. Challenge: available in UI? Not yet persisted/exposed; avoid claiming completed assistant navigation. |

## 31. Guided source reading: 25 targets

Read in this order. The output column identifies actual data shapes; the last column combines important errors, trust and performance implications. “Study question” refers to the bank.

| # / source and symbols | Why, input → output | Side effects/dependencies and critical considerations |
|---|---|---|
| 1. `backend/app/config.py:9` Settings | Establish active configuration; env/defaults → settings object | Reads backend env; no active ANTHROPIC_MODEL/NEO4J_DATABASE option. Never display secrets. [Q129](03_QUESTION_BANK.md#q129-which-models-serve-which-roles)/[Q152](03_QUESTION_BANK.md#q152-how-would-you-handle-secrets-and-dependency-security-before-deployment). |
| 2. `backend/app/main.py:126` normalizers | Understand scope; URL/name → owner/repo | ValueError→422; broad regex/case preservation; no branch. [Q049](03_QUESTION_BANK.md#q049-how-is-a-repository-url-validated), [Q050](03_QUESTION_BANK.md#q050-how-does-codegraph-choose-a-branch). |
| 3. `backend/app/services/github_service.py:29` headers/download | Network input boundary; owner/repo → temp root | Optional token, redirects, full response bytes, 60s timeout, HTTP errors. [Q051](03_QUESTION_BANK.md#q051-what-happens-with-a-private-repository)/054. |
| 4. `github_service.py:38/106` extraction/cleanup | Understand file safety and ownership; ZIP→files | Containment check, no size quotas, temp registry cleanup. [Q052](03_QUESTION_BANK.md#q052-how-is-archive-path-traversal-prevented). |
| 5. `main.py:154` discovery | Determine indexed corpus; root→sorted paths | Disk walk, fixed excludes/suffixes, no .gitignore or file caps. [Q053](03_QUESTION_BANK.md#q053-which-files-are-discovered-and-counted). |
| 6. `parser_service.py:25–163` grammar/query constants | Learn exact language constructs; syntax→captures | No imports or callee binding; seven suffixes. [Q042](03_QUESTION_BANK.md#q042-which-languages-are-actually-supported), [Q043](03_QUESTION_BANK.md#q043-how-does-codegraph-distinguish-a-call-from-a-function-reference), [Q044](03_QUESTION_BANK.md#q044-can-tree-sitter-resolve-polymorphic-method-calls). |
| 7. `parser_service.py:214` CodeParser init | Understand reusable state; grammar wheels→parsers/queries/locks | Compiles all grammars per instance; missing package breaks imports. [Q057](03_QUESTION_BANK.md#q057-is-codegraph-really-parsing-32-files-simultaneously). |
| 8. `parser_service.py:387/464` lexical definitions | Learn identity fields; CST→records | Parameter syntax/occurrences, source spans; Python capture work. [Q045](03_QUESTION_BANK.md#q045-how-are-nested-and-anonymous-calls-attributed), [Q046](03_QUESTION_BANK.md#q046-how-are-overloads-represented), [Q047](03_QUESTION_BANK.md#q047-how-are-function-ids-generated-and-what-remains-unstable). |
| 9. `parser_service.py:519` calls | Trace owner and uncertainty; calls→owned/unattributed | Candidate scan O(C×F), anonymous boundary checks, unresolved targets. [Q045](03_QUESTION_BANK.md#q045-how-are-nested-and-anonymous-calls-attributed)/[Q198](03_QUESTION_BANK.md#q198-a-function-returns-a-callback-that-calls-save-is-outer-shown-as-calling-save). |
| 10. `entity_identity.py:16/37` key helpers | Understand stable keys; canonical fields→fn:v1 hash | Invalid relative paths rejected; no persistence/snapshot. [Q047](03_QUESTION_BANK.md#q047-how-are-function-ids-generated-and-what-remains-unstable)/[Q071](03_QUESTION_BANK.md#q071-are-neo4j-element-ids-durable-application-identifiers). |
| 11. `parser_service.py:737` batch parser | Work scheduling; paths→progress records | Threads, 32 semaphore, grammar locks, all tasks/results, isolated errors. [Q057](03_QUESTION_BANK.md#q057-is-codegraph-really-parsing-32-files-simultaneously), [Q058](03_QUESTION_BANK.md#q058-how-does-the-gil-affect-this-pipeline), [Q059](03_QUESTION_BANK.md#q059-does-the-semaphore-provide-full-backpressure), [Q060](03_QUESTION_BANK.md#q060-what-happens-if-the-concurrency-limit-increases-to-1000), [Q061](03_QUESTION_BANK.md#q061-how-is-deterministic-result-ordering-retained), [Q062](03_QUESTION_BANK.md#q062-what-is-the-worst-local-parsing-complexity-concern), [Q063](03_QUESTION_BANK.md#q063-why-batch-database-writes-by-100-records), [Q064](03_QUESTION_BANK.md#q064-what-does-cancellation-actually-stop). |
| 12. `main.py:376` ingestion generator | Connect orchestration; owner/repo→NDJSON | Writes DB/calls providers, finally temp cleanup, non-atomic failure. [Q025](03_QUESTION_BANK.md#q025-why-can-ingestion-return-http-200-when-it-failed)/194. |
| 13. `graph_ops.py:123` flattening/template | See fidelity gap; parsed→file/function/call rows | Drops IDs/lexical calls, dedup, Cartesian attribution, metadata embeddings. [Q003](03_QUESTION_BANK.md#q003-why-represent-code-as-a-graph-when-imports-already-exist)/[Q066](03_QUESTION_BANK.md#q066-how-does-the-current-function-key-fail)/[Q179](03_QUESTION_BANK.md#q179-what-historical-trade-off-appeared-in-the-batching-refactor). |
| 14. `graph_ops.py:238` writer/deletes | Transaction boundaries; rows→graph | 100 batches, scoped replacement, provider/GDS/labels required; partial state. [Q063](03_QUESTION_BANK.md#q063-why-batch-database-writes-by-100-records)/187. |
| 15. `neo4j_client.py:26/55/82` schema/client | Indexes/lifecycle; config→sync driver/indexes | Import connectivity; no uniqueness; await indexes up to 300s. [Q023](03_QUESTION_BANK.md#q023-what-are-the-consequences-of-importing-neo4j_client)/[Q068](03_QUESTION_BANK.md#q068-what-uniqueness-constraints-exist). |
| 16. `embedding_service.py:27` batch embeddings | Provider contract; strings→ordered vectors | OpenAI API, validation and no result cache; [Q097](03_QUESTION_BANK.md#q097-what-exactly-does-codegraph-embed), [Q098](03_QUESTION_BANK.md#q098-which-embedding-model-and-dimensions-are-used), [Q099](03_QUESTION_BANK.md#q099-how-is-cosine-similarity-relevant), [Q100](03_QUESTION_BANK.md#q100-why-use-approximate-rather-than-exhaustive-nearest-neighbor-search), [Q101](03_QUESTION_BANK.md#q101-how-does-the-embedding-service-preserve-batch-order), [Q102](03_QUESTION_BANK.md#q102-are-embeddings-reused-across-queries-or-ingestions), [Q103](03_QUESTION_BANK.md#q103-can-structurally-related-code-be-semantically-dissimilar), [Q104](03_QUESTION_BANK.md#q104-what-happens-when-semantic-retrieval-returns-nothing). |
| 17. `gds_ops.py:53` clustering | Projection semantics; graph→community IDs | DB memory, unweighted/undirected, shared name and finally drop. [Q089](03_QUESTION_BANK.md#q089-explain-leiden-without-claiming-it-understands-software), [Q090](03_QUESTION_BANK.md#q090-why-choose-leiden-rather-than-a-simple-traversal), [Q091](03_QUESTION_BANK.md#q091-how-does-leiden-improve-on-louvain-conceptually), [Q092](03_QUESTION_BANK.md#q092-what-leiden-configuration-does-codegraph-explicitly-set), [Q093](03_QUESTION_BANK.md#q093-are-community-ids-stable-between-ingestions), [Q094](03_QUESTION_BANK.md#q094-how-are-community-names-generated), [Q095](03_QUESTION_BANK.md#q095-what-if-leiden-or-projection-cleanup-fails), [Q096](03_QUESTION_BANK.md#q096-does-the-architecture-tool-retrieve-a-query-specific-leiden-subgraph). |
| 18. `community_summarizer.py:110` labels | Semantic interpretation; samples→Community nodes | Sequential model calls, structured shape, atomic label replacement only. [Q094](03_QUESTION_BANK.md#q094-how-are-community-names-generated). |
| 19. `db/__init__.py:88/166/213` serialization/read | UI contracts; Neo4j→nodes/edges/source | Remove code/vectors, 200 row cap, elementId, scope; [Q031](03_QUESTION_BANK.md#q031-why-is-the-source-endpoint-separate-from-the-graph-endpoint)/[Q071](03_QUESTION_BANK.md#q071-are-neo4j-element-ids-durable-application-identifiers)/[Q075](03_QUESTION_BANK.md#q075-does-limit-200-make-graph-retrieval-cheap-and-complete). |
| 20. `agent/graph.py:21–332` queries/tools | Actual available evidence; arguments→string observations | Parameterized queries, mixed output formats, unbounded lists, no source tool. [Q121](03_QUESTION_BANK.md#q121-what-do-reasoning-action-and-observation-mean-in-this-agent), [Q122](03_QUESTION_BANK.md#q122-when-is-a-multi-tool-sequence-justified), [Q123](03_QUESTION_BANK.md#q123-how-does-dependency-analysis-differ-from-semantic-search), [Q124](03_QUESTION_BANK.md#q124-what-if-the-model-chooses-the-wrong-analysis-tool), [Q125](03_QUESTION_BANK.md#q125-can-the-model-access-a-different-repository-through-a-tool), [Q126](03_QUESTION_BANK.md#q126-why-are-tool-names-potentially-misleading-here), [Q127](03_QUESTION_BANK.md#q127-can-the-current-agent-verify-a-functions-source-implementation), [Q128](03_QUESTION_BANK.md#q128-what-makes-a-tool-result-trustworthy-enough-to-cite). |
| 21. `agent/graph.py:335–467` orchestration/metrics | Prompt/loop/accounting; question→answer+metrics | No history/scope injection, provider calls, proxy tokenizer; [Q113](03_QUESTION_BANK.md#q113-what-state-does-the-active-agent-carry), [Q114](03_QUESTION_BANK.md#q114-what-causes-the-agent-loop-to-continue-or-stop), [Q115](03_QUESTION_BANK.md#q115-how-are-tool-outputs-returned-to-the-model), [Q116](03_QUESTION_BANK.md#q116-what-happens-if-the-model-names-an-invalid-tool), [Q117](03_QUESTION_BANK.md#q117-what-if-the-model-repeatedly-calls-the-same-tool), [Q118](03_QUESTION_BANK.md#q118-how-are-tool-errors-handled), [Q119](03_QUESTION_BANK.md#q119-why-use-a-prebuilt-agent-rather-than-the-root-custom-stategraph), [Q120](03_QUESTION_BANK.md#q120-does-the-active-agent-have-long-term-memory). |
| 22. `api/dependencies.py:9`, `api/webhooks.py:22`, `pipeline.py:111` | Event trust/reconciliation; signed event→background merges | 202 before work, HMAC raw bytes, missing removals/PR API/replay; [Q145](03_QUESTION_BANK.md#q145-does-repository-scoping-prevent-one-user-accessing-another-users-code), [Q146](03_QUESTION_BANK.md#q146-how-is-the-webhook-signature-computed-and-checked), [Q147](03_QUESTION_BANK.md#q147-are-webhook-replay-attacks-prevented), [Q148](03_QUESTION_BANK.md#q148-what-prevents-a-malicious-repository-from-executing-code-during-ingestion), [Q149](03_QUESTION_BANK.md#q149-could-this-application-suffer-denial-of-service-from-a-large-repository), [Q150](03_QUESTION_BANK.md#q150-does-graph-payload-redaction-protect-private-source), [Q151](03_QUESTION_BANK.md#q151-what-is-the-prompt-injection-impact-of-malicious-repository-instructions), [Q152](03_QUESTION_BANK.md#q152-how-would-you-handle-secrets-and-dependency-security-before-deployment). |
| 23. `frontend/src/api.js:32/95/166` | Client contracts; UI values→HTTP/decoded records | Chunk buffering, shared hard-coded base, signal support varies. [Q025](03_QUESTION_BANK.md#q025-why-can-ingestion-return-http-200-when-it-failed)/040. |
| 24. `frontend/src/App.jsx:363/585/808/971`, CodePanel, GraphLegend | Rendering/state; graph→layout and interactions | 300 ticks, dimming, stale-response/controller races, lazy source. [Q033](03_QUESTION_BANK.md#q033-where-is-frontend-state-managed), [Q034](03_QUESTION_BANK.md#q034-how-does-react-flow-receive-its-graph), [Q035](03_QUESTION_BANK.md#q035-do-cluster-filters-reduce-the-number-of-rendered-nodes), [Q036](03_QUESTION_BANK.md#q036-how-does-the-source-drawer-avoid-stale-requests), [Q037](03_QUESTION_BANK.md#q037-can-the-conversation-remember-an-earlier-question), [Q038](03_QUESTION_BANK.md#q038-what-race-can-occur-while-loading-graphs), [Q039](03_QUESTION_BANK.md#q039-why-is-a-shared-abortcontroller-ref-risky), [Q040](03_QUESTION_BANK.md#q040-is-chat-currently-streamed-to-the-browser). |
| 25. `backend/tests/`, frontend tests, Postman collection, history docs | Distinguish evidence layers; fixtures→assertions | Mocks vs live services, no answer eval; historical claims need revision context. [Q153](03_QUESTION_BANK.md#q153-how-many-tests-are-present-at-the-analyzed-revision), [Q154](03_QUESTION_BANK.md#q154-what-do-the-parser-tests-prove-and-not-prove), [Q155](03_QUESTION_BANK.md#q155-why-are-mocked-database-tests-useful), [Q156](03_QUESTION_BANK.md#q156-what-does-the-postman-repository-workflow-automate), [Q157](03_QUESTION_BANK.md#q157-how-does-postman-validate-webhook-hmac-behavior), [Q158](03_QUESTION_BANK.md#q158-do-the-node-tests-validate-react-rendering), [Q159](03_QUESTION_BANK.md#q159-what-does-the-token-metrics-unit-test-actually-assert), [Q160](03_QUESTION_BANK.md#q160-what-is-the-highest-value-missing-test-category)/[Q177](03_QUESTION_BANK.md#q177-what-does-git-establish-about-project-ownership), [Q178](03_QUESTION_BANK.md#q178-what-changed-in-the-latest-commit), [Q179](03_QUESTION_BANK.md#q179-what-historical-trade-off-appeared-in-the-batching-refactor), [Q180](03_QUESTION_BANK.md#q180-when-was-semantic-search-introduced-and-what-did-it-add), [Q181](03_QUESTION_BANK.md#q181-what-does-the-token-tracking-commit-prove), [Q182](03_QUESTION_BANK.md#q182-how-did-postman-support-evolve), [Q183](03_QUESTION_BANK.md#q183-which-documentation-is-stale-after-head), [Q184](03_QUESTION_BANK.md#q184-what-was-the-hardest-personal-engineering-challenge). |

### Fourteen execution traces

1. **Full ingestion:** `submitRepository` → `ingestRepository` URL JSON → `ingest_repository` validation → `_stream_repository_ingestion` download/discovery → parser completions → relative paths/IDs → `save_parsed_ast_to_neo4j_with_progress` → terminal record. Temporary files are removed in finally. Source graph writes happen before completion.
2. **One source file:** `parse_file` validates bytes/suffix → grammar lock → thread `_parse_source` → parser CST → definition records with spans/signatures/qualified names → call ownership/unattributed lists → optional `attach_function_entity_ids`. Invalid syntax warns; unsupported extension raises.
3. **Graph construction:** `_extract_etl_records` drops malformed entries and declaration-only signatures → dedup lists → optional delete/token baseline → File batches → metadata embedding + Function batches → CALLS batches → external tagging → GDS → labels. Different transactions make partial state observable.
4. **Embedding generation:** `_function_embedding_text` builds name/path text → `generate_embeddings` trim/validate → cached client request → provider items sorted by index → count/dimension validation → strict pair with functions → `fn.embedding` set. No source chunking or persistent embedding cache.
5. **Semantic retrieval:** Claude emits semantic tool call → query embedding → global SEARCH top-k → repository post-filter → text name/path/score rows → ToolMessage → Claude. No matches does not prove no implementation.
6. **Leiden/architecture retrieval:** ingestion projects Functions/CALLS undirected → writes community property → drops projection → samples names/paths → structured labels → Community/membership writes. Later architecture tool returns summaries/counts. **No query-specific member/source subgraph extraction stage exists.** The graph UI uses a different capped query.
7. **Single tool call:** `_run_code_agent` fresh messages → prebuilt model node emits tool call → ToolNode validates name/arguments → async tool opens session → result rows formatted → ToolMessage attached → next model response. Scope is still a model argument.
8. **Multi-tool question:** possible semantic search for “retry” → returned function name/path → list functions in that file → outgoing/incoming query → final prose. This is an illustrative sequence; tool selection/order is not guaranteed or validated. Same-name collisions may make later steps ambiguous.
9. **API chat response:** `_run_code_agent` extracts last message text → `_tool_context_text` joins tool messages → count_tokens → fetch stored baseline → arithmetic → `/api/chat` maps answer to response. Errors anywhere, including metric DB read, become 502; tool trace is not returned.
10. **Graph rendering:** scoped graph Cypher→records→deduplicated elementId nodes/edges→strip body/vector→frontend normalize→degree map→300 force ticks→custom React Flow nodes/edges. Hover creates undirected emphasis; arrows remain directed.
11. **Progress streaming:** generator JSON+newline→arbitrary byte chunks→TextDecoder stream mode→buffer complete lines→onProgress→state→progress 100 scope activation→graph load. Error record throws; HTTP 200 alone is insufficient.
12. **Repository cleanup:** explicit UI confirmation→DELETE path endpoint→normalization→`delete_repository_graph` scoped DETACH DELETE→success→reset local state. Beforeunload instead sends best-effort keepalive JSON DELETE. Startup uses broader all-scoped deletion.
13. **Invalid webhook:** body/header→Depends verify_github_signature→missing header or mismatched raw HMAC→401 before handler/BackgroundTasks. With valid signature but malformed/non-object JSON, handler returns 400; no job is queued.
14. **Failed ingestion:** suppose batch 2 embedding fails: old scope already deleted, baseline/files/batch 1 committed; later calls/GDS/labels may not exist; generator logs and yields generic error at current progress; finally releases temp root; frontend shows error. No rollback/retry job restores the prior graph.

## 32. Active-recall learning system

### The 50 facts to recall without notes

1. Active backend package is under `backend/`.
2. Root Python files are a distinct legacy prototype.
3. Revision analyzed is `79fa768` on `main`.
4. Full ingest accepts HTTPS GitHub repository URLs.
5. Full ingest uses the default branch, without a ref field.
6. Canonical scope is owner/repository, with case preserved.
7. GitHub bearer authentication is optional and server-wide.
8. Downloads buffer the whole archive.
9. Archive members are checked for path containment.
10. Archive/file/resource quotas are absent.
11. Seven suffixes are supported.
12. JS and JSX share one parser/lock.
13. TSX uses its own grammar entry point.
14. Imports are not extracted.
15. Classes are parser metadata, not persistent Class nodes.
16. Tree-sitter provides syntax, not runtime dispatch.
17. Syntax-error trees can still produce records.
18. Raw code is sliced from captured definition bytes.
19. Parser line ranges are one-based; columns are byte-based zero-based values.
20. New function IDs include repository/path/language/qualified name/discriminator.
21. Body-only edits preserve those parser IDs.
22. Reordering repeated signatures can affect occurrence identity.
23. Calls are lexically owned or unattributed, but targets remain unresolved.
24. Neo4j does not yet persist the new IDs.
25. Function MERGE still uses repo plus simple name.
26. Legacy CALLS copies file-wide targets to every file function.
27. CALLS records inferred-file-scope provenance.
28. ExternalFunction is an additional label on Function.
29. External means no stored definition, not a verified package.
30. Full parsing has a 32-slot semaphore.
31. Parsing is serialized per language.
32. One task is allocated per file.
33. ETL writes batches of 100 in separate transactions.
34. Full replacement is not atomic.
35. Embeddings use name plus path, not bodies.
36. Embeddings are expected to have 1,536 dimensions.
37. Vector index similarity is cosine.
38. Semantic top-k is globally selected then repository-filtered.
39. Leiden projects all scoped Function/CALLS, including external nodes.
40. Its projection is undirected and unweighted.
41. Community labels use at most 15 names and 5 paths.
42. Seven tools are registered; none is a source-reading tool.
43. Blast radius is direct callers, capped at 100 rows.
44. Chat is fresh per request; browser history is not model memory.
45. Active chat returns JSON, ingestion returns NDJSON.
46. Graph query LIMIT 200 counts rows, not nodes.
47. Startup deletes all nodes with a non-null repo_name.
48. HMAC lacks replay protection; public APIs lack auth.
49. Current audit: 92 backend passes + 4 skips; 13 frontend passes.
50. Specific 737k→18k benchmark and general answer accuracy are unverified.

### Glossary tied to CodeGraph

| Term | Meaning and application |
|---|---|
| CST / AST | Concrete syntax versus abstract representation; Tree-sitter CST is reduced into selected CodeGraph records. |
| Capture query | Grammar pattern binding nodes such as function names/definitions. |
| Lexical scope | Syntactic enclosing class/function hierarchy used in qualified names. |
| Semantic resolution | Determining the referenced symbol/type; not supplied by current capture patterns. |
| Dynamic dispatch | Runtime receiver-dependent target selection; unresolved here. |
| Overload | Same name with different signatures; parser distinguishes, storage currently collapses. |
| Call site | Specific invocation syntax/location; recorded in memory, not as a persistent entity. |
| Entity identity | Key separating definitions; parser canonical hash differs from legacy graph key. |
| Snapshot | Immutable repository analysis generation; proposed, not implemented. |
| ETL | Extract parsed data, transform to rows, load graph; transformation currently weakens identity. |
| Property graph | Nodes/relationships with labels/types/properties, as in Neo4j. |
| MERGE | Match-or-create pattern; not a substitute for correct unique keys. |
| UNWIND | Turn parameter list into rows for batched writes. |
| OPTIONAL MATCH | Preserve a row when optional relationship data is absent. |
| DETACH DELETE | Delete node and incident relationships; used for scope cleanup. |
| Index / constraint | Access acceleration versus enforced data invariant; only indexes created here. |
| Projection | In-memory GDS graph derived from stored scoped Functions/CALLS. |
| Community | Connectivity partition, not inherently a source module. |
| Modularity | Partition objective comparing within-group connectivity to a baseline; not answer accuracy. |
| Leiden | Community algorithm used before labeling; not a semantic code interpreter. |
| Embedding | Learned numeric representation of text; currently function metadata. |
| Cosine similarity | Normalized vector dot product; configured ranking metric. |
| ANN | Approximate nearest-neighbor retrieval; candidates can be missed. |
| Post-filter | Scope filtering after global candidate selection; can reduce in-scope recall. |
| RAG | Retrieval-augmented generation; CodeGraph supplies graph-tool observations. |
| ReAct | Alternating model decisions, tool actions and observations. |
| ToolMessage | Structured execution observation returned to the model, counted as selected context. |
| Checkpointer | Persistent graph/conversation state mechanism; not configured. |
| Groundedness | Whether claims follow from authoritative evidence; not automatically validated here. |
| Hallucination | Unsupported/generated factual claim; can occur despite tool use. |
| Precision / recall | Retrieved evidence relevance versus completeness; neither currently benchmarked. |
| Ablation | Controlled removal of one feature to measure its contribution, proposed for Leiden. |
| NDJSON | Newline-separated JSON records, used for ingestion progress. |
| SSE | Event stream framing; frontend compatibility branch, not active chat output. |
| Backpressure | Limiting upstream work based on downstream capacity; semaphore only partially bounds this pipeline. |
| GIL | Interpreter coordination relevant to Python thread CPU scaling; offload still aids responsiveness. |
| Idempotency | Repeated operation has equivalent effect; MERGE does not make the whole ingestion exactly once. |
| Atomicity | All-or-nothing boundary; holds per managed transaction, not whole ingestion. |
| HMAC | Shared-secret body authentication/integrity; does not encrypt or prevent replay. |
| CORS | Browser origin policy; not user authentication or an ACL. |
| Authorization | Permission to access a repository/operation; absent from public API routes. |
| Prompt injection | Untrusted data attempting to influence model instructions/actions; metadata can be a channel. |
| Liveness / readiness | Process response versus ability to accept dependent work; current health is liveness. |
| Provenance | How a fact was obtained; inferred_from_file_scope is crucial call-edge provenance. |
| Source map/reference | Entity/range/revision link enabling verification; no validated final-answer reference contract yet. |

### Exercises — attempt before opening the key

E01. Draw complete ingestion from browser URL to progress 100. Mark external calls and every durable write boundary.

E02. Draw the stored graph schema. Cross out Class, Import and Branch if they are not actually persistent labels.

E03. For `def a(): x()` and `def b(): y()` in one file, list parser call ownership and current ETL call rows separately.

E04. Give two definitions with the same simple name in different classes. Explain parser identity versus persisted identity and which source may be returned.

E05. Whiteboard the LangGraph loop and all seven tools without inventing a source tool.

E06. Trace “Where is retry logic, and who calls it?” through a possible multi-tool sequence. Mark observations versus hypotheses.

E07. Draw the actual Graph-RAG flow. Then draw a proposed query→community→member-source expansion in a different color and identify missing implementation.

E08. Explain Leiden using two dense groups with one bridge. State projection direction/weights, inclusion of external functions and label input limits.

E09. Calculate the supplied 737,000→18,000 reduction. Name five reasons it is not an end-to-end cost or accuracy result.

E10. Explain how an evidence-free answer can score 100% efficiency and what quality metric would expose it.

E11. Trace a webhook with a valid signature but malformed JSON, then a valid push with a removed file.

E12. Show why scope predicates are insufficient when the model changes repo_name. Design request-bound authorization.

E13. Draw the transaction states after deletion, files, first function batch, embedding failure. Show what another graph reader can see.

E14. Explain the 32-slot semaphore, executor, grammar lock and retained-result memory separately. Predict the effect of 1,000 slots.

E15. Write a conceptual incoming three-hop query and explain cycle, scope and path-explosion concerns. Identify the actual one-hop query.

E16. Construct an NDJSON stream split in the middle of a UTF-8 character and a JSON line. Explain decoder and buffer responsibilities.

E17. Create a timeline where an old graph fetch returns after repository deletion, and another where old chat cleanup clears a new ingestion controller.

E18. Design an evaluation comparing full-source, vector-only, graph-only, community-assisted and multi-tool retrieval at matched budgets.

E19. Give a 60-second project pitch and a source-level explanation of the parser/persistence gap without overclaiming.

E20. Choose one real historical commit you personally remember. Explain your contribution, AI assistance if any, diagnosis, validation and remaining limitation.

### Separate answer key

**E01:** URL/schema validation→zipball/default branch→safe temp extraction→discovery→32-slot read/count/parse→relative paths/IDs→delete old scope/token baseline→file batches→OpenAI vectors/function batches→call batches/tagging→GDS projection/write/drop→OpenAI labels/atomic label replace→100→temp cleanup. Every DB batch is a separate boundary; provider waits are external.

**E02:** Repository→CONTAINS→File→DEFINES→Function→CALLS→Function; Function can also have ExternalFunction label and IN_COMMUNITY→Community. Embeddings/code are properties. No persistent Class/Import/Branch/User/Commit.

**E03:** Parser a owns x and b owns y; legacy outgoing_calls is x,y; ETL emits a→x, a→y, b→x, b→y. All persisted edges carry file-scope inference provenance.

**E04:** `A.validate` and `B.validate` have different parser keys. Per-file ETL deduplicates simple names, and cross-file DB MERGE collapses repo/name. Source/path may reflect the retained/last-written record, not the intended class.

**E05:** Fresh messages→model→tool calls?→ToolNode→ToolMessages→model→final. Tools: callers, files, functions-in-file, outgoing, external, semantic, architecture. No checkpointer/source tool/global application budget.

**E06:** Semantic search→file functions→incoming callers→outgoing targets. Names/paths/scores are candidate evidence; inferred edges are not proven runtime calls; exact retry behavior cannot be verified by current tool bodies.

**E07:** Agent chooses independent tools; architecture returns stored labels/counts, vector returns metadata hits. The proposed expansion lacks query-specific community selection, member source retrieval, reranking and budget logic.

**E08:** Connectivity communities can split a single component; GDS uses undirected unweighted Function/CALLS including external nodes. Labels sample 15 names/5 paths. Dense groups may reflect false ETL edges rather than real modules.

**E09:** 97.5577%, rounded 97.56%. No raw experiment; proxy tokenizer; supported-source-only baseline; excludes system/user/output; no repeated history billing/preprocessing costs/quality assessment.

**E10:** Positive baseline, no ToolMessages gives zero context. Claim-level grounding, evidence coverage and appropriate abstention—not reduction alone—identify failure.

**E11:** Raw HMAC passes, JSON parse fails→400/no background task. Removed-only push yields no changed-file deletion; graph remains stale. 202 is acknowledgement, not job completion.

**E12:** Queries trust the argument; another valid scope can be read. Derive authorized scope from principal/request, remove model scope argument and enforce it in all tools and database access.

**E13:** Old graph gone; baseline/files committed; some functions committed; provider fails; no rollback. Readers may observe a partial graph; stage error and temp cleanup do not restore old data.

**E14:** Semaphore limits active pipeline tasks, executor supplies threads, lock serializes shared grammar parser, all tasks/results still consume memory. Increasing slots mostly creates waiting work and pressure unless measurements reveal usable parallel capacity.

**E15:** Bound hops, constrain all traversed nodes to repository/snapshot and deduplicate/cap. Enumerating paths can explode; visited-node reachability differs. Current CALLERS_QUERY contains only one CALLS hop and LIMIT 100.

**E16:** TextDecoder's stream option preserves incomplete byte sequences; string buffer preserves incomplete lines. Multiple lines per chunk and a final unterminated line must be handled. HTTP 200 still needs terminal success/error interpretation.

**E17:** loadGraph lacks signal/generation check, so stale promise resolution can reset arrays after delete. Chat finally clears abortRef unconditionally; ingestion finalizer checks identity. Separate controllers/generations fix ownership, then test deferred completion order.

**E18:** Fixed SHAs, independently labeled claims/ranges, held-out questions, same model/budgets and repeated runs. Measure evidence precision/recall, claim correctness/groundedness, abstention, latency and actual total cost. Isolate Leiden from graph-identity changes.

**E19:** Use [volume 01](01_FOUNDATIONS.md)'s pitches. Essential detail: HEAD's lexical records are richer than ETL; inference and generated interpretation are not validated source facts.

**E20:** There is no repository-derived personal answer. Supply firsthand facts and tie them to a diff/test. Do not substitute a generated anecdote for your experience.

---

[Back to contents](#contents) · [Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](03_QUESTION_BANK.md) · [Next](05_MOCK_INTERVIEWS.md)
