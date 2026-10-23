# Part 28 — 200-question technical interview bank

[Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](02_APPLICATION_AND_AUDIT.md) · [Next](04_STUDY_AND_DEFENSE.md)

## Contents

- [A. Project overview and motivation](#a-project-overview-and-motivation)
- [B. Complete system architecture](#b-complete-system-architecture)
- [C. Python and backend development](#c-python-and-backend-development)
- [D. FastAPI and API design](#d-fastapi-and-api-design)
- [E. React and frontend engineering](#e-react-and-frontend-engineering)
- [F. Tree-sitter and parsing](#f-tree-sitter-and-parsing)
- [G. Repository ingestion](#g-repository-ingestion)
- [H. Concurrency and performance](#h-concurrency-and-performance)
- [I. Neo4j and graph modeling](#i-neo4j-and-graph-modeling)
- [J. Cypher and graph traversal](#j-cypher-and-graph-traversal)
- [K. Graph algorithms](#k-graph-algorithms)
- [L. Leiden community detection](#l-leiden-community-detection)
- [M. Embeddings and vector search](#m-embeddings-and-vector-search)
- [N. Retrieval-augmented generation](#n-retrieval-augmented-generation)
- [O. LangGraph and agent orchestration](#o-langgraph-and-agent-orchestration)
- [P. ReAct and tool calling](#p-react-and-tool-calling)
- [Q. LLM selection and prompt engineering](#q-llm-selection-and-prompt-engineering)
- [R. AI reliability and evaluation](#r-ai-reliability-and-evaluation)
- [S. Security and trust boundaries](#s-security-and-trust-boundaries)
- [T. Testing and Postman](#t-testing-and-postman)
- [U. Deployment and scalability](#u-deployment-and-scalability)
- [V. Architectural decisions](#v-architectural-decisions)
- [W. Development history](#w-development-history)
- [X. Weaknesses and improvements](#x-weaknesses-and-improvements)
- [Y. Challenging hypothetical scenarios](#y-challenging-hypothetical-scenarios)

---

Each entry contains a spoken answer, implementation explanation, source reference, follow-up with answer, misconception and tested concept. Answers describe HEAD, not a proposed future system. Sources are relative to the repository root. Additional escalating interviews appear in [the pressure drills](05_MOCK_INTERVIEWS.md#progressive-pressure-drills-four-deeper-sequences).

Reference key: **M**=`backend/app/main.py`; **P**=`backend/app/services/parser_service.py`; **ID**=`backend/app/utils/entity_identity.py`; **ETL**=`backend/app/db/graph_ops.py`; **DB**=`backend/app/db/__init__.py`; **IDX**=`backend/app/db/neo4j_client.py`; **GDS**=`backend/app/db/gds_ops.py`; **EMB**=`backend/app/services/embedding_service.py`; **LABEL**=`backend/app/services/community_summarizer.py`; **AG**=`backend/app/agent/graph.py`; **GH**=`backend/app/services/github_service.py`; **PIPE**=`backend/app/services/pipeline.py`; **HOOK**=`backend/app/api/webhooks.py`; **SIG**=`backend/app/api/dependencies.py`; **UI**=`frontend/src/App.jsx`; **HTTP**=`frontend/src/api.js`; **CODE**=`frontend/src/components/CodePanel.tsx`. A suffix is the one-based source line.

## A. Project overview and motivation

[All categories](#contents) · [Q001](#q001-what-practical-problem-does-codegraph-address) · [Q002](#q002-why-can-keyword-search-be-insufficient-for-repository-exploration) · [Q003](#q003-why-represent-code-as-a-graph-when-imports-already-exist) · [Q004](#q004-what-distinguishes-this-application-from-a-chatbot-reading-files) · [Q005](#q005-which-parts-of-codegraph-are-deterministic-and-which-are-probabilistic) · [Q006](#q006-what-is-the-most-important-current-limitation) · [Q007](#q007-what-can-you-honestly-claim-about-project-performance) · [Q008](#q008-explain-codegraph-to-an-interviewer-in-one-minute)

### Q001. What practical problem does CodeGraph address?

**Spoken answer:** It helps developers orient themselves in unfamiliar repositories through a graph and scoped natural-language questions. I would present it as an exploration aid whose results require source verification.

**Technical explanation:** The product combines default-branch ingestion, stored source snippets, inferred function relationships, metadata vectors and community summaries. These give different entry points into code, but none proves complete repository understanding.

**Evidence:** M:376; UI:585; AG:343.

**Follow-up:** Who benefits most today? **Answer:** A developer exploring a supported-language repository locally, where the prototype's ephemeral storage and approximate graph are acceptable.

**Misconception:** It is not a compiler-accurate refactoring engine. **Concept tested:** Product scope and evidence.

### Q002. Why can keyword search be insufficient for repository exploration?

**Spoken answer:** A developer may know the behavior they want without knowing its identifier. Semantic search can suggest names and files, while graph tools offer relationship clues.

**Technical explanation:** CodeGraph's semantic input is only function name and path, so it can also miss behavior hidden behind generic names. There is no keyword/BM25 tool or hybrid ranking implemented.

**Evidence:** ETL:208; AG:266.

**Follow-up:** Would you remove keyword search from a redesign? **Answer:** No. Exact symbols and error strings often favor lexical search; I would compare combined retrieval on a labeled dataset.

**Misconception:** Semantic search does not dominate exact lookup for every task. **Concept tested:** Retrieval complementarity.

### Q003. Why represent code as a graph when imports already exist?

**Spoken answer:** Imports are only one kind of relationship, and this parser does not actually extract them. CodeGraph stores definitions and approximate calls so tools can query neighbors and communities.

**Technical explanation:** A File→Function relation and Function→Function call are different from module import statements. The current graph adds queryability, but its call inference needs qualification because it copies file-wide target names.

**Evidence:** P:36; ETL:178.

**Follow-up:** Could imports improve the graph? **Answer:** Yes, if extracted and resolved per language; they would provide binding evidence rather than automatically prove runtime call targets.

**Misconception:** Import graphs and call graphs are not interchangeable. **Concept tested:** Graph semantics.

### Q004. What distinguishes this application from a chatbot reading files?

**Spoken answer:** It maintains a separate indexed representation and offers graph visualization and targeted tools. The current agent mostly sees metadata and summaries, not file bodies.

**Technical explanation:** Neo4j persists functions, calls, vectors and communities. Chat selects among seven tools; a browser-only source endpoint serves stored code independently. This separation is both an architectural feature and a grounding limitation.

**Evidence:** DB:34; AG:343; CODE:58.

**Follow-up:** Is this necessarily more accurate than a large-context prompt? **Answer:** No comparison establishes that. Full-source prompting is a useful baseline because it can see evidence these tools omit.

**Misconception:** A graph-backed answer is not automatically source-grounded. **Concept tested:** System differentiation.

### Q005. Which parts of CodeGraph are deterministic and which are probabilistic?

**Spoken answer:** Parsing and fixed query formatting follow programmed rules; model tool choices and generated labels or answers are probabilistic. Leiden also has unstabilized algorithm choices because no seed is set.

**Technical explanation:** Deterministic code can still produce inaccurate semantics: file-wide call attribution is repeatable but wrong for some snippets. Cached compiled agents do not make provider outputs deterministic.

**Evidence:** P:601; ETL:123; LABEL:86; GDS:37.

**Follow-up:** Would temperature zero guarantee correctness? **Answer:** No. It cannot repair missing evidence, merged identities or an invalid inference.

**Misconception:** Determinism and correctness are separate properties. **Concept tested:** Reliability taxonomy.

### Q006. What is the most important current limitation?

**Spoken answer:** The stored graph collapses same-named functions and overattributes file calls. That can mislead every downstream dependency, community and answer feature.

**Technical explanation:** HEAD's parser creates stronger IDs and lexical calls, but the writer discards them. Fixing persistence and queries together is more fundamental than changing the LLM or improving prose.

**Evidence:** ID:37; ETL:55,178.

**Follow-up:** Why not describe the parser upgrade as solving it? **Answer:** Because it only fixes intermediate representation; the application's reads still use the legacy graph.

**Misconception:** A local subsystem improvement does not imply an end-to-end fix. **Concept tested:** Contract propagation.

### Q007. What can you honestly claim about project performance?

**Spoken answer:** I can describe bounded work and batching, and report the tests/build actually run. I cannot claim general throughput, latency or a 97.5% quality-preserving reduction without benchmark artifacts.

**Technical explanation:** The context metric counts tool text against indexed-source tokens. The repository contains no fixed query set or raw results for the supplied 737k-to-18k example.

**Evidence:** AG:425; README.md final limitations.

**Follow-up:** How would you strengthen the claim? **Answer:** Record fixed repository SHAs, prompts, traces, token rules, timing and independent answer-quality scores.

**Misconception:** Optimization mechanisms are not measured speedups. **Concept tested:** Evidence-based claims.

### Q008. Explain CodeGraph to an interviewer in one minute.

**Spoken answer:** It downloads a GitHub default branch, parses supported sources, builds a Neo4j graph with metadata embeddings and Leiden summaries, and exposes it through React Flow and a seven-tool Claude agent. Its current graph is approximate.

**Technical explanation:** Separate ingestion enrichment from query-time retrieval, then explain that source inspection is a browser feature and chat history is local only. Mention the parser-to-database identity gap before making precision claims.

**Evidence:** M:376; AG:335; UI:971.

**Follow-up:** What detail proves you understand more than the stack names? **Answer:** I can trace exactly how `_extract_etl_records` drops lexical IDs and creates caller-target rows from file-wide lists.

**Misconception:** A technology list is not an architecture explanation. **Concept tested:** System communication.

## B. Complete system architecture

[All categories](#contents) · [Q009](#q009-why-are-there-two-fastapi-applications-in-this-repository) · [Q010](#q010-where-does-ingestion-end-and-question-answering-begin) · [Q011](#q011-why-does-the-application-use-both-sync-and-async-neo4j-drivers) · [Q012](#q012-what-happens-if-the-community-label-service-is-removed) · [Q013](#q013-what-data-contract-connects-the-assistant-to-the-graph-ui) · [Q014](#q014-which-state-survives-a-browser-refresh-or-api-restart) · [Q015](#q015-where-are-the-main-trust-boundaries) · [Q016](#q016-why-not-combine-the-entire-pipeline-in-one-service-function)

### Q009. Why are there two FastAPI applications in this repository?

**Spoken answer:** The root app is an older prototype; backend/app is the active full application. The working directory affects which `app.main` Python imports.

**Technical explanation:** The root API has a legacy webhook route and SSE chat behavior. The active backend uses `/api/webhooks/github`, repository-scoped requests and JSON chat. Mixing their contracts produces misleading tests or startup instructions.

**Evidence:** app/main.py; M:191; tests/test_webhook.py.

**Follow-up:** How would you prevent accidental imports? **Answer:** Use a unique package name or explicit packaging/entry point and separate legacy code from active test discovery.

**Misconception:** Same module path spelling does not imply the same application. **Concept tested:** Python package boundaries.

### Q010. Where does ingestion end and question answering begin?

**Spoken answer:** Ingestion finishes after embeddings, graph writes, Leiden and community labeling, then emits progress 100. Chat later reads that stored representation and may embed its query.

**Technical explanation:** Full ingestion is expensive preprocessing. A chat request does not ordinarily download or reparse the repository, but the semantic tool incurs a fresh embedding call. Failure in labeling prevents normal completion despite earlier graph writes.

**Evidence:** ETL:294; M:462; AG:279.

**Follow-up:** Can an agent read a partial graph? **Answer:** Yes, there is no active-snapshot gate preventing a direct API request during ingestion.

**Misconception:** Progress completion is not an atomic visibility boundary. **Concept tested:** Lifecycle separation.

### Q011. Why does the application use both sync and async Neo4j drivers?

**Spoken answer:** The sync module verifies connectivity and initializes indexes; request data paths mostly use the async driver. It is historical implementation structure, not a demonstrated necessity.

**Technical explanation:** Startup offloads sync initialization to a thread and closes both drivers on shutdown. The sync session dependency exists but is not how most active handlers obtain sessions.

**Evidence:** IDX:55; DB:52; M:60.

**Follow-up:** What risk does this introduce? **Answer:** Duplicated configuration/lifecycle and connection pools make startup and tests harder; a consolidated driver strategy could simplify them.

**Misconception:** A defined dependency is not necessarily used by every route. **Concept tested:** Resource ownership.

### Q012. What happens if the community-label service is removed?

**Spoken answer:** Current ingestion awaits it, so it would fail unless the pipeline is changed. The already-written graph could still be useful, but the API would not emit normal completion.

**Technical explanation:** Graph construction, clustering and labels are separate stages with separate side effects. Optional enrichment would need an explicit degraded-success state and UI/tool behavior for unlabeled clusters.

**Evidence:** ETL:314; LABEL:110.

**Follow-up:** Would fallback cluster numbers be enough? **Answer:** They already exist in graph serialization, but ingestion still needs a policy to continue when label generation fails.

**Misconception:** A UI fallback does not imply backend degradation support. **Concept tested:** Failure coupling.

### Q013. What data contract connects the assistant to the graph UI?

**Spoken answer:** They share the active repository string, but there is no entity-level link contract. Chat returns Markdown and metrics; graph nodes use Neo4j element IDs.

**Technical explanation:** Tools return names/paths or community records without stable function references. The frontend renders ordinary Markdown and cannot reliably map a mentioned function to a unique node.

**Evidence:** AG:127,467; DB:95; UI:547.

**Follow-up:** How would you add clickable references safely? **Answer:** Return validated reference IDs grounded in tool results, with canonical entity and snapshot IDs, then resolve or fetch the target graph neighborhood.

**Misconception:** Matching display names is not reliable entity navigation. **Concept tested:** Cross-component identity.

### Q014. Which state survives a browser refresh or API restart?

**Spoken answer:** Browser chat and selection do not persist. Neo4j has a volume, but API startup explicitly deletes every node with a non-null repository scope.

**Technical explanation:** Beforeunload also attempts deletion of the active scope. Stored graph state is therefore intentionally ephemeral in current behavior, and shared users cannot rely on retention.

**Evidence:** M:60; ETL:29; HTTP:154.

**Follow-up:** Does Docker persistence contradict this? **Answer:** No. Durable storage can faithfully persist an application's deletion operation.

**Misconception:** A persistent volume is not a data-retention policy. **Concept tested:** State lifecycle.

### Q015. Where are the main trust boundaries?

**Spoken answer:** User requests, downloaded repositories, provider outputs and stored graph data cross different boundaries. Repository names in requests or tool arguments are not authenticated ownership claims.

**Technical explanation:** HMAC protects webhook body authenticity only. Public routes and model-selected scopes remain unrestricted; source and metadata can flow to database, browser and providers according to the selected path.

**Evidence:** SIG:9; M:349; AG:104.

**Follow-up:** What must be enforced outside prompts? **Answer:** Authorization, scope binding, resource budgets and destructive-operation policy.

**Misconception:** Prompts cannot replace access controls. **Concept tested:** Trust architecture.

### Q016. Why not combine the entire pipeline in one service function?

**Spoken answer:** The existing services separate download, parsing, persistence and AI enrichment enough to test contracts independently. But orchestrating them still requires explicit consistency and failure policies.

**Technical explanation:** Small functions make mocked tests easy; they do not make a distributed workflow atomic. The current stream coordinates several external systems with no durable job state or rollback.

**Evidence:** M:376; GH:59; ETL:238.

**Follow-up:** What would you introduce first for reliability? **Answer:** A persisted job/snapshot model with stage status and atomic activation, before adding distributed workers.

**Misconception:** Modularity alone does not ensure reliable orchestration. **Concept tested:** Service boundaries.

## C. Python and backend development

[All categories](#contents) · [Q017](#q017-what-does-async-provide-in-codegraph) · [Q018](#q018-why-use-a-dataclass-for-parser-progress) · [Q019](#q019-what-is-cached-with-lru_cache-here) · [Q020](#q020-how-are-errors-isolated-during-batch-parsing) · [Q021](#q021-why-use-strict-zip-when-pairing-functions-and-vectors) · [Q022](#q022-why-use-finally-blocks-in-ingestion-and-gds) · [Q023](#q023-what-are-the-consequences-of-importing-neo4j_client) · [Q024](#q024-why-are-python-type-hints-not-enough-for-tool-safety)

### Q017. What does async provide in CodeGraph?

**Spoken answer:** It lets network and database waits yield to other requests. CPU-heavy parsing is moved to threads so it does not run directly on FastAPI's event loop.

**Technical explanation:** `async def` alone does not make synchronous work nonblocking. ETL flattening and context token counting still execute synchronously in async flows, and large tasks can affect responsiveness.

**Evidence:** P:690; M:399; AG:437.

**Follow-up:** Would making `_extract_etl_records` async help? **Answer:** Only if it yielded or offloaded work; changing the keyword alone provides no parallelism.

**Misconception:** Async syntax is not CPU acceleration. **Concept tested:** Cooperative concurrency.

### Q018. Why use a dataclass for parser progress?

**Spoken answer:** It gives each completion a clear immutable shape with index, processed count, total, optional result and token count. The index separates completion order from original input order.

**Technical explanation:** The frozen slotted dataclass discourages accidental mutation and reduces per-object overhead. The receiver restores deterministic result ordering even though tasks finish asynchronously.

**Evidence:** P:175,794.

**Follow-up:** Why preserve ordering? **Answer:** It makes ETL deterministic and avoids completion timing changing which same-name record wins under legacy behavior.

**Misconception:** Completion order and source order are different. **Concept tested:** Data contracts.

### Q019. What is cached with lru_cache here?

**Spoken answer:** The application caches provider clients, the compiled agent and tokenizer encodings. It does not cache embeddings, parsed files, answers or repository snapshots by content.

**Technical explanation:** Client caching avoids setup overhead but can retain settings until process restart or cache clearing. The agent factory cache does not remember conversation turns because no checkpointer or history is supplied.

**Evidence:** EMB:17; LABEL:68; AG:335; backend/app/utils/tokens.py:13.

**Follow-up:** Could changing an environment variable update the cached client? **Answer:** Not reliably after settings/client construction; configuration reload needs an explicit lifecycle.

**Misconception:** Object reuse is not semantic result caching. **Concept tested:** Cache scope.

### Q020. How are errors isolated during batch parsing?

**Spoken answer:** Each file task catches read/parse errors, logs them and returns a missing result while progress continues. A failed file does not discard successful neighbors.

**Technical explanation:** Tokens counted before a parse failure can still contribute to the baseline. The final ingestion response does not list every skipped file, so success does not establish complete extraction.

**Evidence:** P:755; backend/tests/test_parser_service.py:189.

**Follow-up:** What improvement would make partial success visible? **Answer:** Return skipped-file counts/reasons and define whether some errors should fail the job.

**Misconception:** Successful job status need not mean every file parsed. **Concept tested:** Fault isolation.

### Q021. Why use strict zip when pairing functions and vectors?

**Spoken answer:** Each vector must correspond to exactly one function row. Strict pairing prevents silently dropping records if lengths differ.

**Technical explanation:** The embedding service already checks count and dimensionality and sorts by provider index. ETL's `zip(...,strict=True)` adds another shape boundary before database writes, though malformed duplicate provider indexes are not separately validated.

**Evidence:** EMB:40; ETL:302.

**Follow-up:** Does this prove the vector belongs to the right function semantically? **Answer:** It verifies positional contract assumptions, not provider/model meaning or an end-to-end retrieval result.

**Misconception:** Shape validation is not semantic validation. **Concept tested:** Defensive data alignment.

### Q022. Why use finally blocks in ingestion and GDS?

**Spoken answer:** They attempt resource cleanup on both success and failure. Temporary directories and GDS projections should not remain just because a later stage raises.

**Technical explanation:** The cleanup itself can fail, and already committed graph writes are unaffected. Task cancellation also does not forcibly kill running thread work. Finally is lifecycle control, not transaction rollback.

**Evidence:** M:515; GDS:99; P:806.

**Follow-up:** Could cleanup hide the original exception? **Answer:** Yes, an exception from a finally cleanup operation can replace the original propagated error unless handled carefully.

**Misconception:** Finally does not guarantee successful cleanup. **Concept tested:** Exception semantics.

### Q023. What are the consequences of importing neo4j_client?

**Spoken answer:** Importing it attempts a synchronous connectivity check. That can slow imports and complicate tests before any endpoint is invoked.

**Technical explanation:** The driver creation uses five-second connection/acquisition timeouts and returns None on failure; initialize_database retries later. During this audit network was disabled to prevent unintended service use.

**Evidence:** IDX:55,79.

**Follow-up:** How might you redesign it? **Answer:** Create drivers explicitly in lifespan/dependencies and inject them, keeping module import free of network side effects.

**Misconception:** Importing application code is not always side-effect free. **Concept tested:** Initialization design.

### Q024. Why are Python type hints not enough for tool safety?

**Spoken answer:** They help schemas and validation but cannot establish ownership, correctness or bounded work. A string repo_name can still name someone else's repository.

**Technical explanation:** Tools trim strings and semantic search clamps k, but most lists are unbounded and scopes remain model chosen. Pydantic/API validation and database authorization are separate responsibilities.

**Evidence:** AG:104,266; M:73.

**Follow-up:** What should a safe tool context include? **Answer:** An authenticated, server-derived repository/snapshot scope and explicit result/time budgets.

**Misconception:** Type-correct arguments can still be unauthorized. **Concept tested:** Validation versus policy.

## D. FastAPI and API design

[All categories](#contents) · [Q025](#q025-why-can-ingestion-return-http-200-when-it-failed) · [Q026](#q026-what-does-health-actually-prove) · [Q027](#q027-why-is-repo_name-required-for-chat-and-source-lookup) · [Q028](#q028-how-is-idempotency-different-for-deletion-and-ingestion) · [Q029](#q029-what-does-webhook-http-202-mean) · [Q030](#q030-how-are-backend-errors-mapped-to-http-responses) · [Q031](#q031-why-is-the-source-endpoint-separate-from-the-graph-endpoint) · [Q032](#q032-what-happens-if-you-launch-several-api-workers)

### Q025. Why can ingestion return HTTP 200 when it failed?

**Spoken answer:** The response headers are sent when streaming starts. Later download, database or model failures are represented by NDJSON error records.

**Technical explanation:** Clients must validate terminal stream semantics, not only response.ok. The frontend throws on payload.error and requires a progress-100 record with repo_name; Postman explicitly tests the distinction.

**Evidence:** M:376,468; HTTP:57.

**Follow-up:** What would a durable API add? **Answer:** A job ID and persisted terminal status, allowing recovery after disconnect independent of HTTP transport.

**Misconception:** HTTP transport success is not job success. **Concept tested:** Streaming contracts.

### Q026. What does `/health` actually prove?

**Spoken answer:** Only that the handler can respond with status ok in a serving process. It does not query Neo4j, GDS or either model provider.

**Technical explanation:** Startup itself requires database initialization and cleanup, so a new process may fail before serving. Once running, health can still be green while later dependencies fail.

**Evidence:** M:60,544.

**Follow-up:** How would readiness differ? **Answer:** It would assess the dependencies needed for accepting work, ideally with cached/cheap checks and clear degraded states.

**Misconception:** Liveness and readiness are not identical. **Concept tested:** Operational API design.

### Q027. Why is repo_name required for chat and source lookup?

**Spoken answer:** It makes the intended graph scope explicit and prevents accidental unscoped reads. It is not authentication because callers can choose any valid repository string.

**Technical explanation:** Pydantic and normalization require owner/repository syntax. Source lookup combines that predicate with elementId; chat also puts it in the prompt but does not enforce it on tool arguments.

**Evidence:** M:73,248; DB:34.

**Follow-up:** Would hiding the input field secure it? **Answer:** No. Authorization must be enforced on server requests and every downstream access.

**Misconception:** A required scope parameter is not an ACL. **Concept tested:** Request scoping.

### Q028. How is idempotency different for deletion and ingestion?

**Spoken answer:** Deleting an already-empty scope still returns success, so repeated deletion has the same end state. Repeated ingestion does expensive rebuild work and can interleave with other jobs.

**Technical explanation:** The API has no idempotency key or serialized generation protocol. Webhooks also lack delivery deduplication; MERGE does not make model calls or multi-stage effects exactly once.

**Evidence:** M:301; ETL:278; PIPE:219.

**Follow-up:** Can MERGE eliminate all duplicate nodes? **Answer:** Not under all concurrent scenarios without suitable uniqueness constraints, and it cannot fix an insufficient key.

**Misconception:** Idempotent database clauses do not make a workflow idempotent. **Concept tested:** Distributed operation semantics.

### Q029. What does webhook HTTP 202 mean?

**Spoken answer:** The body passed signature/JSON checks and background processing was scheduled. It does not mean the graph was updated successfully.

**Technical explanation:** FastAPI BackgroundTasks runs in-process after acknowledgement. Pipeline exceptions are logged, there is no job ID/status endpoint, and missing repository metadata causes early return.

**Evidence:** HOOK:53; PIPE:139,233.

**Follow-up:** How would a sender learn completion? **Answer:** A durable job record/status API or delivery outcome channel would be required; it is not present.

**Misconception:** Accepted is not completed. **Concept tested:** Asynchronous acknowledgements.

### Q030. How are backend errors mapped to HTTP responses?

**Spoken answer:** Graph/source/delete distinguish database auth/unavailability as 503 and query errors as 500. Chat broadly maps execution failures to 502, while ingestion uses stream errors after validation.

**Technical explanation:** Validation produces 422; source absence produces 404; webhook signature errors produce 401 and signed malformed JSON produces 400. These distinctions help clients choose retry versus correction.

**Evidence:** M:209,248,301,349; HOOK:39.

**Follow-up:** Is every 502 a provider outage? **Answer:** No. Chat catches all exceptions, including graph/metrics errors, so diagnosis needs logs or finer internal error categories.

**Misconception:** Public status codes may combine several failure causes. **Concept tested:** Error contracts.

### Q031. Why is the source endpoint separate from the graph endpoint?

**Spoken answer:** Graph loading avoids transferring raw bodies and vectors for every node. Source is fetched only when a function is selected.

**Technical explanation:** Serialization removes raw_code and embedding; fetch_node_code reads a scoped Function by storage ID. This reduces payload size but does not protect source from unauthorized callers because no auth exists.

**Evidence:** DB:98,213.

**Follow-up:** Could metadata still be sensitive? **Answer:** Yes, private function names, paths and module descriptions may reveal internal design even without bodies.

**Misconception:** Payload minimization is not authorization. **Concept tested:** API payload design.

### Q032. What happens if you launch several API workers?

**Spoken answer:** Each process has its own initialization flag, drivers and cached agent, and each startup runs global scoped cleanup. That is unsafe for shared retained data.

**Technical explanation:** Per-process locks do not coordinate ingestion or GDS graph names across workers. More workers may increase throughput but also multiply cleanup and concurrency hazards.

**Evidence:** M:60; IDX:89; GDS:74.

**Follow-up:** What must change before scaling workers? **Answer:** Remove startup-wide deletion, introduce durable job/snapshot coordination and bind access to tenants.

**Misconception:** Horizontal scaling can amplify correctness bugs. **Concept tested:** Process lifecycle.

## E. React and frontend engineering

[All categories](#contents) · [Q033](#q033-where-is-frontend-state-managed) · [Q034](#q034-how-does-react-flow-receive-its-graph) · [Q035](#q035-do-cluster-filters-reduce-the-number-of-rendered-nodes) · [Q036](#q036-how-does-the-source-drawer-avoid-stale-requests) · [Q037](#q037-can-the-conversation-remember-an-earlier-question) · [Q038](#q038-what-race-can-occur-while-loading-graphs) · [Q039](#q039-why-is-a-shared-abortcontroller-ref-risky) · [Q040](#q040-is-chat-currently-streamed-to-the-browser)

### Q033. Where is frontend state managed?

**Spoken answer:** One App component owns graph, repository, chat, progress and filter state; CodePanel and GraphLegend own their local interaction state. There is no external store or router.

**Technical explanation:** This keeps the prototype straightforward, but shared abortRef and intertwined lifecycle effects require care. Hooks derive adjacency and styling rather than introducing a synchronized server-state layer.

**Evidence:** UI:585; CODE:54.

**Follow-up:** Would Redux automatically solve stale responses? **Answer:** No. Request cancellation/version checks and clear ownership are still needed regardless of state library.

**Misconception:** A state library is not a concurrency policy. **Concept tested:** State ownership.

### Q034. How does React Flow receive its graph?

**Spoken answer:** The client fetches nodes/edges, normalizes them, computes a D3 layout, then supplies controlled node/edge arrays with custom renderers.

**Technical explanation:** The backend's grid positions are replaced. D3 simulation runs 300 synchronous ticks, and node sizes derive from degree; this can block the main thread on larger payloads.

**Evidence:** UI:280,363,509.

**Follow-up:** Why not let the backend limit solve all performance issues? **Answer:** The 200-row cap is not a node budget and may still produce costly layout; it also truncates useful data.

**Misconception:** Server caps and client performance are separate concerns. **Concept tested:** Rendering pipeline.

### Q035. Do cluster filters reduce the number of rendered nodes?

**Spoken answer:** They mainly dim and recolor nodes and edges. They are visual emphasis controls, not progressive loading or a reduced server subgraph.

**Technical explanation:** `styledNodes` and `styledEdges` map over the loaded arrays. Legend counts also use that loaded subset, so they are not complete repository community sizes.

**Evidence:** UI:697,759; frontend/src/utils/communities.js.

**Follow-up:** How would true large-graph exploration work? **Answer:** Fetch targeted neighborhoods or paginated/aggregated views and manage expansion state explicitly.

**Misconception:** Visual isolation is not data pruning. **Concept tested:** Filtering semantics.

### Q036. How does the source drawer avoid stale requests?

**Spoken answer:** Its effect creates an AbortController and aborts when the selected node or repository changes. It resets displayed source and ignores abort errors.

**Technical explanation:** Loading finalization checks whether the controller was aborted. This is a local lifecycle guard; graph fetching elsewhere does not have equivalent protection.

**Evidence:** CODE:58; HTTP:110.

**Follow-up:** Is source displayed with original file line numbers? **Answer:** No, the snippet is highlighted with local line numbers; the endpoint does not expose original parser ranges.

**Misconception:** A numbered snippet does not necessarily show original source locations. **Concept tested:** Effect cleanup.

### Q037. Can the conversation remember an earlier question?

**Spoken answer:** The browser displays history, but each backend request sends only the latest message and repository. No checkpointer or prior messages are supplied.

**Technical explanation:** A follow-up like “what about the second one?” may lack the context visible to the user. Caching the compiled agent does not retain those chat messages.

**Evidence:** HTTP:181; AG:394; UI:971.

**Follow-up:** How would you add memory safely? **Answer:** Persist bounded history keyed by authenticated user, repository and snapshot, with context management and deletion policy.

**Misconception:** Visible chat history is not model memory. **Concept tested:** Client/server state divergence.

### Q038. What race can occur while loading graphs?

**Spoken answer:** An earlier fetch can finish after a later state change and overwrite the current graph, because loadGraph has no request-generation check or cancellation signal.

**Technical explanation:** The active repository may have changed or been deleted while the request was in flight. UI disabling reduces some interactions but is not a server/client consistency proof.

**Evidence:** UI:808; HTTP:95.

**Follow-up:** How would you test it? **Answer:** Use deferred mocked promises to resolve requests out of order and assert stale results are ignored.

**Misconception:** Await alone does not order independent requests. **Concept tested:** Asynchronous UI correctness.

### Q039. Why is a shared AbortController ref risky?

**Spoken answer:** Chat and ingestion reuse the same ref. An older chat finally block can clear it after a newer ingestion has stored its controller.

**Technical explanation:** Ingestion checks controller identity before clearing; chat clears unconditionally. Losing the new reference can break later stop/unmount cancellation without changing the underlying fetch itself.

**Evidence:** UI:958,1058.

**Follow-up:** What is the minimal design correction? **Answer:** Separate controllers by operation or conditionally clear only the matching generation, with race tests.

**Misconception:** Aborting one task does not safely transfer ref ownership by itself. **Concept tested:** Resource lifetime races.

### Q040. Is chat currently streamed to the browser?

**Spoken answer:** The active server returns ordinary JSON after the agent finishes. The frontend contains an SSE compatibility parser, but that branch is not evidence of active streaming.

**Technical explanation:** The chat Accept header permits both types. In the JSON branch only response text is rendered; metrics are discarded. NDJSON streaming is implemented for ingestion, a different endpoint.

**Evidence:** M:349; HTTP:178; UI:1004.

**Follow-up:** What would genuine token streaming require? **Answer:** A server event contract, streamed model execution, error/final metrics events and cancellation semantics.

**Misconception:** Client parser capability does not establish server behavior. **Concept tested:** End-to-end feature verification.

## F. Tree-sitter and parsing

[All categories](#contents) · [Q041](#q041-what-is-the-difference-between-a-concrete-and-abstract-syntax-tree-here) · [Q042](#q042-which-languages-are-actually-supported) · [Q043](#q043-how-does-codegraph-distinguish-a-call-from-a-function-reference) · [Q044](#q044-can-tree-sitter-resolve-polymorphic-method-calls) · [Q045](#q045-how-are-nested-and-anonymous-calls-attributed) · [Q046](#q046-how-are-overloads-represented) · [Q047](#q047-how-are-function-ids-generated-and-what-remains-unstable) · [Q048](#q048-how-does-the-parser-handle-invalid-syntax-and-encodings)

### Q041. What is the difference between a concrete and abstract syntax tree here?

**Spoken answer:** Tree-sitter retains grammar-level syntax and spans in a concrete tree; CodeGraph extracts a smaller record representation from selected named nodes. That record is not a complete semantic model.

**Technical explanation:** Queries capture definitions and calls, then raw_code is sliced from original bytes. Punctuation and source positions make accurate text extraction possible without executing the repository.

**Evidence:** P:359,464,601.

**Follow-up:** Does a parsed call identify its runtime target? **Answer:** No. The parser lacks imported symbol bindings, inferred receiver types and runtime state.

**Misconception:** Syntax structure does not imply semantic resolution. **Concept tested:** Parsing versus semantics.

### Q042. Which languages are actually supported?

**Spoken answer:** Seven suffixes cover Python, JavaScript/JSX, TypeScript/TSX, Go and Java. JS/JSX share a grammar; TSX uses the TypeScript package's TSX entry point.

**Technical explanation:** The mapping is explicit and discovery uses it. A language package's broader capabilities do not mean CodeGraph captures every construct or supports unlisted extensions.

**Evidence:** P:25,217; M:46.

**Follow-up:** What happens to Rust or Markdown? **Answer:** Full ingestion excludes their unsupported suffixes; they do not enter the indexed-source baseline.

**Misconception:** Seven extensions are not seven completely separate language ecosystems. **Concept tested:** Coverage boundaries.

### Q043. How does CodeGraph distinguish a call from a function reference?

**Spoken answer:** It matches grammar call-expression patterns rather than every identifier. Passing `foo` as a value is different from capturing `foo()`.

**Technical explanation:** Python patterns require a `call`; JS/TS/Go use call_expression; Java uses method_invocation. Computed/dynamic forms outside the specific patterns can be missed even when they execute a function.

**Evidence:** P:41,70,130,155.

**Follow-up:** Does `new Client()` become a Java method call? **Answer:** Not through the method_invocation query; constructor declarations are captured, but object-creation call resolution is absent.

**Misconception:** A named symbol occurrence is not necessarily a call site. **Concept tested:** Syntactic pattern precision.

### Q044. Can Tree-sitter resolve polymorphic method calls?

**Spoken answer:** Not by syntax parsing alone, and CodeGraph does not add the type analysis required. It preserves receiver syntax and marks the call unresolved.

**Technical explanation:** Two `obj.validate()` expressions can dispatch differently depending on runtime type. Legacy graph matching by the simple target name makes a guess that should not be defended as resolution.

**Evidence:** P:544,563; ETL:72.

**Follow-up:** Could an LSP fix every dynamic case? **Answer:** It could improve static bindings for some languages, but runtime reflection and dynamic behavior remain uncertain.

**Misconception:** Better static analysis is not omniscient execution tracing. **Concept tested:** Dynamic dispatch.

### Q045. How are nested and anonymous calls attributed?

**Spoken answer:** Named nested definitions own calls inside their smallest enclosing body. Calls inside uncaptured anonymous functions are kept unattributed rather than assigned to an outer function.

**Technical explanation:** The algorithm scans captured bodies for containment, selects the smallest, then walks ancestors looking for anonymous boundaries. Default arguments and file-scope calls are outside captured function bodies.

**Evidence:** P:565; backend/tests/test_function_identity.py:173.

**Follow-up:** Does persistence use that ownership? **Answer:** No. It still uses the file-wide outgoing_calls list, so the improvement currently stops at parser output.

**Misconception:** Correct lexical ownership in memory is not a correct stored call graph. **Concept tested:** Scope attribution.

### Q046. How are overloads represented?

**Spoken answer:** The parser records signatures and occurrence discriminators, so Java overloads and TypeScript declaration signatures can be distinct in memory. Legacy persistence still collapses simple names.

**Technical explanation:** TypeScript declarations without bodies stay in functions but are excluded from defined_functions and ETL. Return type is not part of the identity signature key.

**Evidence:** P:426,508; ETL:153.

**Follow-up:** Why not use name and line number as identity? **Answer:** Line shifts would break references after unrelated edits; canonical fields are more stable, though moves/signature changes still change IDs.

**Misconception:** Overload capture does not prove overload target resolution. **Concept tested:** Entity identity.

### Q047. How are function IDs generated and what remains unstable?

**Spoken answer:** A versioned SHA-256 hash covers repository, normalized relative path, language, qualified name and signature/occurrence discriminator. Body-only edits preserve the ID.

**Technical explanation:** The canonical JSON representation avoids process-randomized hash behavior. Reordering repeated same-signature definitions can swap occurrence identity, and repository case is preserved. No snapshot ID is included.

**Evidence:** ID:37; P:706.

**Follow-up:** Are these IDs used in graph navigation? **Answer:** No, current graph/source APIs still use Neo4j element IDs and simple-name persistence.

**Misconception:** A deterministic ID is not automatically a durable application reference. **Concept tested:** Canonical key design.

### Q048. How does the parser handle invalid syntax and encodings?

**Spoken answer:** It warns on Tree-sitter error nodes and still extracts available captures. Decoded snippets use UTF-8 replacement, and full-file token counting does too.

**Technical explanation:** Reads are bytes and there is no encoding detection or binary sniff. Batch exceptions can skip files while progress continues; successful extraction can be partial rather than an all-or-nothing parse.

**Evidence:** P:374,614,762.

**Follow-up:** Would you count such a repository as fully analyzed? **Answer:** No. I would expose parse coverage/error metadata and qualify downstream answers.

**Misconception:** Error-tolerant parsing does not imply complete correct analysis. **Concept tested:** Partial results.

## G. Repository ingestion

[All categories](#contents) · [Q049](#q049-how-is-a-repository-url-validated) · [Q050](#q050-how-does-codegraph-choose-a-branch) · [Q051](#q051-what-happens-with-a-private-repository) · [Q052](#q052-how-is-archive-path-traversal-prevented) · [Q053](#q053-which-files-are-discovered-and-counted) · [Q054](#q054-what-happens-if-github-rate-limits-or-the-network-fails) · [Q055](#q055-does-the-webhook-path-implement-complete-incremental-indexing) · [Q056](#q056-what-happens-when-two-ingestions-target-the-same-repository)

### Q049. How is a repository URL validated?

**Spoken answer:** The backend requires HTTPS and a GitHub hostname, decodes the path, and requires an owner/repository pair. It then constructs a fixed GitHub API URL from encoded names.

**Technical explanation:** The normalizer removes a trailing .git and trims whitespace but preserves case. A broad character regex is not full GitHub resource validation; existence and access are discovered by the API request.

**Evidence:** M:126,139; GH:76.

**Follow-up:** Can a query string select a branch? **Answer:** No. The downstream zipball request omits a ref and uses the default branch.

**Misconception:** URL acceptance does not establish repository existence. **Concept tested:** Input normalization.

### Q050. How does CodeGraph choose a branch?

**Spoken answer:** Full ingestion always requests the repository's default-branch zipball. There is no branch field or branch entity.

**Technical explanation:** A `/tree/feature` URL has too many path parts and is rejected. Webhooks fetch immutable commit bytes but merge into the same owner/repository scope, so branch separation is absent.

**Evidence:** GH:67,86; PIPE:89.

**Follow-up:** What would multi-branch support require? **Answer:** Include ref/snapshot identity in storage and requests, and separate active indexes so branches cannot overwrite each other.

**Misconception:** Commit-specific downloading is not branch-aware persistence. **Concept tested:** Revision modeling.

### Q051. What happens with a private repository?

**Spoken answer:** It can be fetched if the server's optional GitHub token has access. The client does not provide a per-user credential or ownership identity.

**Technical explanation:** Headers use a server-wide bearer token. An inaccessible private repository can return 404; successful ingestion then stores source retrievable through unauthenticated APIs.

**Evidence:** GH:29; M:248.

**Follow-up:** Why is server token access not enough for multi-user safety? **Answer:** The server may access more repositories than a particular caller is entitled to see.

**Misconception:** Upstream service authorization is not downstream user authorization. **Concept tested:** Credential delegation.

### Q052. How is archive path traversal prevented?

**Spoken answer:** Each member's resolved destination must remain under the resolved extraction root before extractall is called. Empty or unexpected root layouts are rejected.

**Technical explanation:** This addresses ordinary traversal paths but not resource exhaustion. The archive is buffered and no compressed-size, expansion-ratio, member-count or explicit special-file limits are enforced.

**Evidence:** GH:38.

**Follow-up:** How would you test it safely? **Answer:** Create small in-memory ZIP fixtures with escaping and normal paths in a temporary directory, never against user files.

**Misconception:** Path containment is not a complete archive security policy. **Concept tested:** Filesystem boundaries.

### Q053. Which files are discovered and counted?

**Spoken answer:** Sorted traversal includes supported suffixes and prunes common generated/environment directories. It does not read .gitignore rules or impose file-size limits.

**Technical explanation:** The baseline counts supported discovered source text, including tests with supported suffixes, but not README prose or other unsupported assets. File content is read in full.

**Evidence:** M:47,154; P:762.

**Follow-up:** Could generated code inflate the index? **Answer:** Yes, if it lies outside the fixed pruned directory names and has a supported suffix.

**Misconception:** “Full repository tokens” is a restricted-source baseline. **Concept tested:** Index coverage.

### Q054. What happens if GitHub rate-limits or the network fails?

**Spoken answer:** The download raises and the ingestion stream emits an error. There is no application retry/backoff scheduler for these requests.

**Technical explanation:** HTTP 404 gets a specific not-found message; other status errors retain the status in the error text. Request/ZIP/value errors use a broader download/extraction message; temp cleanup is attempted.

**Evidence:** GH:81; M:468.

**Follow-up:** Could a retry lose the previous graph? **Answer:** A failed download occurs before deletion, but a later failure after replacement begins can leave a partial scope.

**Misconception:** Failure timing determines data impact. **Concept tested:** Stage-aware recovery.

### Q055. Does the webhook path implement complete incremental indexing?

**Spoken answer:** No. It merges added/modified files but does not reconcile removed files, obsolete definitions/calls or complete token totals. Ordinary PR file enumeration is also missing.

**Technical explanation:** Push paths are deduplicated, source is fetched at a commit SHA, and all parse jobs are gathered. Missing metadata skips processing; the final blast-radius stage is only a log placeholder.

**Evidence:** PIPE:23,111,207,228.

**Follow-up:** How should a deleted function be handled? **Answer:** Remove or version its definition/call sites and reconcile unresolved references in a new snapshot, then activate consistently.

**Misconception:** Incremental fetching is not complete incremental maintenance. **Concept tested:** Change reconciliation.

### Q056. What happens when two ingestions target the same repository?

**Spoken answer:** They can interleave deletes, batches, embeddings and GDS work because there is no job lock or snapshot protocol. The final graph can mix generations.

**Technical explanation:** Ordinary indexes do not enforce unique keys, and both runs use the same GDS projection name. Cleanup or graph requests can observe or modify intermediate data.

**Evidence:** ETL:278; GDS:74; IDX:26.

**Follow-up:** Would a Python lock solve all deployments? **Answer:** Only within one process; multi-worker or distributed jobs need shared ordering/locking or atomic snapshot activation.

**Misconception:** Local mutual exclusion is not distributed coordination. **Concept tested:** Concurrent consistency.

## H. Concurrency and performance

[All categories](#contents) · [Q057](#q057-is-codegraph-really-parsing-32-files-simultaneously) · [Q058](#q058-how-does-the-gil-affect-this-pipeline) · [Q059](#q059-does-the-semaphore-provide-full-backpressure) · [Q060](#q060-what-happens-if-the-concurrency-limit-increases-to-1000) · [Q061](#q061-how-is-deterministic-result-ordering-retained) · [Q062](#q062-what-is-the-worst-local-parsing-complexity-concern) · [Q063](#q063-why-batch-database-writes-by-100-records) · [Q064](#q064-what-does-cancellation-actually-stop)

### Q057. Is CodeGraph really parsing 32 files simultaneously?

**Spoken answer:** It allows at most 32 active read/token/parse tasks per full-ingest batch, but parsing is serialized per grammar. It does not create exactly 32 parser threads.

**Technical explanation:** The semaphore encloses the whole stage, asyncio.to_thread uses the default executor, and a shared parser lock limits same-language execution. JS and JSX share their lock.

**Evidence:** P:24,250,753.

**Follow-up:** What should the resume say? **Answer:** “Implemented bounded asynchronous file processing with a 32-slot limit,” qualified by parser locking and no claimed speedup.

**Misconception:** A semaphore size is not measured parallel throughput. **Concept tested:** Concurrency precision.

### Q058. How does the GIL affect this pipeline?

**Spoken answer:** Python-heavy work may not run in parallel across threads, while native libraries and I/O can behave differently. Offloading still protects event-loop responsiveness.

**Technical explanation:** Parsing includes native Tree-sitter plus Python capture processing; tokenization and reads add different costs. No benchmark establishes how much GIL release or CPU scaling occurs in this environment.

**Evidence:** P:601,690,763.

**Follow-up:** Would a process pool always be faster? **Answer:** No. Grammar initialization, interprocess serialization and memory overhead can dominate small files.

**Misconception:** Threads and processes have workload-dependent trade-offs. **Concept tested:** Runtime parallelism.

### Q059. Does the semaphore provide full backpressure?

**Spoken answer:** It bounds active per-file work, but all tasks are created and successful results are retained. It does not bound total job memory or all concurrent ingestions.

**Technical explanation:** The downloader buffers the archive, parsing accumulates dictionaries/raw code, and ETL builds full row lists before writing batches. A slow consumer can leave completed task results waiting.

**Evidence:** P:789; M:404; ETL:128.

**Follow-up:** What would stronger backpressure look like? **Answer:** A bounded queue with fixed workers and incremental result consumption, plus global admission and byte budgets.

**Misconception:** Bounded active tasks do not imply bounded memory. **Concept tested:** Flow control.

### Q060. What happens if the concurrency limit increases to 1,000?

**Spoken answer:** More files can hold bytes and wait for language locks or the executor, so memory pressure may rise without proportional throughput gains.

**Technical explanation:** The per-language critical section and provider/database stages remain bottlenecks. Multiple requests multiply active work further; a larger local limit is not a scale strategy.

**Evidence:** P:690,753.

**Follow-up:** What measurements should guide tuning? **Answer:** Per-stage latency, CPU utilization, resident memory, executor queue depth and throughput by language/file size.

**Misconception:** More concurrency is not always more performance. **Concept tested:** Capacity tuning.

### Q061. How is deterministic result ordering retained?

**Spoken answer:** Each task carries its original index; completions arrive through as_completed and results are placed back into indexed slots.

**Technical explanation:** This decouples progress responsiveness from input order. Deterministic ETL ordering is useful because legacy same-name merges can overwrite fields in order-dependent ways.

**Evidence:** P:179,794,818; M:404.

**Follow-up:** Does ordering eliminate collisions? **Answer:** No. It only makes an incorrect collision outcome more reproducible.

**Misconception:** Deterministic output can still encode incorrect semantics. **Concept tested:** Ordering versus correctness.

### Q062. What is the worst local parsing complexity concern?

**Spoken answer:** Call ownership checks compare each call against captured definitions, then inspect ancestor boundaries. Large files with many definitions and calls can add roughly C×F work.

**Technical explanation:** Tree-sitter's parse cost is only part of total processing. Legacy ETL separately multiplies each file's function count by its unique outgoing names, inflating call rows and downstream graph work.

**Evidence:** P:565; ETL:178.

**Follow-up:** How could ownership lookup improve? **Answer:** Use source intervals or a tree traversal maintaining the current lexical owner, while preserving anonymous-boundary rules.

**Misconception:** Native parsing speed does not bound application extraction cost. **Concept tested:** Algorithmic profiling.

### Q063. Why batch database writes by 100 records?

**Spoken answer:** It bounds transaction payloads and retry units and avoids one enormous write. The trade-off is partial visibility and more round trips.

**Technical explanation:** Files, functions and calls each use chunk_data and execute_write. Embeddings are obtained outside the managed transaction callback, reducing accidental provider repetition during DB retries.

**Evidence:** ETL:101,260,298.

**Follow-up:** Is 100 proven optimal? **Answer:** No. It is an implemented constant, tested for batching behavior rather than benchmarked as the best size.

**Misconception:** A tested batch boundary is not an optimal tuning result. **Concept tested:** Batching trade-offs.

### Q064. What does cancellation actually stop?

**Spoken answer:** It can cancel pending async tasks and HTTP waits, but not necessarily a thread already parsing or graph writes already committed.

**Technical explanation:** Parser finally cancels and gathers outstanding tasks. Stream cleanup removes temporary storage after ownership transfer; there is no persisted cancelled job state or rollback of ingestion.

**Evidence:** P:806; M:515; HTTP:43.

**Follow-up:** How would a durable system handle it? **Answer:** Check cancellation between stages, stop scheduling new work and leave unactivated staging data for cleanup.

**Misconception:** Client abort does not guarantee server rollback. **Concept tested:** Cancellation semantics.

## I. Neo4j and graph modeling

[All categories](#contents) · [Q065](#q065-what-labels-and-relationships-are-actually-stored) · [Q066](#q066-how-does-the-current-function-key-fail) · [Q067](#q067-what-exactly-is-an-externalfunction) · [Q068](#q068-what-uniqueness-constraints-exist) · [Q069](#q069-how-does-repository-isolation-work) · [Q070](#q070-could-postgresql-store-the-same-graph) · [Q071](#q071-are-neo4j-element-ids-durable-application-identifiers) · [Q072](#q072-how-are-communities-represented)

### Q065. What labels and relationships are actually stored?

**Spoken answer:** Repository, File, Function, additional ExternalFunction labels, and Community; relationships are CONTAINS, DEFINES, CALLS and IN_COMMUNITY.

**Technical explanation:** Classes and lexical identities exist in parser output but are not persisted. Methods use Function, embeddings are properties, and there are no Branch, Import, User or call-site nodes.

**Evidence:** ETL:35,52,66,86; LABEL:39.

**Follow-up:** Why does that matter for explanations? **Answer:** The agent cannot query a class/import relationship that the graph never represents.

**Misconception:** A parser field is not necessarily a database entity. **Concept tested:** Schema reconstruction.

### Q066. How does the current Function key fail?

**Spoken answer:** It merges by repository and simple name, so unrelated definitions named validate become one node. The new parser IDs are ignored.

**Technical explanation:** Different files can both point to that node with DEFINES. The first legacy file field can remain while file_path/raw_code/embedding are replaced by another definition.

**Evidence:** ETL:55,57; ID:3.

**Follow-up:** What key should replace it? **Answer:** A canonical function identity with uniqueness enforcement and snapshot semantics, propagated to all relationships and tools.

**Misconception:** Adding more display metadata does not fix the MERGE key. **Concept tested:** Identity invariants.

### Q067. What exactly is an ExternalFunction?

**Spoken answer:** It is a Function lacking a stored incoming DEFINES edge, tagged with an additional label and flag. It is not a verified dependency package.

**Technical explanation:** A target placeholder is created by simple name; later internal definitions clear external labels/flags. Missed local definitions and unrelated same-named library calls can be misclassified or merged.

**Evidence:** ETL:72,86.

**Follow-up:** Can it tell you which pip package to upgrade? **Answer:** No, package ownership and versions are not modeled.

**Misconception:** Unresolved external-looking names are not an SBOM. **Concept tested:** Unknown entity modeling.

### Q068. What uniqueness constraints exist?

**Spoken answer:** None are created by the active initializer. It creates ordinary composite indexes and a vector index.

**Technical explanation:** Indexes accelerate access but do not impose uniqueness. MERGE expresses matching intent; concurrent creation and weak keys still require explicit database constraints and migration planning.

**Evidence:** IDX:26.

**Follow-up:** Why not just add a uniqueness constraint on simple name? **Answer:** That would enforce the current conflation. First choose the correct canonical key, then enforce it.

**Misconception:** A constraint can enforce the wrong model perfectly. **Concept tested:** Integrity versus performance.

### Q069. How does repository isolation work?

**Spoken answer:** Most queries and merges include repo_name, separating same names across scopes. This limits accidental mixing but does not decide which user may access a scope.

**Technical explanation:** Some endpoint patterns rely on already-correct relationships, such as Functions reached from a scoped File. The agent can supply another valid scope, and no authenticated principal is checked.

**Evidence:** AG:21,38; ETL:55; M:209.

**Follow-up:** What would multi-tenancy require? **Answer:** Principal-bound authorization and tenant/snapshot keys enforced consistently on reads, writes, tools and cleanup.

**Misconception:** Data partitioning is not access control. **Concept tested:** Isolation boundaries.

### Q070. Could PostgreSQL store the same graph?

**Spoken answer:** Yes. Tables for entities and relationships could handle these direct-neighbor queries with joins, and recursive CTEs could support bounded transitive traversal.

**Technical explanation:** Neo4j's value here is integrated Cypher, vectors and GDS, not exclusive ability to store edges. The trade-off is service/plugin/query-version complexity.

**Evidence:** AG:21,45; GDS:17.

**Follow-up:** When would you choose PostgreSQL? **Answer:** If transactions, tenancy and ordinary lookups dominate and graph algorithms do not justify a separate graph stack.

**Misconception:** A graph-shaped domain does not mandate a graph database. **Concept tested:** Storage selection.

### Q071. Are Neo4j element IDs durable application identifiers?

**Spoken answer:** They identify stored entities for the current graph/source API, but should not be treated as stable across deletion and reingestion.

**Technical explanation:** The parser's fn:v1 IDs are separate and not persisted yet. Durable navigation needs canonical references plus a snapshot/version to detect entities that no longer exist.

**Evidence:** DB:95,34; ID:37.

**Follow-up:** Why include a snapshot if a canonical key is stable? **Answer:** The same logical function can have different code and relationships across revisions; existence/content must be versioned.

**Misconception:** Stable naming does not prove current snapshot membership. **Concept tested:** Reference durability.

### Q072. How are communities represented?

**Spoken answer:** Each Function receives a leiden_community number, and Community nodes store generated names/descriptions with IN_COMMUNITY memberships.

**Technical explanation:** Community IDs come from a clustering run, not source modules or permanent identities. Labels are replaced after generation; same numbers across runs need not refer to equivalent groups.

**Evidence:** GDS:37; LABEL:39.

**Follow-up:** Can a community be used as a stable bookmark? **Answer:** Only with run/snapshot identity and explicit handling of reclustering changes.

**Misconception:** A cluster number is not a permanent architectural module key. **Concept tested:** Derived data lifecycle.

## J. Cypher and graph traversal

[All categories](#contents) · [Q073](#q073-explain-the-incoming-call-query-in-plain-language) · [Q074](#q074-what-is-the-difference-between-incoming-and-outgoing-dependency-queries) · [Q075](#q075-does-limit-200-make-graph-retrieval-cheap-and-complete) · [Q076](#q076-how-does-unwind-help-graph-construction) · [Q077](#q077-how-would-you-add-a-three-hop-blast-radius-query-safely) · [Q078](#q078-why-can-vector-search-return-fewer-than-top_k-matches-for-the-selected-repository) · [Q079](#q079-what-does-detach-delete-do-and-why-is-it-risky-here) · [Q080](#q080-which-query-assumptions-would-you-validate-with-profile)

### Q073. Explain the incoming-call query in plain language.

**Spoken answer:** It finds scoped functions with an outgoing CALLS edge to the named scoped target, optionally collects their defining files, and returns up to 100 distinct caller rows.

**Technical explanation:** OPTIONAL MATCH allows caller information even when a defining file is absent. Aggregation and ordering happen before the limit; legacy inferred edges remain the evidence source.

**Evidence:** AG:21.

**Follow-up:** Does it find all downstream breakage? **Answer:** No. It is one-hop incoming structure with a cap, not transitive or behavioral impact analysis.

**Misconception:** A tool name does not change query semantics. **Concept tested:** Pattern reading.

### Q074. What is the difference between incoming and outgoing dependency queries?

**Spoken answer:** Incoming asks who calls a target; outgoing asks which targets a named caller calls. They reverse the subject of the same directed CALLS relation.

**Technical explanation:** The UI's hover adjacency is undirected for emphasis, which should not be mistaken for backend traversal direction. Source graph errors can affect both views.

**Evidence:** AG:21,45; UI:638.

**Follow-up:** If A calls B and B calls C, what returns for A outgoing? **Answer:** B, unless a separate direct A→C edge exists; the tool does not traverse through B.

**Misconception:** Visual neighbors and transitive dependencies are different. **Concept tested:** Directed graph reasoning.

### Q075. Does LIMIT 200 make graph retrieval cheap and complete?

**Spoken answer:** No. It caps returned query rows, not total nodes, and the query first collects repository nodes. It can both do substantial work and omit relevant graph parts.

**Technical explanation:** There is no ORDER BY, cursor or targeted expansion endpoint. Serializing n and m can yield a node count different from 200, and legend counts reflect the subset.

**Evidence:** DB:12,31,166.

**Follow-up:** How would you make results predictable? **Answer:** Define an ordered pagination or bounded neighborhood contract with explicit truncation metadata.

**Misconception:** Output cardinality limits do not bound all query work. **Concept tested:** Query planning.

### Q076. How does UNWIND help graph construction?

**Spoken answer:** It turns a parameter list into rows so one query can process a batch of files, functions or calls. This reduces per-record network overhead.

**Technical explanation:** Each batch still executes in a separate managed transaction, and MERGE/MATCH semantics determine identity. UNWIND does not itself deduplicate records or validate relationships.

**Evidence:** ETL:35,52,66.

**Follow-up:** Where is deduplication performed? **Answer:** Python sets deduplicate file/function/call records, then MERGE matches persisted entities and relationships.

**Misconception:** Batch syntax is not a consistency guarantee. **Concept tested:** Set-oriented database operations.

### Q077. How would you add a three-hop blast-radius query safely?

**Spoken answer:** I would bound path length, enforce repository/snapshot scope on every traversed node and cap/deduplicate results. I would not claim the current tool already does this.

**Technical explanation:** Variable-length path enumeration can grow rapidly in dense cyclic graphs; a visited-node traversal answers a different question than returning every path. Provenance must still identify inferred edges.

**Evidence:** AG:21; ETL:78.

**Follow-up:** What is the complexity? **Answer:** Reachability with a visited set is O(V+E), while enumerating paths can be combinatorial; the exact query plan must be measured.

**Misconception:** All graph traversals do not share one complexity bound. **Concept tested:** Traversal design.

### Q078. Why can vector search return fewer than top_k matches for the selected repository?

**Spoken answer:** Its index candidates are selected globally, then a repository predicate filters them. Other repositories can occupy candidate slots.

**Technical explanation:** The WHERE is outside SEARCH and the vector index has no repository filter property. Clamping k controls candidates but does not guarantee in-scope recall or fill the result count.

**Evidence:** AG:60; IDX:43.

**Follow-up:** What would improve it? **Answer:** Use supported in-index filtering with the proper index configuration, or a tested scoped candidate strategy; verify on multiple repositories.

**Misconception:** Post-filtering and pre-filtering are not equivalent. **Concept tested:** ANN filtering.

### Q079. What does DETACH DELETE do and why is it risky here?

**Spoken answer:** It removes nodes and their incident relationships. Cleanup scopes it by repo_name, while startup removes every node with any repo_name.

**Technical explanation:** The operation can be intentional for a local session but destructive in a shared service. Full rebuild deletes before later model/database stages, so failure cannot recover the old graph automatically.

**Evidence:** ETL:17,24,29.

**Follow-up:** Does deletion remove unscoped legacy nodes? **Answer:** Startup's predicate does not; they remain but active scoped reads generally exclude them.

**Misconception:** Deleting scoped data is not resetting the entire database. **Concept tested:** Deletion semantics.

### Q080. Which query assumptions would you validate with PROFILE?

**Spoken answer:** I would check composite index use for scoped merges/lookups, aggregation cost in graph/community queries, vector post-filter behavior and row estimates for high-degree nodes.

**Technical explanation:** Current tests often assert query strings or mocked arguments; no saved EXPLAIN/PROFILE plans prove production performance. LIMIT after collect and repeated optional matches deserve particular attention.

**Evidence:** DB:12; LABEL:24; IDX:26.

**Follow-up:** Would PROFILE be safe on any query? **Answer:** PROFILE executes the query, so use read queries or a disposable database for mutating statements.

**Misconception:** A query-plan investigation must respect side effects. **Concept tested:** Database verification.

## K. Graph algorithms

[All categories](#contents) · [Q081](#q081-which-graph-algorithms-does-the-backend-actually-run) · [Q082](#q082-why-are-calls-projected-as-undirected-for-leiden) · [Q083](#q083-are-call-frequencies-used-as-edge-weights) · [Q084](#q084-why-might-a-utility-function-distort-community-detection) · [Q085](#q085-how-do-connected-components-differ-from-communities) · [Q086](#q086-how-would-personalized-pagerank-differ-from-leiden-for-retrieval) · [Q087](#q087-what-does-modularity-tell-you-about-answer-quality) · [Q088](#q088-what-happens-to-isolated-functions-in-the-projection)

### Q081. Which graph algorithms does the backend actually run?

**Spoken answer:** Leiden community detection is the explicit backend graph algorithm. Direct neighbor queries and graph serialization are also used, but there is no implemented PageRank or variable-length impact traversal.

**Technical explanation:** The frontend runs a force simulation for layout, which optimizes display positions rather than inferring code architecture. Algorithm names should be tied to their actual purpose and layer.

**Evidence:** GDS:37; AG:21; UI:363.

**Follow-up:** Does D3 layout validate modules? **Answer:** No. Spatial proximity in a force layout is not independently verified architectural meaning.

**Misconception:** Visualization layout and graph analysis are different computations. **Concept tested:** Algorithm purpose.

### Q082. Why are calls projected as undirected for Leiden?

**Spoken answer:** The configured projection treats all CALLS relationships as undirected to group connectivity. Direction remains in stored CALLS and in other queries.

**Technical explanation:** This can group functions connected by either caller or callee relationships, but loses dependency-layer direction for clustering. It does not convert the persisted database edges into undirected edges.

**Evidence:** GDS:17; ETL:77.

**Follow-up:** What information is lost? **Answer:** Who depends on whom is not distinguished by the clustering input, so a layered architecture may be grouped differently from its dependency design.

**Misconception:** Projection semantics need not equal storage semantics. **Concept tested:** Graph projection.

### Q083. Are call frequencies used as edge weights?

**Spoken answer:** No. The writer records file-scope provenance, and GDS is invoked without a relationshipWeightProperty. It therefore does not weight frequently executed calls.

**Technical explanation:** Repeated call sites are reduced to names/edges, so runtime frequency is not available anyway. source_files records provenance, not counts of invocations or workload intensity.

**Evidence:** ETL:78; GDS:37.

**Follow-up:** Would static call counts equal runtime frequency? **Answer:** No. Loops, branches and actual workloads can change runtime counts by orders of magnitude.

**Misconception:** Multiplicity of syntax is not execution frequency. **Concept tested:** Weight semantics.

### Q084. Why might a utility function distort community detection?

**Spoken answer:** A shared target such as log or get can connect otherwise unrelated groups, especially when simple-name merging combines unrelated APIs.

**Technical explanation:** External nodes participate because the projection matches all Function labels. The graph's topology therefore reflects extraction shortcuts as well as real structure. Excluding or downweighting hubs would be an experimental redesign, not current behavior.

**Evidence:** ETL:72; GDS:18.

**Follow-up:** Should all external nodes be removed? **Answer:** Not automatically; some represent useful integration boundaries. Compare quality with and without them on labeled architecture questions.

**Misconception:** Hub removal is not universally beneficial. **Concept tested:** Topology bias.

### Q085. How do connected components differ from communities?

**Spoken answer:** Components answer whether paths connect nodes; communities seek denser internal structure. A repository can have one large connected component but several useful groups.

**Technical explanation:** Leiden is intended to partition such structure. However, CodeGraph's inferred false edges can make either connectivity or density misleading, so clustering cannot repair the underlying graph.

**Evidence:** GDS:17,37.

**Follow-up:** When would components be enough? **Answer:** For identifying isolated subsystems or disconnected fragments, where density-based partitioning adds little value.

**Misconception:** Connectedness and modular organization are not the same. **Concept tested:** Graph objectives.

### Q086. How would personalized PageRank differ from Leiden for retrieval?

**Spoken answer:** Personalized PageRank could rank nodes near query-selected seeds, whereas Leiden partitions the graph independently during ingestion. It addresses relevance ranking rather than module grouping.

**Technical explanation:** CodeGraph has no PPR implementation or seeded propagation stage. A redesign could combine semantic seeds with bounded graph ranking, but would need correct edges, damping choices and retrieval evaluation.

**Evidence:** AG:266; GDS:53.

**Follow-up:** Would it guarantee higher recall? **Answer:** No. Bad seeds or noisy hubs can spread relevance to the wrong nodes; compare against bounded traversal and vector baselines.

**Misconception:** A different algorithm is not evidence of better answers. **Concept tested:** Query-dependent graph ranking.

### Q087. What does modularity tell you about answer quality?

**Spoken answer:** It describes a graph partition objective, not whether generated architectural explanations are correct. A high score on a flawed graph can still support wrong answers.

**Technical explanation:** The application logs modularity and communityCount but does not compare partitions to known modules or score answers. Numeric algorithm output should not be repurposed as AI accuracy.

**Evidence:** GDS:87; LABEL:17.

**Follow-up:** How would you validate architectural usefulness? **Answer:** Compare retrieved evidence and claims against independently labeled repository architecture across fixed revisions.

**Misconception:** Graph objective quality is not semantic answer quality. **Concept tested:** Metric validity.

### Q088. What happens to isolated functions in the projection?

**Spoken answer:** The projection starts with all scoped Function nodes and uses OPTIONAL MATCH for outgoing calls, so it is designed to include nodes without outgoing relationships.

**Technical explanation:** Zero total functions skips the projection entirely. Isolated definitions and external placeholders still differ semantically, but the clustering stage does not explicitly categorize that difference.

**Evidence:** GDS:12,18,67.

**Follow-up:** Why not use only MATCH for edges? **Answer:** That could omit nodes lacking matching outgoing edges and bias the graph toward connected callers.

**Misconception:** Edge-driven projection can accidentally drop isolated nodes. **Concept tested:** Projection completeness.

## L. Leiden community detection

[All categories](#contents) · [Q089](#q089-explain-leiden-without-claiming-it-understands-software) · [Q090](#q090-why-choose-leiden-rather-than-a-simple-traversal) · [Q091](#q091-how-does-leiden-improve-on-louvain-conceptually) · [Q092](#q092-what-leiden-configuration-does-codegraph-explicitly-set) · [Q093](#q093-are-community-ids-stable-between-ingestions) · [Q094](#q094-how-are-community-names-generated) · [Q095](#q095-what-if-leiden-or-projection-cleanup-fails) · [Q096](#q096-does-the-architecture-tool-retrieve-a-query-specific-leiden-subgraph)

### Q089. Explain Leiden without claiming it understands software.

**Spoken answer:** It groups nodes based on graph connectivity, refining communities and aggregating them across levels. CodeGraph then asks a separate model to label the resulting groups.

**Technical explanation:** The input is Function/CALLS topology, not code semantics or embeddings. Generated module names are interpretations of sampled names/paths, not the algorithm's direct output.

**Evidence:** GDS:37; LABEL:24,86.

**Follow-up:** What does Leiden itself write? **Answer:** A numeric leiden_community property on functions; human-readable labels are a later service.

**Misconception:** Community detection does not generate architectural prose. **Concept tested:** Algorithm/application separation.

### Q090. Why choose Leiden rather than a simple traversal?

**Spoken answer:** Traversal finds reachable or nearby nodes; Leiden addresses a different need—partitioning the whole graph into connectivity groups for an overview.

**Technical explanation:** That is a defensible current rationale, not evidence that the developer benchmarked alternatives. For an exact caller question, the existing one-hop traversal is simpler and more relevant than communities.

**Evidence:** GDS:53; AG:21.

**Follow-up:** Could vector search alone be sufficient? **Answer:** For finding functions by intent, possibly; architecture grouping is a separate hypothesis that needs evaluation.

**Misconception:** More sophisticated algorithms are not necessary for every question. **Concept tested:** Requirement-driven algorithm choice.

### Q091. How does Leiden improve on Louvain conceptually?

**Spoken answer:** Its refinement stage addresses poorly connected communities before aggregation. That motivates its use for topology grouping, but does not certify the repository's module boundaries.

**Technical explanation:** The application's noisy edges and unpinned GDS behavior remain independent concerns. The original Leiden guarantees concern graph partitions under algorithm assumptions, not accurate static code analysis.

**Evidence:** GDS:37; 01_FOUNDATIONS.md section 12.

**Follow-up:** Can you claim CodeGraph proved better partitions than Louvain? **Answer:** No comparative experiment is stored in the repository.

**Misconception:** An algorithm paper's result is not a project benchmark. **Concept tested:** Theoretical versus empirical evidence.

### Q092. What Leiden configuration does CodeGraph explicitly set?

**Spoken answer:** Only the write property. The projection is undirected, and no weight, seed, resolution, iteration or concurrency override is passed.

**Technical explanation:** The code yields communityCount and modularity. Current GDS documentation describes defaults, but the actual plugin version is not pinned or measured in this audit, so runtime defaults must be verified separately.

**Evidence:** GDS:29,37; docker-compose.yml.

**Follow-up:** Does the code explicitly optimize CPM? **Answer:** No. It does not select a CPM option; do not infer that from general Leiden literature.

**Misconception:** General algorithm variants are not application configuration. **Concept tested:** Configuration evidence.

### Q093. Are community IDs stable between ingestions?

**Spoken answer:** No stability guarantee is implemented. Rebuilt graph topology and unstabilized algorithm randomness can change memberships and numeric IDs.

**Technical explanation:** Labels and memberships are replaced after each enrichment run; the frontend uses numbers for color/selection within a loaded graph. They should be snapshot-scoped if used for persistent references.

**Evidence:** GDS:37; LABEL:146; frontend/src/utils/colors.js.

**Follow-up:** Would a fixed random seed solve identity? **Answer:** It can improve reproducibility on identical inputs but does not make IDs semantically stable after graph changes.

**Misconception:** Reproducibility is not persistent identity. **Concept tested:** Derived identifiers.

### Q094. How are community names generated?

**Spoken answer:** The labeler samples up to 15 function names and 5 distinct paths, then requests structured name/description output from gpt-4o-mini at temperature 0.2.

**Technical explanation:** Pydantic checks string lengths/nonblank values, not architectural truth. Requests run sequentially and member sample order is not explicitly sorted before slicing. A refusal or malformed label raises.

**Evidence:** LABEL:24,53,86,128.

**Follow-up:** Can it see full source or every member? **Answer:** No. Its prompt receives only sampled metadata; important exceptions may be omitted.

**Misconception:** Structured output guarantees shape, not factual accuracy. **Concept tested:** Summarization constraints.

### Q095. What if Leiden or projection cleanup fails?

**Spoken answer:** Earlier graph writes remain. The function attempts to drop the named projection in finally, and ingestion emits an error rather than progress 100.

**Technical explanation:** The cleanup attempt can also fail or interact with another same-scope run because graph names are shared. Unit tests verify attempted calls with mocks, not guaranteed live release under every failure.

**Evidence:** GDS:75,99; ETL:318.

**Follow-up:** How would you improve recoverability? **Answer:** Use per-job projection names, durable stage status and snapshot activation after successful validation, with cleanup errors logged separately.

**Misconception:** Finally is not a successful cleanup certificate. **Concept tested:** Resource failure handling.

### Q096. Does the architecture tool retrieve a query-specific Leiden subgraph?

**Spoken answer:** No. It returns stored community labels and function counts for the repository, ordered by size. There is no query embedding or member-source expansion in that tool.

**Technical explanation:** The semantic tool is independent and the frontend graph query is a separate capped view. A true community-routed retrieval pipeline would require new selection/expansion/budget logic.

**Evidence:** AG:74,317; DB:12.

**Follow-up:** How would you test whether such expansion helps? **Answer:** Ablate it against the same graph/model/question set at matched context budgets and score evidence recall and answer quality.

**Misconception:** Possessing communities is not the same as community-guided retrieval. **Concept tested:** Feature boundary verification.

## M. Embeddings and vector search

[All categories](#contents) · [Q097](#q097-what-exactly-does-codegraph-embed) · [Q098](#q098-which-embedding-model-and-dimensions-are-used) · [Q099](#q099-how-is-cosine-similarity-relevant) · [Q100](#q100-why-use-approximate-rather-than-exhaustive-nearest-neighbor-search) · [Q101](#q101-how-does-the-embedding-service-preserve-batch-order) · [Q102](#q102-are-embeddings-reused-across-queries-or-ingestions) · [Q103](#q103-can-structurally-related-code-be-semantically-dissimilar) · [Q104](#q104-what-happens-when-semantic-retrieval-returns-nothing)

### Q097. What exactly does CodeGraph embed?

**Spoken answer:** A short string containing the function's simple name and file path. It stores source bodies, but they are not part of the embedding input.

**Technical explanation:** The function name/path template is built in graph_ops before each batch. There is no chunking of bodies, documentation or graph neighborhoods, so semantic behavior inference is limited by naming quality.

**Evidence:** ETL:208,299.

**Follow-up:** Why might a body-aware model help? **Answer:** It could retrieve behavior hidden behind generic names, but would require privacy, token limits, chunking and benchmark decisions.

**Misconception:** Stored source does not imply embedded source. **Concept tested:** Embedding input design.

### Q098. Which embedding model and dimensions are used?

**Spoken answer:** The code requests text-embedding-3-small and validates each vector has 1,536 elements. The Neo4j vector index is configured to that dimension.

**Technical explanation:** The request does not explicitly set dimensions, but the response guard rejects unexpected shape. Provider availability and actual live vector responses were not tested during this audit.

**Evidence:** EMB:13,36,44; IDX:43.

**Follow-up:** What happens if you change models? **Answer:** You need compatible dimensions/semantics, index migration and re-embedding/versioning; equal dimension alone does not make spaces interchangeable.

**Misconception:** Vector spaces from different models are not automatically comparable. **Concept tested:** Embedding compatibility.

### Q099. How is cosine similarity relevant?

**Spoken answer:** It compares vector directions through normalized dot product. It is a semantic ranking signal, not a probability that a function answers the question correctly.

**Technical explanation:** The Neo4j index uses cosine, and the tool formats returned scores to four decimals. It does not apply a minimum score threshold or calibrated confidence model.

**Evidence:** IDX:47; AG:297.

**Follow-up:** How does Euclidean distance differ? **Answer:** It measures absolute geometric distance and depends on magnitudes; for unit vectors its ranking relates directly to cosine.

**Misconception:** A high similarity score is not a proof of behavior. **Concept tested:** Vector geometry.

### Q100. Why use approximate rather than exhaustive nearest-neighbor search?

**Spoken answer:** An index can avoid comparing the query with every vector, improving scalability at the cost of possible candidate misses. CodeGraph relies on Neo4j's vector index rather than implementing search itself.

**Technical explanation:** No recall benchmark or ANN tuning is recorded. Repository post-filtering can introduce additional misses beyond approximation itself, so quality analysis needs both factors.

**Evidence:** AG:60; IDX:43.

**Follow-up:** How would you measure ANN recall? **Answer:** Compare returned candidates with exact similarity rankings on a fixed vector set, then separately assess task relevance.

**Misconception:** Nearest-neighbor recall and answer correctness are distinct. **Concept tested:** Search approximation.

### Q101. How does the embedding service preserve batch order?

**Spoken answer:** It sorts provider response items by their index and checks count and vector dimension before returning the list. ETL pairs that list with the input batch.

**Technical explanation:** This prevents typical out-of-order response mismatches. Tests return reversed indices to verify reordering; they do not invoke OpenAI or evaluate whether index values themselves are duplicated/invalid.

**Evidence:** EMB:40; backend/tests/test_embedding_service.py:21.

**Follow-up:** What additional validation might help? **Answer:** Require exactly the expected index set and finite numeric vector values before persistence.

**Misconception:** A count check alone is not complete response validation. **Concept tested:** Provider boundary contracts.

### Q102. Are embeddings reused across queries or ingestions?

**Spoken answer:** No content-result cache is implemented. Full reingestion regenerates function vectors, and each semantic search embeds its query again.

**Technical explanation:** Only the AsyncOpenAI client is cached. A result cache would need keys incorporating canonical input, embedding model/version and scope/privacy policy, plus invalidation behavior.

**Evidence:** EMB:17,27; ETL:298.

**Follow-up:** Could caching by function name be safe? **Answer:** No. Paths, source-input policy and model changes alter meaning; same names can represent distinct functions.

**Misconception:** Client caching is not embedding caching. **Concept tested:** Cache correctness.

### Q103. Can structurally related code be semantically dissimilar?

**Spoken answer:** Yes. A generically named utility may be called by many domain-specific functions while its name/path reveals little about their purpose.

**Technical explanation:** Conversely, two similarly named validators can be unrelated in the call graph. CodeGraph offers both signals, but current approximate edges and metadata-only vectors limit each.

**Evidence:** AG:45,266; ETL:208.

**Follow-up:** How should a model combine them? **Answer:** Treat semantic hits as candidates and graph relations as qualified evidence, ideally verify source before asserting behavior.

**Misconception:** Semantic proximity is not a dependency edge. **Concept tested:** Evidence fusion.

### Q104. What happens when semantic retrieval returns nothing?

**Spoken answer:** The tool returns a no-matches string. The agent may try another tool or answer anyway; the application does not enforce abstention or fallback retrieval.

**Technical explanation:** Empty output may mean no relevant metadata, global top-k crowding, missing embeddings or genuine absence. It does not establish that the repository lacks the requested behavior.

**Evidence:** AG:307; AG:84.

**Follow-up:** How would you distinguish these cases? **Answer:** Return structured diagnostics and use exact/alternate retrieval, then report uncertainty rather than interpreting absence as proof.

**Misconception:** No retrieval hit is not proof of no implementation. **Concept tested:** Negative evidence.

## N. Retrieval-augmented generation

[All categories](#contents) · [Q105](#q105-what-is-the-actual-rag-pipeline) · [Q106](#q106-how-is-context-size-controlled) · [Q107](#q107-what-does-the-975-context-reduction-claim-establish) · [Q108](#q108-what-is-included-in-the-baseline-and-context-counts) · [Q109](#q109-could-an-answer-with-no-evidence-show-perfect-efficiency) · [Q110](#q110-how-does-source-attribution-work-today) · [Q111](#q111-why-not-send-the-entire-repository-to-a-large-context-model) · [Q112](#q112-how-would-you-compare-ordinary-rag-with-this-agent)

### Q105. What is the actual RAG pipeline?

**Spoken answer:** The agent selects graph tools; their text becomes model context. Semantic search and community summaries are optional tools, not mandatory consecutive stages.

**Technical explanation:** Only semantic_code_search embeds the query. Architecture reads precomputed labels. There is no automatic source-chunk assembly, graph expansion, reranking or citation checker in the active path.

**Evidence:** AG:343,394.

**Follow-up:** Why call it Graph-RAG at all? **Answer:** Because generation is augmented by retrieved graph-backed observations, while clearly describing the limited implementation.

**Misconception:** An umbrella label must not imply unimplemented stages. **Concept tested:** RAG reconstruction.

### Q106. How is context size controlled?

**Spoken answer:** Some tools have limits—100 direct caller rows and semantic k at most 20—but most structure/dependency/community lists are unbounded. There is no global token-budget truncator.

**Technical explanation:** The context metric is calculated after the agent run, so it does not prevent large prompts or repeated tool outputs during execution. Provider context limits remain external failure boundaries.

**Evidence:** AG:29,279,369,425.

**Follow-up:** Would measuring tokens before a call solve everything? **Answer:** It would help budgeting, but preserving relevant evidence under truncation requires a tested selection policy.

**Misconception:** Post-hoc accounting is not runtime budget enforcement. **Concept tested:** Context management.

### Q107. What does the 97.5% context-reduction claim establish?

**Spoken answer:** The supplied numbers produce about that arithmetic reduction, but no repository benchmark artifacts establish the measurement or its generality. I can defend the implemented metric, not an unsupported experiment.

**Technical explanation:** 737,000 to 18,000 yields 97.56% under two-decimal rounding. The metric excludes prompts, outputs and repeated history billing and uses a proxy tokenizer.

**Evidence:** AG:425; backend/app/utils/tokens.py; README.md.

**Follow-up:** How do you know essential code was not removed? **Answer:** I do not without evidence-recall and answer-quality evaluation on the same questions.

**Misconception:** Context reduction is not accuracy preservation. **Concept tested:** Benchmark interpretation.

### Q108. What is included in the baseline and context counts?

**Spoken answer:** Baseline is supported discovered source text; context is concatenated ToolMessages from the final agent trace. Neither is total provider usage.

**Technical explanation:** Baseline can include files whose parsing later failed and excludes unsupported files. Context excludes system/user/assistant messages and does not sum repeated prompt history across model rounds.

**Evidence:** P:762; AG:369,437.

**Follow-up:** Can the reported efficiency be negative? **Answer:** Yes, if tool text exceeds the stored baseline; with zero baseline savings and efficiency are forced to zero.

**Misconception:** The percentage is not necessarily between zero and one hundred. **Concept tested:** Metric boundary conditions.

### Q109. Could an answer with no evidence show perfect efficiency?

**Spoken answer:** Yes. If the baseline is positive and the agent uses no tools, context_tokens can be zero and efficiency 100%.

**Technical explanation:** This is a counterexample to optimizing the reduction metric as a quality objective. The system does not require tool use, grounded citations or independent factual validation.

**Evidence:** AG:394,442.

**Follow-up:** What metric would catch this? **Answer:** Claim support/groundedness and evidence recall, with correct abstention scored separately.

**Misconception:** Minimal context can mean missing evidence rather than excellent retrieval. **Concept tested:** Metric gaming.

### Q110. How does source attribution work today?

**Spoken answer:** Tools mention names and paths, but final answers have no validated citation contract. The API discards tool traces and returns plain text plus metrics.

**Technical explanation:** No function-source tool is registered. A displayed file name can be invented or ambiguous, and there is no server check that each claim refers to retrieved evidence.

**Evidence:** AG:343,412,467.

**Follow-up:** How would you enforce citations? **Answer:** Assign opaque references to authoritative tool/source results, validate cited IDs and scope/snapshot, and reject or flag unsupported claims.

**Misconception:** Markdown formatting does not create grounding. **Concept tested:** Answer provenance.

### Q111. Why not send the entire repository to a large-context model?

**Spoken answer:** That is a legitimate baseline with broader textual coverage, but can carry cost and irrelevant context. CodeGraph instead exposes reusable compact graph observations.

**Technical explanation:** No measured comparison proves the current approach wins. Preprocessing costs and ephemeral rebuilds may outweigh per-query savings for small or one-off tasks.

**Evidence:** ETL:298,323; AG:425.

**Follow-up:** When might full-source prompting be preferable? **Answer:** For a small repository and a one-time behavior question needing bodies the current tools cannot access.

**Misconception:** Retrieval is a trade-off, not an automatic improvement. **Concept tested:** System-level cost/quality.

### Q112. How would you compare ordinary RAG with this agent?

**Spoken answer:** Hold repository revisions, questions, model and budgets fixed; compare vector-only, graph-only, community-augmented and multi-tool variants using source-verified answers.

**Technical explanation:** The current vectors are metadata-only, so compare a body-vector variant separately rather than silently changing inputs. Record tool paths, evidence recall, unsupported claims, latency and actual usage.

**Evidence:** AG:266,343; ETL:208.

**Follow-up:** Why match context budgets? **Answer:** Otherwise an apparent algorithm advantage may simply reflect receiving more evidence or more model calls.

**Misconception:** Fair ablations require controlled inputs and budgets. **Concept tested:** Experimental design.

## O. LangGraph and agent orchestration

[All categories](#contents) · [Q113](#q113-what-state-does-the-active-agent-carry) · [Q114](#q114-what-causes-the-agent-loop-to-continue-or-stop) · [Q115](#q115-how-are-tool-outputs-returned-to-the-model) · [Q116](#q116-what-happens-if-the-model-names-an-invalid-tool) · [Q117](#q117-what-if-the-model-repeatedly-calls-the-same-tool) · [Q118](#q118-how-are-tool-errors-handled) · [Q119](#q119-why-use-a-prebuilt-agent-rather-than-the-root-custom-stategraph) · [Q120](#q120-does-the-active-agent-have-long-term-memory)

### Q113. What state does the active agent carry?

**Spoken answer:** The prebuilt graph carries a messages sequence and managed remaining-step state. CodeGraph supplies a fresh system/user pair per request and no persistent checkpointer.

**Technical explanation:** It also passes repo_name as an input key, but does not define a custom state schema or inject it into tool signatures. Effective tool scope remains an ordinary model argument.

**Evidence:** AG:394; installed LangGraph chat_agent_executor.py AgentState.

**Follow-up:** Does a cached graph share conversations between users? **Answer:** No conversation persistence is configured; caching the execution graph is different from storing per-thread messages.

**Misconception:** Graph reuse and memory reuse are separate. **Concept tested:** Agent state.

### Q114. What causes the agent loop to continue or stop?

**Spoken answer:** A model response with tool calls routes to tool execution and then back to the model. A response without calls ordinarily becomes the final answer.

**Technical explanation:** Library step-budget logic also bounds graph execution, but the application supplies no explicit per-request recursion or spend budget. Empty final content raises rather than becoming a successful empty response.

**Evidence:** AG:352,394,408; installed prebuilt executor.

**Follow-up:** Could the model stop too early? **Answer:** Yes. There is no application rule requiring enough evidence or a particular tool before answering.

**Misconception:** Loop termination is not answer validation. **Concept tested:** Agent control flow.

### Q115. How are tool outputs returned to the model?

**Spoken answer:** Registered functions return strings that LangGraph wraps as ToolMessages associated with tool calls. These are appended to the message state for the next model invocation.

**Technical explanation:** Some strings encode JSON and others are human-readable lists. They lack a unified entity-reference schema, which complicates precise evidence tracking and frontend linking.

**Evidence:** AG:127,155,332; AG:369.

**Follow-up:** Would JSON alone guarantee reliability? **Answer:** No. It improves parsing only if fields are validated and tied to authoritative scope/identity; factual content still needs checking.

**Misconception:** Structured syntax is not grounded semantics. **Concept tested:** Tool observation contracts.

### Q116. What happens if the model names an invalid tool?

**Spoken answer:** The inspected installed ToolNode generates an error ToolMessage listing available tools. That gives the model an opportunity to correct its choice.

**Technical explanation:** This is library behavior, not custom CodeGraph recovery code. Runtime execution exceptions are handled differently by the default handler and can propagate to the API's 502 path.

**Evidence:** installed langgraph/prebuilt/tool_node.py:1268; M:353.

**Follow-up:** Why pin the library? **Answer:** Error and step defaults can change; reproducible behavior requires locked versions and tests at the contract boundary.

**Misconception:** All tool failures do not have identical recovery behavior. **Concept tested:** Framework defaults.

### Q117. What if the model repeatedly calls the same tool?

**Spoken answer:** There is no application duplicate-call detector, deduplicated context cache or explicit cost ceiling. Execution relies on framework/model stopping behavior and default limits.

**Technical explanation:** The inspected LangGraph runtime's default recursion limit is 10007 unless overridden; that should not be confused with a small practical spend budget. Repeated semantic calls can repeat embedding usage.

**Evidence:** AG:335,394; installed langgraph/_internal/_config.py:32.

**Follow-up:** What guard would you add? **Answer:** Per-request step/time/token limits, repeated-argument detection and bounded observations with a clear exhaustion response.

**Misconception:** A framework limit is not necessarily a safe product budget. **Concept tested:** Agent resource governance.

### Q118. How are tool errors handled?

**Spoken answer:** Tools generally let database/provider exceptions propagate. The installed ToolNode converts invocation errors but rethrows ordinary execution errors by default; chat then maps failures broadly to 502.

**Technical explanation:** No application retry policy distinguishes transient DB errors, provider limits or invalid tool arguments. Library/SDK retries exist separately and are version-dependent.

**Evidence:** AG tool implementations; M:358; installed ToolNode default handler.

**Follow-up:** Should every error be shown to the model? **Answer:** No. Return safe actionable categories for recoverable cases; do not expose secrets or blindly retry irreversible work.

**Misconception:** Tool exceptions are not all harmless observations. **Concept tested:** Failure policy.

### Q119. Why use a prebuilt agent rather than the root custom StateGraph?

**Spoken answer:** The active code uses the prebuilt loop to register seven tools concisely. The root prototype explicitly defines agent/tools nodes for one tool and has different prompts and streaming behavior.

**Technical explanation:** The root code helps explain loop mechanics but is not evidence that the active backend has its temperature setting, source-grounding instruction or SSE implementation.

**Evidence:** AG:335; agent.py:build_agent.

**Follow-up:** Which implementation should an interview walkthrough prioritize? **Answer:** backend/app/agent/graph.py, then the installed prebuilt code for delegated behavior.

**Misconception:** Historical code is not current behavior. **Concept tested:** Architecture versioning.

### Q120. Does the active agent have long-term memory?

**Spoken answer:** No checkpointer, store or conversation-history replay is configured. Each request starts from its current question and a repository-specific system prompt.

**Technical explanation:** The compiled graph is cached and the browser stores messages locally, but neither creates server-side memory. References to earlier turns can therefore be under-specified.

**Evidence:** AG:335,394; HTTP:181.

**Follow-up:** What key should future memory use? **Answer:** Authenticated user/session plus repository and snapshot, with bounded context and privacy/retention controls.

**Misconception:** A conversational interface does not imply a stateful model backend. **Concept tested:** Conversation persistence.

## P. ReAct and tool calling

[All categories](#contents) · [Q121](#q121-what-do-reasoning-action-and-observation-mean-in-this-agent) · [Q122](#q122-when-is-a-multi-tool-sequence-justified) · [Q123](#q123-how-does-dependency-analysis-differ-from-semantic-search) · [Q124](#q124-what-if-the-model-chooses-the-wrong-analysis-tool) · [Q125](#q125-can-the-model-access-a-different-repository-through-a-tool) · [Q126](#q126-why-are-tool-names-potentially-misleading-here) · [Q127](#q127-can-the-current-agent-verify-a-functions-source-implementation) · [Q128](#q128-what-makes-a-tool-result-trustworthy-enough-to-cite)

### Q121. What do reasoning, action and observation mean in this agent?

**Spoken answer:** The model decides what information to request, a registered tool executes the request, and its result becomes an observation for another model response. The application's correctness comes from evidence and controls, not trusting hidden reasoning.

**Technical explanation:** CodeGraph uses structured model tool calls rather than parsing an arbitrary textual Action line. Fixed Python/Cypher executes the action; the model does not submit arbitrary Cypher.

**Evidence:** AG:9,343,352.

**Follow-up:** Does this eliminate hallucinations? **Answer:** No. Tool selection, interpretation and final claims can still be wrong, especially when the graph itself is inaccurate.

**Misconception:** Tool use does not make model inference infallible. **Concept tested:** Agent mechanics.

### Q122. When is a multi-tool sequence justified?

**Spoken answer:** When the question needs different evidence, such as locating a candidate and then examining its callers. A single exact lookup should not require unnecessary agent exploration.

**Technical explanation:** A plausible sequence is semantic search, functions-in-file, incoming callers and outgoing dependencies. The active system does not prescribe or validate this sequence, so it is an example rather than guaranteed behavior.

**Evidence:** AG:162,194,266.

**Follow-up:** How would you detect wasted tool calls? **Answer:** Log structured tool arguments/results and evaluate whether each call adds evidence needed for the answer, alongside cost/latency.

**Misconception:** More tool calls do not necessarily mean deeper understanding. **Concept tested:** Tool efficiency.

### Q123. How does dependency analysis differ from semantic search?

**Spoken answer:** Dependency tools read stored edges for a named function, while semantic search ranks metadata vectors for a natural-language query. They answer different questions.

**Technical explanation:** An edge is a structural assertion with current file-scope provenance; a vector score is learned textual similarity. Neither should silently substitute for source-level verification.

**Evidence:** AG:45,60; ETL:78.

**Follow-up:** Could a semantic hit prove a call relationship? **Answer:** No. It can suggest a function to inspect, not establish an execution edge.

**Misconception:** Similarity is not causality. **Concept tested:** Evidence types.

### Q124. What if the model chooses the wrong analysis tool?

**Spoken answer:** The application has no relevance validator. The model may notice an unhelpful result and recover, or produce a poor answer.

**Technical explanation:** Tool descriptions and architecture-specific prompt guidance influence selection but do not enforce correct routing. A deterministic route for exact caller requests could be more predictable.

**Evidence:** AG:84,103,317.

**Follow-up:** How would you evaluate routing? **Answer:** Use labeled question-to-evidence tasks and score tool choice, arguments, recovery and final answer support, not just successful execution.

**Misconception:** A valid tool call can still be the wrong action. **Concept tested:** Tool-selection quality.

### Q125. Can the model access a different repository through a tool?

**Spoken answer:** The tool schemas accept repo_name and the model supplies it. The prompt asks for the active name, but no request-bound enforcement prevents another valid value.

**Technical explanation:** Cypher then correctly scopes to whichever repository argument it receives. That is query partitioning without authorization or immutable request scope.

**Evidence:** AG:104,141,394.

**Follow-up:** What would a safer schema look like? **Answer:** Omit repo_name from model-visible arguments and inject a server-authorized scope, also validating snapshot and user permissions.

**Misconception:** A scoped query can still be scoped to the wrong repository. **Concept tested:** Authority binding.

### Q126. Why are tool names potentially misleading here?

**Spoken answer:** Blast radius suggests transitive impact, external dependencies suggests packages, and architectural subsystems suggests validated modules. Their implementations are narrower.

**Technical explanation:** The first reads direct callers, the second lists unresolved target names, and the third returns generated community summaries. Precise descriptions and provenance help prevent the model or interviewer from overinterpreting them.

**Evidence:** AG:103,236,317.

**Follow-up:** Should you rename them immediately during this audit? **Answer:** No, this is read-only analysis; I would document limitations and propose clearer contracts for later development.

**Misconception:** Names are not executable specifications. **Concept tested:** Interface semantics.

### Q127. Can the current agent verify a function's source implementation?

**Spoken answer:** Not through its registered tools. The browser source endpoint exists, but none of the seven tools calls it or returns raw_code.

**Technical explanation:** This limits answers about exact branch logic, validation conditions or algorithms inside functions. Names, paths and call edges may suggest behavior without demonstrating it.

**Evidence:** AG:343; DB:34.

**Follow-up:** How would a source tool improve reliability? **Answer:** Return bounded immutable snippets with entity/range references and enforce scope; then validate cited claims against those observations.

**Misconception:** A source viewer for humans is not a source-reading agent capability. **Concept tested:** Capability auditing.

### Q128. What makes a tool result trustworthy enough to cite?

**Spoken answer:** It should identify the repository revision, entity and provenance, and distinguish direct source evidence from inferred or generated information. Current results mostly lack that structure.

**Technical explanation:** A database row can be an accurate read of an inaccurate graph. Validation should preserve how the relation was derived and whether source confirms it before elevating it to a factual claim.

**Evidence:** ETL:78; AG:127; DB:95.

**Follow-up:** Would returning the raw tool trace be sufficient? **Answer:** It improves transparency but still needs stable references, scope checks and claim verification.

**Misconception:** Observation authenticity is not observation correctness. **Concept tested:** Evidence provenance.

## Q. LLM selection and prompt engineering

[All categories](#contents) · [Q129](#q129-which-models-serve-which-roles) · [Q130](#q130-what-instructions-are-in-the-active-system-prompt) · [Q131](#q131-why-is-a-structured-community-label-not-necessarily-accurate) · [Q132](#q132-how-can-prompt-injection-enter-this-application) · [Q133](#q133-why-not-claim-claude-was-chosen-because-it-is-the-most-accurate-model) · [Q134](#q134-does-the-current-code-control-model-temperature-and-output-tokens) · [Q135](#q135-how-are-anthropic-content-blocks-handled) · [Q136](#q136-how-would-you-improve-prompts-without-overstating-their-power)

### Q129. Which models serve which roles?

**Spoken answer:** Claude's configured string is claude-sonnet-5 for chat; OpenAI text-embedding-3-small generates vectors; gpt-4o-mini labels communities. Their roles and data inputs differ.

**Technical explanation:** The active model strings are constants, not user-configurable model selection. Provider availability, latency and accuracy were not measured; root ANTHROPIC_MODEL configuration does not control the active factory.

**Evidence:** AG:339; EMB:13; LABEL:16.

**Follow-up:** Why split providers? **Answer:** The source demonstrates the split, but no recorded comparison explains the original decision; a current rationale is using suitable interfaces for each role.

**Misconception:** Configured model identifiers are not verified live service availability. **Concept tested:** Provider architecture.

### Q130. What instructions are in the active system prompt?

**Spoken answer:** Readable structured Markdown, concise answers, exact repository scope, and use of stored architecture summaries for architecture questions. It does not enforce citations or abstention.

**Technical explanation:** These are behavioral requests to the model. The scope rule is not backed by injected tool arguments, and the output remains unconstrained text rather than validated claims.

**Evidence:** AG:84.

**Follow-up:** What important instruction is missing for reliability? **Answer:** Explicit uncertainty and source-evidence requirements would help, but require tool/provenance/validation support to be enforceable.

**Misconception:** A better prompt alone cannot fix missing data or authorization. **Concept tested:** Prompt versus enforcement.

### Q131. Why is a structured community label not necessarily accurate?

**Spoken answer:** Pydantic validates the name/description shape and lengths, not whether they correctly describe the code. The labeler sees a small metadata sample.

**Technical explanation:** A plausible module title can be generated from generic names or noisy clusters. There is no source check, confidence score or independent architectural label benchmark.

**Evidence:** LABEL:53,86.

**Follow-up:** What should the UI communicate? **Answer:** That these are generated cluster interpretations and that users should inspect supporting code/relationships.

**Misconception:** Schema-valid output is not factually validated output. **Concept tested:** Structured generation limits.

### Q132. How can prompt injection enter this application?

**Spoken answer:** User text and untrusted metadata or generated labels can influence the model. Current tools do not ingest whole README text or source bodies into chat, so the exposure should be described precisely.

**Technical explanation:** Function/path names reach embeddings and labeling, and labels/metadata reach Claude through tools. No explicit injection detector or request-bound scope enforcement exists.

**Evidence:** LABEL:93; AG:93,332.

**Follow-up:** Would adding source retrieval change the risk? **Answer:** Yes. Arbitrary comments/docstrings would increase untrusted text exposure and require clear instruction/evidence separation and enforceable tool policies.

**Misconception:** Not every repository file currently reaches the agent. **Concept tested:** Prompt trust boundaries.

### Q133. Why not claim Claude was chosen because it is the most accurate model?

**Spoken answer:** There is no comparative evaluation in the repository supporting that claim. I can describe the configured integration and propose a benchmark for model selection.

**Technical explanation:** Model quality depends on questions, tools, context and cost constraints. Graph correctness and missing source retrieval can dominate any provider difference.

**Evidence:** AG:339; README.md limitations.

**Follow-up:** What is a defensible interview answer? **Answer:** “I integrated a tool-capable model; I would choose or revisit it using repository-specific accuracy, latency and cost measurements.”

**Misconception:** Vendor reputation is not project evidence. **Concept tested:** Decision honesty.

### Q134. Does the current code control model temperature and output tokens?

**Spoken answer:** The community labeler sets temperature 0.2. The active ChatAnthropic factory does not explicitly set temperature, max_tokens, timeout or a per-request token budget.

**Technical explanation:** Installed SDK defaults and model behavior may supply limits, but those are not project-specific guarantees. The root prototype's temperature zero must not be attributed to this path.

**Evidence:** LABEL:87; AG:339; agent.py:build_agent.

**Follow-up:** What should be configured for production? **Answer:** Explicit time/output/step/spend policies with tested failure responses and recorded provider usage.

**Misconception:** Defaults are not a deliberate resource policy. **Concept tested:** Model configuration.

### Q135. How are Anthropic content blocks handled?

**Spoken answer:** The helper returns strings directly or joins text fields from list-of-dictionary blocks. Nontext content is discarded for the API answer.

**Technical explanation:** It checks for nonempty final text, not source-grounding or a structured final-answer type. Tool messages are collected separately only for context counting, then omitted from the public response.

**Evidence:** AG:355,408,467.

**Follow-up:** Could useful metadata be lost? **Answer:** Yes, references or nontext blocks are not preserved in the simple response contract unless explicitly added later.

**Misconception:** Text extraction is not full model-response interpretation. **Concept tested:** Output normalization.

### Q136. How would you improve prompts without overstating their power?

**Spoken answer:** Make tool limitations explicit, ask for uncertainty when evidence is absent, and distinguish source facts, inferred edges and generated labels. Pair this with enforceable scope and citation contracts.

**Technical explanation:** Prompt-only changes cannot separate merged functions or expose code the tools never return. Evaluation should measure whether the revised instructions reduce unsupported claims at comparable budgets.

**Evidence:** AG:84; ETL:55,178.

**Follow-up:** What would you test first? **Answer:** Ambiguous names, empty retrieval, architecture labels with misleading metadata and wrong-scope requests.

**Misconception:** Instruction compliance must be evaluated, not assumed. **Concept tested:** Prompt evaluation.

## R. AI reliability and evaluation

[All categories](#contents) · [Q137](#q137-how-do-you-know-the-ai-agent-is-accurate) · [Q138](#q138-how-would-you-measure-hallucinations) · [Q139](#q139-what-happens-when-retrieval-misses-an-important-dependency) · [Q140](#q140-how-would-you-build-a-benchmark-for-codegraph) · [Q141](#q141-how-would-you-prove-leiden-improves-retrieval) · [Q142](#q142-which-production-metrics-matter-beyond-token-counts) · [Q143](#q143-how-should-the-system-handle-unanswerable-questions) · [Q144](#q144-how-do-parser-defects-affect-evaluation-of-the-llm)

### Q137. How do you know the AI agent is accurate?

**Spoken answer:** I have tests for selected parser, API and tool behavior, but no comprehensive answer-accuracy benchmark. The agent can be confidently wrong.

**Technical explanation:** Most agent tests mock model/database outputs and assert formatting or registration. They do not evaluate real tool choice, source support or factual correctness across repositories.

**Evidence:** backend/tests/test_agent_tools.py; AG:425.

**Follow-up:** What would you do next? **Answer:** Create fixed-SHA questions with independently verified evidence and score claims, retrieval and abstention across controlled variants.

**Misconception:** Passing integration plumbing tests is not an AI quality evaluation. **Concept tested:** Validation scope.

### Q138. How would you measure hallucinations?

**Spoken answer:** Break answers into material claims and check whether each is supported or contradicted by authoritative source at the indexed revision. Report unsupported-claim rates and severity.

**Technical explanation:** A graph edge alone may be insufficient because current edges are inferred. Judges should distinguish graph-reporting accuracy from actual code-behavior accuracy and adjudicate ambiguous cases.

**Evidence:** ETL:78; AG:412.

**Follow-up:** Can an LLM judge do this alone? **Answer:** It can assist, but calibrate against independent human/source review and record disagreement rather than treating it as infallible.

**Misconception:** Fluent answers and self-confidence are not grounding metrics. **Concept tested:** Claim-level evaluation.

### Q139. What happens when retrieval misses an important dependency?

**Spoken answer:** The current system may omit it or produce an overconfident answer; there is no coverage check forcing uncertainty. Misses can arise in parsing, graph construction, tool limits or vector candidates.

**Technical explanation:** A direct-caller cap and vector post-filter can hide evidence even when it exists in the database. Evaluating only returned-result precision would miss this recall problem.

**Evidence:** AG:29,60; P:25.

**Follow-up:** How would you improve recall safely? **Answer:** Use richer evidence and bounded expansion/fallbacks, then measure recall and noise rather than maximizing context indiscriminately.

**Misconception:** Absence from retrieved context is not absence from the codebase. **Concept tested:** Retrieval failure propagation.

### Q140. How would you build a benchmark for CodeGraph?

**Spoken answer:** Fix repository SHAs, create realistic questions and gold source ranges, include unsupported/ambiguous cases, and keep held-out repositories/questions separate from tuning.

**Technical explanation:** Cover all supported languages, duplicate names, callbacks, dynamic calls and multiple sizes. Store accepted claims and uncertainty expectations, not only one exact answer string.

**Evidence:** P:25; backend/tests/test_function_identity.py.

**Follow-up:** Why avoid exact wording assertions? **Answer:** Many accurate answers can phrase the same evidence differently; scoring should focus on claims and required evidence.

**Misconception:** Answer variation is not necessarily factual error. **Concept tested:** Benchmark design.

### Q141. How would you prove Leiden improves retrieval?

**Spoken answer:** Run an ablation with and without community information on the same graph, model, questions and context budget. Measure evidence recall and answer quality, not just smaller prompts.

**Technical explanation:** Current architecture tools return summaries without member expansion; an expanded community pipeline would be a distinct experimental variant. Fixing graph identity simultaneously would confound attribution.

**Evidence:** GDS:37; AG:317.

**Follow-up:** What if context shrinks but recall falls? **Answer:** Report the trade-off and choose based on task requirements; do not label the reduction an unconditional improvement.

**Misconception:** Context compression does not prove useful information retention. **Concept tested:** Controlled ablations.

### Q142. Which production metrics matter beyond token counts?

**Spoken answer:** Stage failures, tool success/invalid-call rates, p50/p95 latency, actual provider spend, queue/resource usage and sampled groundedness/answer correctness.

**Technical explanation:** Metrics should include ingestion coverage and stale/partial snapshots because answer quality depends on upstream data. Privacy-safe traces need repository/version and tool provenance without unnecessary sensitive content.

**Evidence:** M:376; AG:425; PIPE:233.

**Follow-up:** What does the current metrics object omit? **Answer:** Provider usage, latency, cost, accuracy and retrieval recall; it only compares baseline and tool-text tokens.

**Misconception:** One efficiency percentage is not production observability. **Concept tested:** Operational and semantic monitoring.

### Q143. How should the system handle unanswerable questions?

**Spoken answer:** It should distinguish absent evidence from absent behavior and say what it cannot establish. The current application does not enforce that policy.

**Technical explanation:** A future answer contract could include supported claims, evidence references and unresolved questions. Evaluation should reward appropriate abstention rather than treating every non-answer as failure.

**Evidence:** AG:84,307,408.

**Follow-up:** Could excessive abstention look good on hallucination rate? **Answer:** Yes, so measure answer coverage and usefulness alongside unsupported-claim rates.

**Misconception:** One quality metric can be optimized at another's expense. **Concept tested:** Calibration and coverage.

### Q144. How do parser defects affect evaluation of the LLM?

**Spoken answer:** They change the evidence available, so a wrong answer may originate upstream rather than in generation. Evaluation should attribute errors by stage.

**Technical explanation:** Use gold source relationships, extracted records, persisted graph rows, retrieved observations and final claims as checkpoints. Current same-name merging and file-scope calls are concrete upstream error sources.

**Evidence:** P:464; ETL:123; AG:369.

**Follow-up:** Why does that matter for improvements? **Answer:** It prevents spending on a stronger model when fixing data identity would address the real failure.

**Misconception:** All AI-system errors are not model errors. **Concept tested:** Error decomposition.

## S. Security and trust boundaries

[All categories](#contents) · [Q145](#q145-does-repository-scoping-prevent-one-user-accessing-another-users-code) · [Q146](#q146-how-is-the-webhook-signature-computed-and-checked) · [Q147](#q147-are-webhook-replay-attacks-prevented) · [Q148](#q148-what-prevents-a-malicious-repository-from-executing-code-during-ingestion) · [Q149](#q149-could-this-application-suffer-denial-of-service-from-a-large-repository) · [Q150](#q150-does-graph-payload-redaction-protect-private-source) · [Q151](#q151-what-is-the-prompt-injection-impact-of-malicious-repository-instructions) · [Q152](#q152-how-would-you-handle-secrets-and-dependency-security-before-deployment)

### Q145. Does repository scoping prevent one user accessing another user's code?

**Spoken answer:** No. There is no user authentication or ownership check, and clients can submit any canonical repo_name. Scoping separates query data but does not authorize access.

**Technical explanation:** The source endpoint, chat, graph and delete routes all lack an authenticated principal. A server GitHub token can import private code that then becomes reachable through these APIs.

**Evidence:** M:209,248,328,349; GH:29.

**Follow-up:** What is the first production control? **Answer:** Enforce principal-to-repository permissions on every route and inject authorized scope into tools.

**Misconception:** CORS and scope strings are not multi-tenant security. **Concept tested:** Authorization.

### Q146. How is the webhook signature computed and checked?

**Spoken answer:** The server HMACs exact raw body bytes with SHA-256 and the shared secret, prefixes the hex digest with sha256=, then uses compare_digest against the header.

**Technical explanation:** JSON parsing happens after authentication. Changing whitespace changes signed bytes. Missing/invalid signature yields 401; valid signature with malformed/non-object JSON yields 400.

**Evidence:** SIG:21; HOOK:39.

**Follow-up:** Why constant-time comparison? **Answer:** It avoids ordinary comparison timing that can reveal where values first differ; it does not fix weak secrets or replay.

**Misconception:** HMAC is authentication/integrity, not encryption. **Concept tested:** Message authentication.

### Q147. Are webhook replay attacks prevented?

**Spoken answer:** No delivery ID or freshness record is checked. A previously valid signed body can be submitted again and accepted.

**Technical explanation:** Even legitimate retries can repeat background merges and model enrichment. The event header controls processing but is not included in the body HMAC, so event authorization should also be explicit.

**Evidence:** SIG:21; HOOK:38; PIPE:111.

**Follow-up:** What would you add? **Answer:** Persist delivery identifiers/outcomes, enforce allowed repository/event policies and make job processing idempotent.

**Misconception:** A valid signature does not prove a request is new. **Concept tested:** Replay resistance.

### Q148. What prevents a malicious repository from executing code during ingestion?

**Spoken answer:** The active path reads bytes and parses syntax; it does not import, build or run repository code. That reduces direct execution risk.

**Technical explanation:** It still processes untrusted ZIP data and native parser input with no size/time sandbox. Resource exhaustion or parser vulnerabilities need separate controls, and no vulnerability scan was performed here.

**Evidence:** GH:38; P:610.

**Follow-up:** Would antivirus-style scanning replace limits? **Answer:** No. Byte/member/time quotas and process isolation address different risks than known-malware detection.

**Misconception:** Not executing code does not make all input processing harmless. **Concept tested:** Untrusted input processing.

### Q149. Could this application suffer denial of service from a large repository?

**Spoken answer:** Yes, source inspection shows unbounded archive/file sizes, all task allocation, full result retention and potentially inflated call rows. No global user/job quotas exist.

**Technical explanation:** A per-ingest 32-slot semaphore and 100-row DB batch limit only portions of the work. Many concurrent ingestions or large community counts can also create provider spending pressure.

**Evidence:** GH:90; P:789; ETL:178,298.

**Follow-up:** What controls are most useful? **Answer:** Total bytes/files, expanded archive ratio, active-job admission, per-tenant budgets and durable scheduling.

**Misconception:** A local concurrency limit is not comprehensive resource protection. **Concept tested:** Resource threat modeling.

### Q150. Does graph payload redaction protect private source?

**Spoken answer:** It reduces unnecessary bulk exposure, but an unauthenticated source endpoint intentionally returns code by ID and scope. Metadata may also be sensitive.

**Technical explanation:** The browser graph omits raw_code/embedding yet retains names/paths/communities. OpenAI receives metadata for embeddings/labels; Claude receives selected tool output. These flows need explicit product privacy policy.

**Evidence:** DB:98,213; LABEL:93; AG:369.

**Follow-up:** Would encrypting the database solve API access? **Answer:** No. At-rest encryption does not authorize clients reading through the application.

**Misconception:** Data minimization, encryption and authorization solve different problems. **Concept tested:** Data protection layers.

### Q151. What is the prompt-injection impact of malicious repository instructions?

**Spoken answer:** Current README text is not indexed for the agent, but names/paths and generated labels can still carry adversarial content. Future source retrieval would broaden the surface.

**Technical explanation:** There is no general command-execution tool, which limits direct effects. Wrong-scope retrieval and unsupported claims remain possible because model arguments and text are not independently constrained by authorization/grounding checks.

**Evidence:** P:25; LABEL:93; AG:343.

**Follow-up:** What should not be entrusted to the model? **Answer:** Whether a user can access a repository, whether to spend beyond a budget, or whether a destructive action is authorized.

**Misconception:** No shell tool does not mean no prompt-injection risk. **Concept tested:** LLM trust containment.

### Q152. How would you handle secrets and dependency security before deployment?

**Spoken answer:** Replace development credentials, use controlled secret injection/rotation, lock dependencies and test compatible Neo4j/GDS versions. Then scan and assess actual vulnerabilities rather than inventing CVE claims.

**Technical explanation:** The repository ignores local env files but contains development defaults and unpinned Python requirements; GDS resolves at startup. These are reproducibility/exposure concerns, not evidence of a specific exploit.

**Evidence:** backend/app/config.py; IDX:16; docker-compose.yml; backend/requirements.txt.

**Follow-up:** Does a lockfile eliminate vulnerabilities? **Answer:** No. It makes versions reproducible so updates and vulnerability assessment can be deliberate.

**Misconception:** Reproducible dependencies are not automatically secure dependencies. **Concept tested:** Supply-chain hygiene.

## T. Testing and Postman

[All categories](#contents) · [Q153](#q153-how-many-tests-are-present-at-the-analyzed-revision) · [Q154](#q154-what-do-the-parser-tests-prove-and-not-prove) · [Q155](#q155-why-are-mocked-database-tests-useful) · [Q156](#q156-what-does-the-postman-repository-workflow-automate) · [Q157](#q157-how-does-postman-validate-webhook-hmac-behavior) · [Q158](#q158-do-the-node-tests-validate-react-rendering) · [Q159](#q159-what-does-the-token-metrics-unit-test-actually-assert) · [Q160](#q160-what-is-the-highest-value-missing-test-category)

### Q153. How many tests are present at the analyzed revision?

**Spoken answer:** The active backend has 96 parametrized cases: 92 passed and four live-DB tests were skipped in this network-disabled audit. The frontend has 13 passing Node cases.

**Technical explanation:** The saved backend venv initially lacked dependencies, so temporary dependencies were overlaid without changing it. Root legacy webhook tests are separate; historical 77 or supplied 82 counts do not describe HEAD.

**Evidence:** backend/tests; frontend/src/*.test.js; 06_EVIDENCE.md.

**Follow-up:** What do the four skips mean? **Answer:** Persistent database integration was deliberately not exercised; they are not passes and do not imply database correctness.

**Misconception:** Counting functions is not always counting parametrized test cases. **Concept tested:** Test evidence.

### Q154. What do the parser tests prove and not prove?

**Spoken answer:** They verify selected language constructs, snippets, identity distinctions, lexical ownership and failure handling. They do not prove every valid program or runtime target is correctly analyzed.

**Technical explanation:** Token counting is mocked in parser batch tests. Identity cases use actual grammar parsing, but persistence remains legacy; a passing parser test cannot validate the graph migration that has not happened.

**Evidence:** backend/tests/test_parser_service.py; backend/tests/test_function_identity.py.

**Follow-up:** What fixture would you add for graph fidelity? **Answer:** A disposable end-to-end duplicate-name/nested-call repository with exact expected stored nodes and edges.

**Misconception:** Parser correctness and database fidelity need separate tests. **Concept tested:** Layered verification.

### Q155. Why are mocked database tests useful?

**Spoken answer:** They verify query parameters, batching, serialization and failure cleanup quickly and without external services. They make contract failures easy to isolate.

**Technical explanation:** They cannot prove Cypher syntax compatibility, transaction isolation, index plans or actual GDS behavior. The skipped live tests cover some basic persistence but still mock embeddings and clustering.

**Evidence:** backend/tests/test_graph_scoping.py; backend/tests/test_pipeline.py.

**Follow-up:** How would you test SEARCH compatibility? **Answer:** Run the exact query/index against a pinned disposable Neo4j/Cypher version with known vectors and multiple scopes.

**Misconception:** Mock success is not live database success. **Concept tested:** Test doubles.

### Q156. What does the Postman repository workflow automate?

**Spoken answer:** Health, ingestion, graph retrieval, source lookup, chat, deletion and verification of an empty graph. It carries canonical scope, baseline and function identifiers between requests.

**Technical explanation:** Scripts parse NDJSON and reject terminal error records even with HTTP 200. Chat assertions check nonempty text and metric arithmetic, not answer truth; cleanup mutates the selected scope.

**Evidence:** postman/collections/codegraph-api.postman_collection.json; postman/README.md.

**Follow-up:** Why not run it during this audit? **Answer:** It would make provider calls and delete graph data, outside the read-only investigation constraint.

**Misconception:** An executable workflow is not proof it was executed here. **Concept tested:** Black-box test boundaries.

### Q157. How does Postman validate webhook HMAC behavior?

**Spoken answer:** Its pre-request script signs exact transmitted bytes and runs six valid/invalid/changed-body/JSON-shape cases. The benign valid event is ping with no useful repository work.

**Technical explanation:** The script uses Web Crypto with a compatibility fallback and a private local secret. HTTP 202 confirms acknowledgement, not successful background indexing; no completion polling exists.

**Evidence:** postman collection folder 03; SIG:21.

**Follow-up:** Why sign malformed JSON in a negative test? **Answer:** To isolate JSON validation after authentication rather than failing earlier at the signature boundary.

**Misconception:** Negative tests should isolate the intended failure layer. **Concept tested:** Security contract testing.

### Q158. Do the Node tests validate React rendering?

**Spoken answer:** No. They cover API helpers, NDJSON chunk handling, scope propagation, cleanup and community utilities. The production build verifies bundling, not browser behavior.

**Technical explanation:** No component/browser test suite was found for graph layout, source-panel races, hover/cluster interactions or accessibility. The successful build still reports a large JS chunk.

**Evidence:** frontend/src/api.test.js; frontend/src/communities.test.js; frontend/package.json.

**Follow-up:** What would you add next? **Answer:** Deferred-request race tests and browser scenarios for ingestion, selection, cancellation and stale graph responses.

**Misconception:** Build success is not UI correctness. **Concept tested:** Frontend test layers.

### Q159. What does the token-metrics unit test actually assert?

**Spoken answer:** It supplies mocked agent messages, token count and baseline, then checks the returned arithmetic. It proves the code path's calculation, not measured savings on a repository.

**Technical explanation:** The tokenizer tests mock encoders and check selection/fallback behavior. No stored raw 737k/18k experiment or independent quality score accompanies the metric.

**Evidence:** backend/tests/test_agent_tools.py:298; backend/tests/test_tokens.py.

**Follow-up:** What artifact would make the benchmark defensible? **Answer:** Fixed inputs and revisions, raw transcripts/counts, methodology and quality/cost comparisons.

**Misconception:** A formula test is not a performance experiment. **Concept tested:** Measurement validation.

### Q160. What is the highest-value missing test category?

**Spoken answer:** End-to-end graph fidelity and AI evidence quality, especially duplicate names, true call ownership and unsupported answers. Concurrency/security tests are also essential before shared deployment.

**Technical explanation:** Current tests often protect intended legacy contracts, including approximate ETL, rather than asserting compiler-grade semantics. A failing new fidelity fixture may reveal a known limitation rather than a regression.

**Evidence:** ETL:178; backend/tests/test_graph_scoping.py.

**Follow-up:** Should you replace all unit tests with end-to-end tests? **Answer:** No. Keep fast focused checks and add a small controlled integration/evaluation layer for cross-system properties.

**Misconception:** More integration tests alone do not replace targeted unit coverage. **Concept tested:** Risk-based test strategy.

## U. Deployment and scalability

[All categories](#contents) · [Q161](#q161-what-is-actually-containerized) · [Q162](#q162-what-would-struggle-with-a-million-line-repository) · [Q163](#q163-how-would-you-support-hundreds-of-concurrent-users) · [Q164](#q164-how-would-you-implement-incremental-indexing-properly) · [Q165](#q165-where-would-you-introduce-distributed-processing) · [Q166](#q166-how-would-you-reduce-operational-costs) · [Q167](#q167-what-is-required-for-enterprise-monorepositories) · [Q168](#q168-how-would-you-design-observability-for-this-system)

### Q161. What is actually containerized?

**Spoken answer:** Only the Neo4j development service is defined in Compose. The backend and frontend are run separately; no application Dockerfile or deployment manifest was found.

**Technical explanation:** Compose pins Neo4j 2026.07.1, exposes Browser/Bolt ports, persists a volume and installs GDS through the plugin mechanism. It is not a fully locked production service stack.

**Evidence:** docker-compose.yml; README.md Quick start.

**Follow-up:** What must a deployment add? **Answer:** Application packaging, configuration, readiness, auth/TLS, retention, quotas and tested compatible database/plugin versions.

**Misconception:** A Docker Compose database is not a complete deployment. **Concept tested:** Deployment inventory.

### Q162. What would struggle with a million-line repository?

**Spoken answer:** Archive/source buffering, same-language parse serialization, call-row inflation, repeated embeddings, full GDS projection and sequential community labeling are likely pressure points.

**Technical explanation:** The graph API then returns only a capped view, and the browser runs synchronous layout. These are source-based hypotheses; no million-line workload was benchmarked here.

**Evidence:** GH:90; P:690; ETL:178; LABEL:128; DB:31.

**Follow-up:** Which change comes first? **Answer:** Correct identity/call modeling and introduce byte/job budgets so scale does not amplify incorrect data or uncontrolled resource use.

**Misconception:** Scale claims need workload measurements. **Concept tested:** Bottleneck analysis.

### Q163. How would you support hundreds of concurrent users?

**Spoken answer:** First add authenticated ownership, retained snapshots and durable jobs with global/tenant admission control. More API workers alone would worsen current cleanup and race problems.

**Technical explanation:** Per-request semaphores do not cap aggregate work, and startup deletes scoped graphs. Cached agents/clients are process-local; provider and database capacity need coordinated budgets.

**Evidence:** M:60; P:753; AG:335.

**Follow-up:** How would you protect interactive latency? **Answer:** Separate ingestion workers from query serving, use queues and resource limits, then measure p95 latency under mixed load.

**Misconception:** Throughput scaling cannot ignore correctness and fairness. **Concept tested:** Multi-user architecture.

### Q164. How would you implement incremental indexing properly?

**Spoken answer:** Persist commit/snapshot and per-file hashes, reconcile additions/deletions/renames, update identities/call references, and publish only a complete validated generation.

**Technical explanation:** Reuse embeddings based on exact input/model hashes and revisit dependent resolutions when definitions change. Communities may need recomputation or a documented incremental approximation, not silent stale reuse.

**Evidence:** PIPE:23,219; ETL:238.

**Follow-up:** Why isn't changed-file MERGE enough? **Answer:** It never removes obsolete facts and cannot safely distinguish branches or concurrent revisions.

**Misconception:** Incremental updates require negative information too. **Concept tested:** Index maintenance.

### Q165. Where would you introduce distributed processing?

**Spoken answer:** Only after jobs and immutable snapshot inputs are defined and profiling identifies a bottleneck. Parsing/enrichment can be worker stages with bounded queues and retryable outputs.

**Technical explanation:** Distributed workers require idempotency, result storage, per-repository ordering and cancellation state. Sending the current mutable repo_name-only workflow to many workers would amplify races.

**Evidence:** M:376; ETL:278; GDS:74.

**Follow-up:** What should a worker key include? **Answer:** Tenant/repository, immutable revision, stage and input/model version, rather than only a display repository name.

**Misconception:** Distribution is not a substitute for data contracts. **Concept tested:** Distributed job design.

### Q166. How would you reduce operational costs?

**Spoken answer:** Retain reusable snapshots, cache embeddings/labels by input and model, bound agent rounds/results and use deterministic routes for simple exact queries. Measure actual provider usage first.

**Technical explanation:** Current full reingestion repeats enrichment and startup/unload deletion limits amortization. The context percentage excludes preprocessing, generated output and repeated history, so it is not a cost ledger.

**Evidence:** ETL:298,323; M:66; AG:425.

**Follow-up:** Could graph preprocessing cost more than it saves? **Answer:** Yes, especially for one-off small repositories or frequent rebuilds; compare total cost over expected query volume.

**Misconception:** Per-query context savings are not total-system savings. **Concept tested:** Cost modeling.

### Q167. What is required for enterprise monorepositories?

**Spoken answer:** Configurable indexing scope, more reliable symbol resolution, durable revisions, tenant authorization, resource quotas, auditability and evaluated retrieval quality. Current supported-language syntax extraction is only a starting point.

**Technical explanation:** Generated code, mixed build systems, submodules, large assets and cross-language boundaries complicate coverage. No universal language-server or build-aware analysis is implemented.

**Evidence:** P:25; M:154; ETL:55.

**Follow-up:** Would increasing the graph response limit solve exploration? **Answer:** No. Targeted neighborhoods, search and aggregation are needed to avoid overwhelming both query and rendering stages.

**Misconception:** Monorepo support is more than handling more files. **Concept tested:** Enterprise requirements.

### Q168. How would you design observability for this system?

**Spoken answer:** Assign job/request/snapshot IDs and measure stage durations, resource usage, coverage, tool calls, provider usage and failures. Add sampled claim-quality audits separately.

**Technical explanation:** Current logs include stages/token counts/modularity but no structured distributed trace or job status store. Sensitive source should not be logged indiscriminately while adding diagnostics.

**Evidence:** M:439; GDS:92; AG:458; PIPE:233.

**Follow-up:** What alert would matter most during ingestion? **Answer:** Stuck/failed jobs, resource saturation and repeated provider/database failures, tied to user-visible status and safe retry policy.

**Misconception:** Verbose logs are not complete observability. **Concept tested:** Operational diagnosis.

## V. Architectural decisions

[All categories](#contents) · [Q169](#q169-why-fastapi-rather-than-a-simpler-synchronous-framework) · [Q170](#q170-why-python-instead-of-go-java-or-typescript) · [Q171](#q171-why-tree-sitter-rather-than-regex) · [Q172](#q172-why-neo4j-instead-of-networkx) · [Q173](#q173-why-react-flow-rather-than-drawing-the-graph-manually) · [Q174](#q174-why-ndjson-instead-of-websockets) · [Q175](#q175-why-an-agent-instead-of-a-fixed-retrieval-pipeline) · [Q176](#q176-what-architectural-choice-would-you-reverse-first)

### Q169. Why FastAPI rather than a simpler synchronous framework?

**Spoken answer:** Its validation, async service calls and streaming fit this API. That is a current engineering rationale, not proof of a historical framework comparison.

**Technical explanation:** The benefits depend on correct offloading and lifecycle design; synchronous parsing or large in-memory transforms can still block. Auth, job durability and database consistency remain application responsibilities.

**Evidence:** M:14,191,534; P:690.

**Follow-up:** When would another framework be preferable? **Answer:** When built-in auth/admin/ORM conventions or an existing team stack outweigh the async prototype advantages.

**Misconception:** Framework choice does not supply missing product guarantees. **Concept tested:** Framework trade-offs.

### Q170. Why Python instead of Go, Java or TypeScript?

**Spoken answer:** It offers the parsing, model and graph libraries used here with concise orchestration. The trade-offs include runtime dependency management and CPU/concurrency limitations.

**Technical explanation:** The code already mixes native grammar/tokenizer work with Python extraction. A rewrite should follow measured bottlenecks and maintenance requirements rather than assume compiled languages automatically fix algorithmic call inflation.

**Evidence:** backend/requirements.txt; P:601; ETL:178.

**Follow-up:** What could be moved independently? **Answer:** A profiled parsing worker can change implementation behind a stable record contract without rewriting the entire UI/API.

**Misconception:** Language speed does not repair poor data modeling. **Concept tested:** Implementation language choice.

### Q171. Why Tree-sitter rather than regex?

**Spoken answer:** Grammar-based nodes and spans distinguish definitions and call syntax more reliably across the supported languages. Regex alone would struggle with nesting and language syntax.

**Technical explanation:** Tree-sitter still needs carefully chosen queries and semantic resolution beyond parsing. The current application does not gain import/type analysis simply by using a real parser.

**Evidence:** P:36,55,84,122,145.

**Follow-up:** When is regex appropriate? **Answer:** For narrow lexical patterns where full syntactic relationships are unnecessary and limitations are explicit.

**Misconception:** Avoiding regex does not imply compiler-grade analysis. **Concept tested:** Parsing technology selection.

### Q172. Why Neo4j instead of NetworkX?

**Spoken answer:** Neo4j gives persistent shared graph queries plus integrated vectors and GDS. NetworkX could serve a smaller single-process prototype but needs separate persistence and service design.

**Technical explanation:** Current queries are mostly direct neighbors, so Neo4j's value depends substantially on integrated storage/algorithms. Its operational/plugin complexity should be justified by evaluated needs.

**Evidence:** DB:52; GDS:37; IDX:43.

**Follow-up:** Would NetworkX eliminate concurrency problems? **Answer:** No. Shared mutable state, persistence and multi-user lifecycle would still require deliberate design.

**Misconception:** An in-memory library is not a complete database service. **Concept tested:** Graph platform choice.

### Q173. Why React Flow rather than drawing the graph manually?

**Spoken answer:** It provides custom React nodes, handles, controls and interactive viewport behavior. CodeGraph still supplies its own normalization, layout and styling logic.

**Technical explanation:** For much larger datasets a canvas/WebGL renderer might reduce DOM costs, but that requires different interaction/accessibility design. Current performance has not been benchmarked at large scale.

**Evidence:** UI:10,363,1402.

**Follow-up:** What part is not provided by React Flow here? **Answer:** The 300-tick D3 force layout and application-specific cluster/neighbor emphasis.

**Misconception:** Using a visualization library does not eliminate layout engineering. **Concept tested:** Frontend library boundaries.

### Q174. Why NDJSON instead of WebSockets?

**Spoken answer:** The implemented need is one-way progress for a POST request, which NDJSON handles with simple line framing. Bidirectional messaging is not currently required.

**Technical explanation:** WebSockets would add connection/session complexity without making jobs durable. SSE is another viable stream format, while polling requires a status store the application lacks.

**Evidence:** M:370,534; HTTP:52.

**Follow-up:** When would you reconsider? **Answer:** For bidirectional interactive control or standard event reconnection, after defining persistent job semantics.

**Misconception:** Transport choice does not solve workflow state. **Concept tested:** Protocol selection.

### Q175. Why an agent instead of a fixed retrieval pipeline?

**Spoken answer:** Open-ended exploration can require different evidence sequences, so model-directed tools provide flexibility. Exact questions could be routed deterministically for predictability.

**Technical explanation:** The agent adds latency, cost and routing/interpretation failure modes. A hybrid design would reserve agent orchestration for questions that benefit from it and enforce budgets/scope externally.

**Evidence:** AG:343,394.

**Follow-up:** What question should be deterministic? **Answer:** Direct callers of an already-resolved function ID is an obvious candidate.

**Misconception:** Agentic behavior is not inherently superior to ordinary logic. **Concept tested:** Automation scope.

### Q176. What architectural choice would you reverse first?

**Spoken answer:** I would replace simple-name persistence and file-wide call assignment with canonical identities and explicit unresolved call evidence. That addresses misleading results across multiple features.

**Technical explanation:** The migration must update constraints, ETL, tools, source lookup and UI references together. Merely changing MERGE while leaving name-based queries would produce incomplete or ambiguous reads.

**Evidence:** ETL:55,178; backend/FUNCTION_IDENTITY.md.

**Follow-up:** What trade-off does that introduce? **Answer:** A richer schema and resolver increase complexity, but make uncertainty and entity identity explicit rather than hidden in merged nodes.

**Misconception:** A stronger model is not the first fix for corrupted evidence. **Concept tested:** Redesign prioritization.

## W. Development history

[All categories](#contents) · [Q177](#q177-what-does-git-establish-about-project-ownership) · [Q178](#q178-what-changed-in-the-latest-commit) · [Q179](#q179-what-historical-trade-off-appeared-in-the-batching-refactor) · [Q180](#q180-when-was-semantic-search-introduced-and-what-did-it-add) · [Q181](#q181-what-does-the-token-tracking-commit-prove) · [Q182](#q182-how-did-postman-support-evolve) · [Q183](#q183-which-documentation-is-stale-after-head) · [Q184](#q184-what-was-the-hardest-personal-engineering-challenge)

### Q177. What does Git establish about project ownership?

**Spoken answer:** The available commits are attributed to Aansh Singh and show specific implementation changes. They do not establish that every line was manually typed or explain all personal decisions.

**Technical explanation:** Commit metadata can support chronology and responsibility for committed work, while AI assistance, debugging experiences and original motivation require firsthand recollection or explicit records.

**Evidence:** git log at 79fa768; 02_APPLICATION_AND_AUDIT.md section 25.

**Follow-up:** How should you discuss AI assistance? **Answer:** State the actual tools/workflow you used and which design/review/testing responsibilities you owned, without inventing details from authorship.

**Misconception:** Commit authorship is not proof of manual authorship. **Concept tested:** Contribution evidence.

### Q178. What changed in the latest commit?

**Spoken answer:** It added parser identity and lexical call ownership foundations, associated tests and a handoff contract. It deliberately did not migrate Neo4j persistence.

**Technical explanation:** Qualified names, signatures, ranges, entity IDs and unattributed calls are richer intermediate data. The writer's small compatibility change skips declaration-only TypeScript signatures while keeping legacy keys/calls.

**Evidence:** commit 79fa768; backend/FUNCTION_IDENTITY.md.

**Follow-up:** Why is this a staged migration? **Answer:** Readers and writes must move together; exposing IDs prematurely would imply durable references the graph does not yet maintain.

**Misconception:** A foundation commit is not a completed integration. **Concept tested:** Migration sequencing.

### Q179. What historical trade-off appeared in the batching refactor?

**Spoken answer:** The e014d9e diff introduced micro-batched passes and changed Function identity from name+file+repo to name+repo. That simplified cross-file name matching while allowing collisions.

**Technical explanation:** This is supported by the diff, not a guessed personal motivation. Current code still carries the weaker key, and later parser identity work prepares its replacement.

**Evidence:** commit e014d9e; ETL:55.

**Follow-up:** Can you claim the collision was intentionally accepted? **Answer:** Only if personal records establish that; the diff proves behavior, not the author's complete reasoning.

**Misconception:** Code changes reveal effects more reliably than motivations. **Concept tested:** Historical inference discipline.

### Q180. When was semantic search introduced and what did it add?

**Spoken answer:** Commit d3ec9ab records vector embedding integration; the current path embeds function metadata and exposes semantic_code_search.

**Technical explanation:** A later commit 8d1c3a4 replaced the older vector procedure with modern SEARCH syntax. Neither milestone includes a stored retrieval-quality benchmark proving semantic accuracy gains.

**Evidence:** commits d3ec9ab,8d1c3a4; AG:60.

**Follow-up:** Why does the later change matter operationally? **Answer:** It couples runtime behavior to compatible Neo4j/Cypher versions, which should be tested and pinned.

**Misconception:** Feature introduction is not quality validation. **Concept tested:** Evolution and compatibility.

### Q181. What does the token-tracking commit prove?

**Spoken answer:** Commit 47f0049 introduced token accounting across ingestion/chat and related tests/source-view changes. It proves implementation of the metric, not the supplied benchmark result.

**Technical explanation:** No historical diff matching the 737k/18k/97.5 figures was found. README examples use illustrative values and explicitly distinguish context from cost/quality.

**Evidence:** commit 47f0049; AG:425.

**Follow-up:** How should you phrase this on a resume? **Answer:** “Implemented token-context accounting” unless you can supply the original reproducible benchmark evidence for a quantitative claim.

**Misconception:** Instrumentation and experimental results are distinct accomplishments. **Concept tested:** Resume evidence.

### Q182. How did Postman support evolve?

**Spoken answer:** An assessment documented gaps and a later commit added the actual collection/environment with a chained lifecycle and HMAC cases. Suggestions in the assessment are not all implemented.

**Technical explanation:** No CI workflow, durable webhook completion polling or formal answer evaluator appears in the final collection. The current artifact has four folders and 23 requests.

**Evidence:** POSTMAN_TECHNICAL_ASSESSMENT.md; commit 17d36c0; postman/README.md.

**Follow-up:** What should you avoid saying? **Answer:** That proposed monitors/CI/evaluation systems were built merely because the assessment recommends them.

**Misconception:** Design recommendations are not shipped features. **Concept tested:** Document versus implementation.

### Q183. Which documentation is stale after HEAD?

**Spoken answer:** Earlier architecture notes say the parser lacks lexical scope/identity, but HEAD now adds those fields. Their persistence warning remains valid because the database migration is still pending.

**Technical explanation:** README's file-scope call warning accurately describes stored edges but needs layer-specific interpretation. backend/FUNCTION_IDENTITY.md explicitly explains the current handoff boundary.

**Evidence:** CG-001-architecture-investigation.md; backend/FUNCTION_IDENTITY.md; ETL:178.

**Follow-up:** How do you resolve contradictions? **Answer:** Use current source for behavior, date documents and describe which layer/revision each statement concerns.

**Misconception:** Documentation age and subsystem scope affect truth. **Concept tested:** Evidence reconciliation.

### Q184. What was the hardest personal engineering challenge?

**Spoken answer:** The repository suggests challenging areas such as graph identity, GDS compatibility and multi-stage failure handling, but only the developer can identify their actual hardest experience.

**Technical explanation:** A credible story should include the observed symptom, diagnosis, chosen fix, alternatives and validation tied to a real commit/test. The manual cannot infer emotions or firsthand debugging from commit titles.

**Evidence:** history table; commits 77d357d,79fa768.

**Follow-up:** How should you prepare? **Answer:** Fill in one genuine incident with before/after evidence and explain what you personally investigated.

**Misconception:** Plausible engineering stories are not personal recollections. **Concept tested:** Authentic contribution narrative.

## X. Weaknesses and improvements

[All categories](#contents) · [Q185](#q185-why-is-same-name-merging-more-serious-than-a-display-bug) · [Q186](#q186-how-would-you-make-ai-answers-more-reliable) · [Q187](#q187-what-is-the-best-fix-for-partial-ingestion) · [Q188](#q188-how-would-you-repair-webhook-updates) · [Q189](#q189-what-should-change-before-exposing-the-api-publicly) · [Q190](#q190-how-would-you-improve-semantic-search-quality) · [Q191](#q191-how-would-you-make-the-frontend-maintainable) · [Q192](#q192-what-limitations-cannot-be-resolved-from-repository-evidence-alone)

### Q185. Why is same-name merging more serious than a display bug?

**Spoken answer:** It combines code, paths, embeddings and relationships from distinct functions, changing the evidence used by tools and clustering. The UI merely displays the corrupted identity.

**Technical explanation:** A function can have multiple defining files while its legacy file points to one and raw_code/file_path to another. Fixing labels in React cannot reconstruct lost distinctions.

**Evidence:** ETL:55,57; DB:95.

**Follow-up:** What verifies a real fix? **Answer:** End-to-end duplicate-name fixtures asserting distinct persisted identities, correct edges, source lookup and tool references.

**Misconception:** Presentation fixes cannot repair data conflation. **Concept tested:** Data correctness.

### Q186. How would you make AI answers more reliable?

**Spoken answer:** Improve graph fidelity, add bounded source retrieval with stable references, enforce scope/budgets and validate cited claims. Then evaluate real questions with independent evidence.

**Technical explanation:** Prompt changes and stronger models can help but cannot recover lost identities or guarantee recall. Architecture labels should remain marked as generated interpretations.

**Evidence:** ETL:178; AG:343; LABEL:17.

**Follow-up:** What is a practical first milestone? **Answer:** Persist canonical function IDs and lexical call-site provenance with regression tests before adding answer-navigation features.

**Misconception:** Reliability requires the full evidence pipeline. **Concept tested:** Improvement prioritization.

### Q187. What is the best fix for partial ingestion?

**Spoken answer:** Build a new immutable generation and activate it only after required stages pass. Keep the previous complete generation available during failures.

**Technical explanation:** The current workflow deletes first and commits batches independently. A snapshot pointer separates efficient bounded writes from atomic user-visible publication; garbage collection handles abandoned generations.

**Evidence:** ETL:278,276; M:462.

**Follow-up:** What does this cost? **Answer:** More storage, snapshot-aware queries and cleanup coordination, but clearer recovery and concurrency semantics.

**Misconception:** Batching and atomic publication need not be mutually exclusive. **Concept tested:** Snapshot architecture.

### Q188. How would you repair webhook updates?

**Spoken answer:** Add durable delivery records, correct PR file enumeration, removed/renamed-file reconciliation and ordered updates tied to immutable revisions.

**Technical explanation:** Recompute affected definitions/references and token baselines consistently, and avoid mixing branches under a single key. Return job status rather than relying only on logs after 202.

**Evidence:** PIPE:39,89,219; HOOK:53.

**Follow-up:** Would retries then be safe automatically? **Answer:** Only with idempotent stage outputs and deduplication; provider requests and graph activation still need explicit policies.

**Misconception:** Durability alone does not ensure exactly-once effects. **Concept tested:** Event processing design.

### Q189. What should change before exposing the API publicly?

**Spoken answer:** Authentication/authorization, server-bound tool scopes, safe retention, quotas and deployment secrets/transport are prerequisites. Current delete and source routes are open to any reachable caller.

**Technical explanation:** Startup-wide deletion, backend-wide GitHub credentials and no tenant identity are fundamental shared-service risks. CORS only controls browser-origin behavior and does not restrict direct clients.

**Evidence:** M:196,248,328; GH:29.

**Follow-up:** Would an API key alone be enough? **Answer:** It may identify a caller, but permissions for each repository and operation still need enforcement.

**Misconception:** Authentication and authorization are separate. **Concept tested:** Production access model.

### Q190. How would you improve semantic search quality?

**Spoken answer:** Evaluate richer function/code inputs, exact-symbol retrieval and scope-aware vector candidates, then combine ranked signals under a context budget.

**Technical explanation:** Name/path vectors are cheap but can miss implementation behavior. Changing embedding inputs requires versioned caching/reindexing and privacy consideration; it should not be disguised as the current system.

**Evidence:** ETL:208; AG:60.

**Follow-up:** What baseline must you retain? **Answer:** The current metadata-only version and a lexical baseline, so gains can be attributed to the specific change.

**Misconception:** Richer vectors are a hypothesis until evaluated. **Concept tested:** Retrieval redesign.

### Q191. How would you make the frontend maintainable?

**Spoken answer:** Separate graph, ingestion and chat request lifecycles; use stable entity/snapshot contracts and explicit stale-response guards. Break the large App into focused components/hooks as behavior warrants.

**Technical explanation:** A new state library is optional; the important change is ownership of controllers, server state and selection/navigation semantics. Browser tests should cover interaction and race conditions.

**Evidence:** UI:585,808,971; CODE:58.

**Follow-up:** What should remain centralized? **Answer:** The active repository/snapshot and navigation intent, so chat/source/graph cannot silently diverge.

**Misconception:** File splitting alone is not architectural separation. **Concept tested:** Frontend design.

### Q192. What limitations cannot be resolved from repository evidence alone?

**Spoken answer:** Live provider/model availability, current database/GDS behavior, real answer accuracy, original benchmark methodology and the developer's personal contributions need additional evidence.

**Technical explanation:** This audit verifies source and isolated tests, not external integrations or historical recollections. The manual marks those gaps rather than supplying plausible but unsupported claims.

**Evidence:** 06_EVIDENCE.md; README.md; git history.

**Follow-up:** How should you answer an interviewer at that boundary? **Answer:** Say exactly what is known, what remains unverified and how you would investigate it.

**Misconception:** Acknowledging an evidence boundary is not the same as understanding nothing. **Concept tested:** Engineering honesty.

## Y. Challenging hypothetical scenarios

[All categories](#contents) · [Q193](#q193-two-files-define-validate-and-a-user-asks-who-calls-the-payment-one-what-happens) · [Q194](#q194-the-embedding-provider-fails-after-half-the-functions-are-written-what-remains) · [Q195](#q195-a-second-worker-starts-while-someone-is-chatting-what-could-happen) · [Q196](#q196-a-global-vector-top-five-contains-only-another-repository-will-five-local-matches-be-returned) · [Q197](#q197-a-signed-push-removes-a-file-does-the-graph-remove-it) · [Q198](#q198-a-function-returns-a-callback-that-calls-save-is-outer-shown-as-calling-save) · [Q199](#q199-the-agent-reports-100-efficiency-and-a-confident-architecture-answer-is-that-success) · [Q200](#q200-how-would-you-defend-codegraph-when-a-senior-engineer-challenges-every-claim)

### Q193. Two files define validate and a user asks who calls the payment one. What happens?

**Spoken answer:** Current tools cannot reliably distinguish it by function name because Neo4j merges the definitions. Even a correct semantic hit can lead to ambiguous follow-up calls.

**Technical explanation:** Parser IDs distinguish the definitions in memory, but persisted embeddings/code may be overwritten and caller edges combined. I would disclose the ambiguity rather than claim a precise payment-only blast radius.

**Evidence:** ID:37; ETL:55; AG:104.

**Follow-up:** What makes a redesign answer precise? **Answer:** Canonical entity IDs, resolved or explicitly unresolved call targets, and snapshot-bound tool arguments.

**Misconception:** File-path display does not undo merged graph identity. **Concept tested:** End-to-end ambiguity.

### Q194. The embedding provider fails after half the functions are written. What remains?

**Spoken answer:** Files and earlier function batches remain committed, and the previous scope may already have been deleted. Calls, communities and terminal success may be missing.

**Technical explanation:** Ingestion catches the eventual exception as a stream error and cleans temporary files, but does not restore old graph data. A direct graph request can observe the partial state.

**Evidence:** ETL:278,298; M:508,515.

**Follow-up:** What would make retry safe? **Answer:** Write a separate generation with idempotent stage records and activate only on completion, preserving the old generation.

**Misconception:** Temporary cleanup is not database rollback. **Concept tested:** Failure tracing.

### Q195. A second worker starts while someone is chatting. What could happen?

**Spoken answer:** Its startup deletes all repository-scoped nodes, potentially removing the active chat's data. Subsequent tool or baseline reads can be empty even though the user did nothing.

**Technical explanation:** The startup lock is process-local and does not coordinate retention. Cached agent state cannot restore deleted evidence; the UI's existing graph may also become stale.

**Evidence:** M:60; ETL:29; AG:438.

**Follow-up:** How should serving startup behave instead? **Answer:** Perform safe schema/readiness initialization, with data cleanup managed by explicit retention jobs.

**Misconception:** Starting another server process should not implicitly own all users' data. **Concept tested:** Lifecycle safety.

### Q196. A global vector top-five contains only another repository. Will five local matches be returned?

**Spoken answer:** No. The current query filters after global candidate selection, so the result can be empty even when local vectors are relevant.

**Technical explanation:** The tool formats no matches, and the agent has no diagnostic explaining crowding. This is a retrieval-recall failure distinct from unauthorized leakage, because the filter still removes foreign rows.

**Evidence:** AG:60,307.

**Follow-up:** How would you prove this on a test database? **Answer:** Populate two known vector groups, make foreign candidates closer globally, and compare scoped exact ranking with the tool result.

**Misconception:** Scope filtering can be secure against row mixing yet poor for recall. **Concept tested:** Filtering trade-offs.

### Q197. A signed push removes a file. Does the graph remove it?

**Spoken answer:** No. The active push extractor reads added and modified lists, not removed, and persistence merges without deleting obsolete file content.

**Technical explanation:** Old definitions/calls can remain; a missing raw file fetch is skipped rather than treated as deletion. A full rebuild is the current way to refresh the scope authoritatively.

**Evidence:** PIPE:23,170,219.

**Follow-up:** What else can become stale? **Answer:** Function source, embeddings, relationships and total source-token baseline, not just the file node.

**Misconception:** Ignoring a deleted file is not deletion reconciliation. **Concept tested:** Incremental negative changes.

### Q198. A function returns a callback that calls save. Is outer shown as calling save?

**Spoken answer:** The new parser tries to keep calls inside uncaptured anonymous boundaries unattributed. The legacy ETL can still attach save to every function in the file through outgoing_calls.

**Technical explanation:** This demonstrates why parser tests and stored graph behavior must be traced separately. The call exists syntactically but its execution timing and owner require more than file-wide association.

**Evidence:** P:578; ETL:178.

**Follow-up:** Can the graph prove save executes when outer runs? **Answer:** No. Even correct lexical nesting would not establish callback invocation timing or runtime reachability.

**Misconception:** Containing syntax does not prove execution. **Concept tested:** Static evidence interpretation.

### Q199. The agent reports 100% efficiency and a confident architecture answer. Is that success?

**Spoken answer:** Not necessarily. Zero tool calls can yield zero context tokens and 100% reported efficiency with a positive baseline. The answer may be unsupported.

**Technical explanation:** Even retrieved community labels are model-generated interpretations of sampled metadata. Success should require supported claims and adequate evidence coverage, not a favorable arithmetic ratio.

**Evidence:** AG:442; LABEL:24.

**Follow-up:** What should the response contract expose? **Answer:** Evidence references, uncertainty and actual tool/provider usage, with quality evaluation separate from context metrics.

**Misconception:** A perfect reduction score can conceal total grounding failure. **Concept tested:** Metric counterexamples.

### Q200. How would you defend CodeGraph when a senior engineer challenges every claim?

**Spoken answer:** I would trace the exact revision, show actual query/parser contracts and test boundaries, acknowledge the identity and retrieval limits, and explain concrete improvements.

**Technical explanation:** I would not claim a source tool, complete branch support, correct incremental reconciliation or validated 97.5% benchmark. The strongest defense is understanding what the system really does and where evidence stops.

**Evidence:** M; P; ETL; AG; 06_EVIDENCE.md.

**Follow-up:** What personal detail must you supply yourself? **Answer:** Your actual design/debugging decisions, AI-tool usage and measured experiments; Git alone cannot provide those stories.

**Misconception:** Defending a project does not require pretending it is production complete. **Concept tested:** Technical judgment and ownership.

---

[Back to contents](#contents) · [Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](02_APPLICATION_AND_AUDIT.md) · [Next](04_STUDY_AND_DEFENSE.md)
