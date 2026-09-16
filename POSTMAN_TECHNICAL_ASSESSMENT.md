# Postman Technical Assessment for Codegraph

**Assessment date:** 2026-09-16  
**Scope:** Investigation and recommendations only; no Postman artifacts or application behavior were implemented.

## Executive decision

Postman is worth adding to Codegraph, but only as a small, deliberately scoped developer-experience layer.

The strongest use case is an executable, human-readable walkthrough of the application's real HTTP lifecycle:

1. verify the API process;
2. ingest a GitHub repository while validating the newline-delimited JSON stream;
3. capture the canonical repository name returned by ingestion;
4. read the resulting graph;
5. capture a function's Neo4j element ID;
6. fetch that function's source;
7. ask a repository-scoped Graph-RAG question and inspect its context metrics; and
8. delete the repository scope and verify cleanup.

That workflow is currently spread across README `curl` examples, frontend behavior, and implementation knowledge. A Postman collection would make it repeatable and visible to contributors, reviewers, and interviewers without requiring them to learn the React UI first.

Postman should **not** become the primary test framework. The repository already has good native unit and component coverage for parsing, Neo4j query construction, graph isolation, embedding batching, GDS cleanup, frontend NDJSON parsing, and UI-side request behavior. Those tests are faster, more deterministic, and closer to the implementation than HTTP collection tests. Postman should cover the black-box seams that those suites do not fully exercise: deployed-process wiring, multi-request workflows, real headers/content types, live dependency configuration, signed webhook requests, and executable examples.

### Recommendation in one sentence

Create one source-controlled **Codegraph API** collection, one secret-free **Local** environment template, and a small data-driven negative-test file; use the collection primarily for onboarding, demonstrations, manual debugging, and an optional live smoke job, while retaining pytest and Node tests as the required correctness suites.

### Value versus complexity

| Outcome | Expected value | Added complexity |
| --- | --- | --- |
| Onboarding and portfolio demo | High | Low |
| Reproducing the full HTTP workflow | High | Low to medium because ingestion is streamed and expensive |
| Webhook HMAC debugging | High | Low |
| Deterministic PR regression testing | Medium | Medium because the live path needs Neo4j GDS and model-provider credentials |
| Production monitoring | Low today | High relative to the project's local-only posture |
| Mock-server infrastructure | Low today | Medium and would require application configurability first |
| Load/performance testing | Low | High and the tool would not address the important concurrency risks well |

The net decision is **yes, with strict scope control**. A collection and local environment template are justified. A Postman-centric test strategy, cloud monitor, mock estate, or mandatory live-AI PR gate is not.

---

## 1. Evidence-based system overview

### Active application boundary

The current application is the `backend/` FastAPI service plus the `frontend/` Vite/React dashboard. The root-level `app/`, `agent.py`, `database.py`, `parse_python.py`, and `tests/` are earlier prototypes with different endpoints and behavior. Postman artifacts must describe only the active `backend/app` API unless a clearly labeled legacy folder is intentionally created; the recommended collection should omit the prototypes entirely.

Evidence:

- `backend/app/main.py` defines the active FastAPI application and includes the webhook router.
- `frontend/src/api.js` is the active browser client.
- `README.md` explicitly distinguishes the active `backend/` and `frontend/` application from root-level prototypes.

### Architecture and runtime

| Area | Actual implementation | Postman relevance |
| --- | --- | --- |
| Frontend | React 19, Vite 7, React Flow, D3 force layout | The collection complements the UI by exposing the raw workflow and payloads. It does not test UI behavior. |
| Backend | FastAPI with Pydantic request validation and generated OpenAPI/Swagger UI | OpenAPI can seed endpoint requests; handwritten workflow scripts remain necessary. |
| Primary data store | Neo4j, including a 1,536-dimension cosine vector index | Graph and source endpoints can validate that writes are visible through the public API. Direct Cypher/database testing should stay outside Postman. |
| Graph analytics | Neo4j Graph Data Science Leiden clustering | Visible indirectly through `community_id`, `community_name`, and `community_description` in graph responses. |
| Source parsing | Tree-sitter for `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.go`, and `.java` | Visible indirectly through files, functions, call edges, and stored source. Parser correctness remains a pytest concern. |
| AI providers | OpenAI embeddings (`text-embedding-3-small`) and community labels (`gpt-4o-mini`); Anthropic chat (`claude-sonnet-5`) | Live workflows require backend-held provider keys, can cost money, and are nondeterministic. The keys should never be Postman variables because Postman does not call these providers directly. |
| GitHub | GitHub zipball API for full ingestion; immutable raw-content URLs for webhook changes | `repository_url` and webhook fixture data are useful collection inputs. `GITHUB_TOKEN` stays in `backend/.env`. |
| Background work | FastAPI in-process `BackgroundTasks` for webhooks | A `202` only proves acceptance. There is no job/status resource for reliable Postman polling. |
| Queue/cache | None | Do not invent queue or cache workflows. |
| Authentication | No application auth. Only GitHub webhook HMAC SHA-256 verification. | No OAuth/token-login folder is warranted. A webhook pre-request HMAC script is warranted. |
| Observability | Standard Python logging only; no metrics, tracing, audit store, or job event store | Postman cannot verify background completion reliably or replace missing observability. |
| Containers | Compose runs only `neo4j:latest` with GDS; API and frontend run on the host | A CLI smoke job must install/start the backend separately and wait for readiness. |
| CI/CD | No checked-in CI workflow or deployment configuration | Postman should not be the first or only CI layer. Establish native CI first. |
| Configuration | `backend/.env` via `pydantic-settings`; frontend API base is hard-coded to `http://localhost:8000` | Postman environments improve host switching, but production/staging environments are premature because neither target exists in the repository. |

### Important lifecycle properties

- FastAPI startup initializes Neo4j indexes and then deletes all repository-scoped graph nodes. Ingested data is intentionally ephemeral across API restarts.
- Full ingestion is performed inside the HTTP response stream, not through a durable job. It downloads a repository, discovers supported source, parses files with at most 32 concurrent file-read slots, counts tokens, replaces the repository scope in multiple Neo4j transactions, creates embeddings, maps calls, runs Leiden, and labels communities.
- Ingestion success or failure after streaming starts is encoded in NDJSON records. HTTP `200` alone is not success.
- Full replacement is not atomic. A failure after scope deletion can leave a partially rebuilt graph.
- Concurrent ingestions of the same repository can interleave destructive replacement and micro-batch writes. Postman runs should serialize ingestion requests.
- The graph endpoint is a visualization window capped by `LIMIT 200`, not a full export and not paginated.
- Webhook processing has no delivery-ID deduplication, replay protection, durable retry, removed-file reconciliation, or completion-status endpoint.

These properties should be documented directly in collection descriptions because they determine how a user interprets a green or red request.

---

## 2. Concrete API inventory

### Health and system

#### `GET /health`

- **Purpose:** Process liveness only.
- **Request:** No parameters, body, or authentication.
- **Success:** `200`, JSON `{"status":"ok"}`.
- **Side effects:** None.
- **Important boundary:** Does not check Neo4j, GitHub, OpenAI, Anthropic, GDS, or index readiness beyond the fact that application startup completed.
- **Postman use:** First request in every manual workflow. Assert the exact body and JSON content type, but label it **liveness**, not readiness.

FastAPI also exposes generated `/docs` and `/openapi.json` routes. They are useful for discovery but are not application health checks.

### Repository ingestion

#### `POST /api/ingest-repo`

- **Purpose:** Download the current default branch of a GitHub repository and replace its repository-scoped knowledge graph.
- **Body:** `{"url":"https://github.com/<owner>/<repository>"}`.
- **Validation:** `url` length 1-2,048 after trimming; scheme must be HTTPS; host must be `github.com` or `www.github.com`; decoded path must normalize to exactly `owner/repository`; each segment permits letters, digits, `_`, `.`, and `-`; a trailing `.git` is removed.
- **Headers:** Request `Content-Type: application/json`; `Accept: application/x-ndjson` is appropriate.
- **Immediate validation failure:** `422` FastAPI error response.
- **Accepted stream:** `200`, `Content-Type: application/x-ndjson`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- **Progress response:** One JSON object per line. Records contain `status` and numeric `progress`. The terminal success record additionally contains `repo_name` and `total_repo_tokens`.
- **Streamed failures:** Still generally HTTP `200`; terminal records contain `error`. Known messages distinguish GitHub 404, archive/download failure, Neo4j authentication/unavailability/query failure, and unexpected failure.
- **Side effects:** Deletes the existing repository scope, then writes repository, file, function, call/external-function, token, community, and embedding data across multiple transactions. Calls GitHub, OpenAI, Neo4j GDS, and OpenAI again for labels.
- **Timeouts/retries:** GitHub zipball download uses a 60-second HTTPX timeout. No application retry policy is implemented. OpenAI and Neo4j operations use library behavior rather than an explicit end-to-end deadline.
- **Idempotency:** Repeating the same URL replaces the same canonical scope, but it is not strictly idempotent: the upstream default branch can move, labels are model-generated, timestamps change, and partial failures can change state.
- **Concurrency:** Same-scope concurrent runs are unsafe because their deletes and bounded write transactions can interleave.
- **Postman use:** Highest-value request. A post-response script must parse every nonblank NDJSON line, fail on any `error`, require exactly one terminal `progress === 100` record, and capture `repo_name` and `total_repo_tokens`. The request timeout must be generous and this request must not be run in parallel.

### Graph exploration

#### `GET /api/graph?repo_name=<owner/repository>`

- **Purpose:** Return a repository-scoped React Flow-compatible graph window.
- **Parameter:** Optional `repo_name`. If omitted, the API intentionally returns `{"nodes":[],"edges":[]}`. If supplied, it must be canonical after trimming and optional `.git` removal.
- **Success:** `200`, object with `nodes` and `edges` arrays.
- **Node structure:** Top-level identifiers/labels/community fields plus a nested `data` object. Function `raw_code` and embeddings are removed from this bulk response. Positions are added server-side.
- **Edge structure:** `id`, `source`, `target`, `label`, and nested `data`; relationships are `DEFINES` or `CALLS`.
- **Errors:** Invalid scope `422`; Neo4j authentication/unavailable `503`; other Neo4j query errors `500`.
- **Side effects:** None.
- **Limit:** Cypher applies `LIMIT 200` before serialization. There is no cursor or pagination parameter.
- **Postman use:** Validate structural invariants, capture one non-external Function node's element ID, verify source bodies are absent, and confirm all returned data belongs to the requested workflow context where the payload exposes that field.

#### `GET /api/node/{node_id}/code?repo_name=<owner/repository>`

- **Purpose:** Return one function's stored source without exposing all source in the graph response.
- **Path/query:** Neo4j `elementId` as `node_id`; required canonical `repo_name` query parameter.
- **Success:** `200`, `{"code":"...","file_path":"...","name":"..."}`.
- **Errors:** Missing query parameter `422`; invalid/blank scope `422`; unknown node or cross-scope node `404`; Neo4j authentication/unavailable `503`; other query failure `500`.
- **Side effects:** None.
- **Postman use:** Chain from graph response. Assert nonblank name/file path, string code, and repository isolation by trying the captured node ID with another scope.

### Graph-RAG chat

#### `POST /api/chat`

- **Purpose:** Ask the Claude-backed LangGraph agent a question using seven repository-scoped graph tools.
- **Body:** `{"message":"...","repo_name":"owner/repository"}`.
- **Validation:** Message is trimmed, nonblank, and at most 10,000 characters; repository identifier is canonical and 3-201 characters.
- **Success:** `200`, `{"response":"...","metrics":{"full_repo_tokens":n,"context_tokens":n,"tokens_saved":n,"efficiency_percentage":n}}`.
- **Errors:** Request validation `422`; any agent/provider/tool failure is deliberately collapsed to `502` with `The code agent could not complete the request`.
- **Side effects:** No application state is persisted, but the call consumes Anthropic capacity and semantic search can call OpenAI embeddings.
- **Idempotency:** Read-only at the application level but nondeterministic and billable; identical requests need not return identical prose or metrics.
- **Timeout/retry:** No explicit route-level deadline or retry policy.
- **Postman use:** Assert shape and arithmetic invariants, not exact answer text. For an ingested repository, `full_repo_tokens` should equal the captured ingestion total. If the baseline is positive, `tokens_saved` should equal `full_repo_tokens - context_tokens`, subject to the application's current logic, and percentage should be numeric. Avoid strict response-time gates.

### Repository deletion

#### `DELETE /api/repositories/{repo_name:path}`

- **Purpose:** Permanently delete all graph nodes with the normalized repository scope.
- **Path:** URL-encoded `owner/repository` is safest (`owner%2Frepository`). Trailing `.git` normalizes away.
- **Success:** `200`, `{"status":"success","repo_name":"owner/repository"}`.
- **Errors:** Invalid scope `422`; Neo4j authentication/unavailable `503`; query failure `500`.
- **Side effects:** Destructive scoped `DETACH DELETE`.
- **Idempotency:** Operationally idempotent: deleting a missing scope still reports success.
- **Postman use:** Preferred explicit cleanup request. Run in a workflow cleanup phase and verify the graph is empty afterward.

#### `DELETE /api/repo`

- **Purpose:** Browser-unload cleanup variant.
- **Body:** `{"repo_name":"owner/repository"}`.
- **Response/errors/side effects:** Same as the path-based delete.
- **Postman use:** Keep in a **Browser lifecycle compatibility** folder, not as the main cleanup operation. It exists to support `fetch(..., {keepalive: true})`, not because the API needs two normal delete styles.

### GitHub webhook

#### `POST /api/webhooks/github`

- **Purpose:** Authenticate and acknowledge a GitHub webhook, then process supported changes in an in-process background task.
- **Required header:** `X-Hub-Signature-256: sha256=<hex HMAC>` computed over the exact raw request bytes using `GITHUB_WEBHOOK_SECRET`.
- **Optional header:** `X-GitHub-Event`; missing values become `unknown`.
- **Body:** Any valid JSON object at the route boundary. Business processing expects GitHub repository metadata and a commit SHA for meaningful `push` or `pull_request` work.
- **Success:** `202`, `{"status":"accepted","message":"Webhook processing started in background"}`.
- **Errors:** Missing/invalid signature `401`; malformed JSON or a non-object JSON value `400`.
- **Side effects:** After the response, supported paths are fetched from GitHub raw content, parsed, and merged into Neo4j. Push processing includes added/modified paths but not removed paths. Standard GitHub pull-request payloads do not include file lists, and the active backend does not call the PR files API.
- **Idempotency/retries:** No delivery ID is inspected and no deduplication exists. Retried deliveries can repeat work. Errors after `202` are logged and cannot be observed through this API.
- **Concurrency:** Background tasks run in the API process with no queue or multi-process coordination.
- **Postman use:** Excellent for signature and request-contract debugging. It is not currently a reliable end-to-end background-work test because there is no job ID or completion endpoint.

---

## 3. Existing testing and the gap Postman should fill

### What the native suites already do well

The active backend suite uses pytest, FastAPI `TestClient`, mocks, and optional live-Neo4j integration tests. Its named tests cover:

- parser support for all seven extensions and exact function-source extraction;
- parser failure isolation, progress accounting, and token-baseline behavior;
- repository-scoped graph writes, reads, source lookup, agent tools, and deletion;
- bounded batches and one Neo4j transaction per micro-batch;
- graph serialization, including omission of `raw_code`;
- embedding order/dimension behavior and community structured output;
- GDS projection/write/drop behavior, including cleanup on failure;
- index initialization and application startup cleanup;
- graph and chat endpoint contracts; and
- delete endpoint normalization and validation.

The frontend's 13 Node tests currently pass and cover repository shorthand normalization, chunked NDJSON handling, streamed terminal errors, graph/chat scoping, source lookup, both deletion clients, and community utilities.

The current checkout's backend virtual environment is incomplete: test collection fails because `openai`, `tiktoken`, and Tree-sitter language packages are not installed in that environment, even though they are declared in `backend/requirements.txt`. This does not show a code failure, but it is direct evidence that onboarding/startup verification needs improvement. A Postman collection cannot repair Python environment installation; a setup check or locked environment remains necessary before the collection can run.

### Important gaps Postman can complement

| Gap | Why Postman helps | Why this is not duplicate coverage |
| --- | --- | --- |
| Whole-process API wiring | Sends requests to a running Uvicorn process with real headers, ports, content types, and Neo4j/service configuration. | `TestClient` mostly tests in-process handlers with patched dependencies. |
| Cross-request state | Captures `repo_name` and a graph `node_id`, then reuses them in source/chat/delete requests. | Native tests verify pieces; they do not provide one shareable external walkthrough. |
| NDJSON terminal semantics | Makes the crucial distinction between HTTP `200` and a terminal `error` executable for humans and smoke runs. | Frontend tests cover its parser, but contributors using curl or another client can still misinterpret the API. |
| HMAC request generation | Computes the signature from the exact raw webhook body and makes valid/invalid requests easy to compare. | The active backend currently has no dedicated webhook route/signature tests; root tests target a legacy endpoint. |
| Environment reproducibility | Encodes `base_url`, demo repository, and private local webhook secret without changing source. | Existing docs are prose and shell snippets. |
| Executable examples | Shows real success and error responses next to requests. | Swagger exposes operations but does not provide the chained product story. |
| Deployment smoke tests | Can run the same small black-box folder after a future deployment. | Native suites do not prove a deployed URL is reachable and configured. |

### Gaps Postman should not attempt to fill

- Parser and graph-algorithm correctness.
- Cypher query scoping and transaction-boundary tests.
- GDS projection cleanup under injected failures.
- OpenAI embedding response ordering and vector dimensions at the service-unit level.
- React rendering, graph layout, hover/filter behavior, or source drawer accessibility.
- Background worker exception behavior that has no public observation API.
- Race conditions from concurrent same-repository ingestion.

Those remain native unit/integration, browser-component, or dedicated concurrency-test concerns.

---

## 4. Capability-by-capability evaluation

| Postman capability | Rating | Project-specific conclusion |
| --- | --- | --- |
| Collections | **High value** | Seven active endpoints form clear health, ingestion, graph, chat, cleanup, webhook, and negative-test folders. A collection would consolidate scattered curl examples and encode the full product story. |
| Environments and variables | **High value** | `base_url`, demo repository inputs, and the webhook secret vary by operator. Captured `repo_name` and `node_id` are essential for chaining. Do not expose backend provider keys. |
| Pre-request scripts | **Medium value** | Strongly justified for exact-body GitHub HMAC signing and optionally unique fixture markers. Not needed for ordinary authorization, timestamps, or UUIDs because the API has no such contract. |
| Post-response/test scripts | **High value** | Needed to parse NDJSON, detect streamed errors, capture terminal values/node IDs, validate schema invariants, and verify cleanup. |
| Request chaining | **High value** | Ingest → graph → source → chat → delete is the natural application lifecycle and the most compelling Postman contribution. |
| Collection Runner | **High value** | Useful for the ordered golden path, cleanup, negative matrices, and repeatable demos. Iteration data can exercise invalid identifiers and webhook error cases. Never parallelize destructive ingestion. |
| Postman CLI | **Medium value now** | Valuable for a future black-box smoke job and local scripted verification. It should follow—not substitute for—working native CI and deterministic service startup. Current Postman guidance recommends the Postman CLI for new workflows. |
| Newman | **Low value / not recommended for new work** | Newman remains a v2.1 open-source runner, but current Postman collection v3 is not compatible with Newman. Starting a new integration on Newman would create a format ceiling. Use Postman CLI unless the project deliberately standardizes on v2.1 for fully offline/open-source reasons. |
| CI/CD integration | **Medium future value; low immediate value** | There is no CI today, and a full run needs GDS plus paid/external AI calls. A deterministic PR job should begin with native tests. Add a Postman smoke job later, initially manual/nightly or deployment-triggered. |
| Mock servers | **Low value today** | The frontend already stubs fetch in Node tests. External provider endpoints are not configurable in a way that makes Postman mocks drop-in dependencies. Static mocks would not reproduce NDJSON timing, Neo4j/GDS behavior, or agent semantics faithfully. |
| API documentation | **High complementary value** | Saved examples and folder descriptions provide an executable onboarding layer. They should complement README and Swagger, not replace either. |
| OpenAPI integration | **Medium value** | FastAPI generates a useful route skeleton, but the current contract under-specifies dynamic graph objects, the NDJSON stream, and raw webhook bodies. Import/generated requests should be a baseline, not the entire collection. |
| Monitoring | **Low value / not applicable today** | The project has no deployed public service, and `/health` is only liveness. Cloud monitoring localhost is impossible without a private runner and would add cost/complexity without meaningful dependency coverage. |
| Contract/schema validation | **Medium value** | Useful at the external API boundary because the React client is plain JavaScript and graph payloads are dynamic. Value is limited until response models/OpenAPI schemas become more explicit. |
| Lightweight performance checks | **Low value** | A loose liveness/graph ceiling can detect egregious regressions. Ingestion and chat depend on repo size and external providers, so hard thresholds would be noisy. Postman must not replace dedicated benchmarking or load testing. |

Current Postman documentation confirms that collection runs can pass data between requests, accept iteration data, and run through the Postman CLI; the CLI can emit machine-readable reports for CI. Postman's current documentation also recommends the Postman CLI rather than Newman for new workflows because Newman does not support the collection v3 format used by Postman v12. See [Collection Runner](https://learning.postman.com/docs/tests-and-scripts/running-collections/intro-to-collection-runs), [Postman CLI](https://learning.postman.com/docs/tests-and-scripts/postman-cli-guides/overview), and [Postman reference overview](https://learning.postman.com/docs/reference/overview).

---

## 5. Recommended artifact design

### A. One source-controlled collection: `Codegraph API`

Recommended folders:

1. **00 - Liveness and contract**
   - Process liveness
   - Empty unscoped graph
   - OpenAPI document (informational, not required in the golden run)
2. **01 - Golden path**
   - Ingest repository
   - Read repository graph
   - Fetch captured function source
   - Ask graph question
   - Delete repository
   - Verify graph cleanup
3. **02 - Validation and failure semantics**
   - Reject non-GitHub ingestion URL
   - Demonstrate streamed GitHub-not-found error
   - Reject malformed repository scope
   - Reject missing chat scope
   - Source not found/cross-scope
4. **03 - Repository lifecycle**
   - Explicit path delete
   - Browser keepalive body delete
   - Repeat delete to document idempotent outcome
5. **04 - GitHub webhook contract**
   - Valid signed request
   - Missing signature
   - Invalid signature
   - Signed malformed/non-object JSON
   - Real push fixture, clearly marked manual and non-deterministic
6. **90 - Manual diagnostics**
   - Demonstrate that `/health` can remain `200` while Neo4j-backed graph calls return `503`
   - Requests intended for controlled failure drills only

Do not create separate collections for each small domain. The API is small enough that fragmentation would make the end-to-end story harder to run.

### B. Environment template: `Codegraph Local.example`

Check in only non-secret defaults and empty secret placeholders. Do not commit a user's populated local environment.

| Variable | Scope | Example/default | Rationale |
| --- | --- | --- | --- |
| `base_url` | Environment | `http://localhost:8000` | Changes by runtime/deployment. |
| `repository_url` | Environment | A small, stable public GitHub repository | Operator-selectable live test input. Pinning a default branch is not supported by this API, so the example can drift. |
| `expected_repo_name` | Environment | Corresponding `owner/repository` | Optional pre-run expectation. The actual value should be overwritten from ingestion. |
| `webhook_secret` | Local/private environment value | Empty | Must match `backend/.env`; never commit the populated value. |
| `chat_question` | Collection | A stable architecture question | Shared request content, not deployment configuration. |
| `graph_response_budget_ms` | Collection | A loose local diagnostic budget | Optional, non-blocking initially. |
| `active_repo_name` | Dynamic collection variable | Unset before run | Captured from the ingestion terminal record and cleared after cleanup. |
| `ingestion_total_tokens` | Dynamic collection variable | Unset | Captured from ingestion and compared with chat metrics. |
| `function_node_id` | Dynamic collection variable | Unset | Captured from the graph response for source lookup. |
| `function_name` | Dynamic collection variable | Unset | Captured for readable assertions/chat prompts. |
| `webhook_raw_body` | Request-local or collection variable | Fixture JSON string | The exact bytes signed must equal the exact body sent. |
| `webhook_signature` | Request-local variable | Generated | Derived in a pre-request script; should not persist as configuration. |

Do **not** create Postman variables for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `NEO4J_URI`, or Neo4j credentials. These configure the backend, are never part of Codegraph's public HTTP request contract, and putting them in Postman expands secret exposure without benefit.

Do not add staging or production environments until such deployments exist and have application authentication. A production environment against the present unauthenticated delete and source endpoints would be unsafe.

### C. Small iteration datasets

- `invalid-repository-identifiers.json`: blank, missing slash, extra path segment, spaces, and invalid characters, paired with the expected `422`.
- `webhook-signature-cases.json`: missing, malformed, and bad signatures plus expected `401`; keep the valid secret out of the file.

Avoid data-driven full ingestion across many repositories. That multiplies GitHub downloads, model usage, database churn, and nondeterminism without improving contract confidence proportionally.

### D. Saved examples

Save compact examples for:

- health success;
- ingestion progress and terminal success as NDJSON text;
- ingestion terminal error despite HTTP `200`;
- graph response with a very small synthetic-looking example, clearly labeled illustrative;
- source success and `404`;
- chat response with metric fields;
- delete success;
- webhook `202`, `401`, and `400`; and
- FastAPI `422` validation format.

Examples improve documentation. They must not be mistaken for generated schemas or live proof.

### E. Pre-request and post-response logic

#### Webhook pre-request script

The script should:

1. read one exact raw JSON string from `webhook_raw_body`;
2. compute HMAC SHA-256 using the private `webhook_secret`;
3. set a request-local `webhook_signature` as `sha256=<hex>`; and
4. place the unmodified raw string in the request body.

The package/version used for HMAC should be pinned if an external package is imported. Current Postman scripting supports versioned public npm packages through `pm.require`; external packages are supported by the Postman CLI but not Newman, another reason to prefer the CLI for new work. See [Postman external packages](https://learning.postman.com/docs/tests-and-scripts/write-scripts/packages/external-package-registries).

#### Ingestion post-response script

The script should treat the body as text and:

- split on line endings;
- discard blank lines;
- parse every remaining line as JSON;
- assert progress is numeric, bounded 0-100, and nondecreasing;
- fail if any record has `error`;
- require a terminal record with `progress === 100`;
- assert terminal `repo_name` is canonical and `total_repo_tokens` is a nonnegative integer; and
- store both terminal values for subsequent requests.

For the intentionally failing ingestion request, invert the terminal assertion: require an `error` and require that no terminal success record exists. This captures the API's unusual but intentional failure semantics.

#### Graph post-response script

- Require `nodes` and `edges` arrays.
- Assert no node or nested `data` object contains `raw_code` or `embedding`.
- Validate that every edge source/target refers to a returned node when possible; note that the query's record limit can make completeness assumptions fragile.
- Select the first node whose labels include `Function` and that is not external.
- Store its `id` and readable name.
- If no such node exists, fail with a message recommending a different demo repository rather than silently skipping source lookup.

#### Chat post-response script

- Assert `response` is a nonblank string.
- Require the four numeric metric fields.
- Compare `full_repo_tokens` to the captured ingestion total.
- When `full_repo_tokens > 0`, verify `tokens_saved === full_repo_tokens - context_tokens` and accept minor rounding only for `efficiency_percentage`.
- Do not assert exact prose, tool choice, community names, or response latency.

#### Cleanup post-response script

- Require the returned scope to equal `active_repo_name`.
- Follow with a graph read and assert both arrays are empty.
- Clear dynamic variables after verification so a later run cannot accidentally act on stale state.

---

## 6. High-value workflows

### Workflow 1: Golden repository journey

**Purpose:** Provide the definitive onboarding/demo experience and an end-to-end black-box smoke test.

**Requests:**

1. `GET /health` — expect `200` and `status: ok`.
2. `POST /api/ingest-repo` with `repository_url` — expect NDJSON and a terminal success record.
3. `GET /api/graph?repo_name={{active_repo_name}}` — expect nonempty nodes for a suitable demo repository and capture one internal Function node.
4. `GET /api/node/{{function_node_id}}/code?repo_name={{active_repo_name}}` — expect source metadata and code string.
5. `POST /api/chat` with `chat_question` and `active_repo_name` — expect answer plus consistent metrics.
6. `DELETE /api/repositories/{{active_repo_name}}` — expect scoped success.
7. `GET /api/graph?repo_name={{active_repo_name}}` — expect empty arrays.

**Captured variables:** `active_repo_name`, `ingestion_total_tokens`, `function_node_id`, `function_name`.

**State transitions:** No scope → repository partially rebuilt during stream → enriched graph ready → read-only exploration/chat → scope deleted.

**Cleanup:** Mandatory explicit delete. Also clear dynamic Postman variables.

**Value:** Makes the most impressive behavior—multi-language ingestion, graph construction, source minimization, community metadata, Graph-RAG, and token-efficiency metrics—observable in one reproducible run.

**Automation tier:** Manual/portfolio by default; optional live smoke. It should not initially block every pull request because it depends on four external/runtime systems and incurs model calls.

### Workflow 2: Ingestion failure semantics

**Purpose:** Prevent clients and operators from treating HTTP `200` as successful ingestion.

**Requests:**

1. `POST /api/ingest-repo` with a syntactically valid but nonexistent GitHub repository — expect HTTP `200`, NDJSON content type, a terminal `error`, and no `progress: 100` success record.
2. `POST /api/ingest-repo` with HTTP, non-GitHub host, or extra path segment — expect immediate `422` JSON validation error.

**Variables:** Dataset-provided URL and expected failure mode.

**State transitions:** The nonexistent GitHub case should not produce a completed scope; invalid URLs never enter the stream.

**Cleanup:** None normally. If a failure happens after deletion/writes in a different test scenario, manual inspection may be needed because ingestion is not atomic.

**Value:** Encodes the API's most counterintuitive contract and is useful for frontend/client debugging.

**Automation tier:** The `422` cases are deterministic. A live GitHub 404 case is generally stable but still depends on network access/rate limits.

### Workflow 3: Repository-scoped source isolation

**Purpose:** Demonstrate that a Neo4j element ID cannot retrieve source through a different repository scope.

**Requests:**

1. Ingest repository A and capture a Function node ID.
2. Ingest repository B.
3. Fetch A's node ID with A's scope — expect `200`.
4. Fetch A's node ID with B's scope — expect `404`.
5. Read each graph separately and verify both are addressable.
6. Delete A, verify B remains; then delete B.

**Variables:** `repo_a_name`, `repo_a_node_id`, `repo_b_name`.

**State transitions:** Two independent scopes coexist; cross-scope source lookup fails; scoped deletion removes only its target.

**Cleanup:** Delete both repositories even if an assertion fails. Because collection runners do not provide transactional cleanup, keep a dedicated cleanup folder that can be run manually.

**Value:** Demonstrates one of the repository's strongest correctness properties to reviewers.

**Automation tier:** Manual or scheduled only. Two full ingestions are too costly and slow for the default PR path.

### Workflow 4: Graph payload privacy/minimization

**Purpose:** Verify that bulk graph reads omit stored source and embeddings while the scoped source endpoint still works.

**Requests:**

1. Ingest a repository or reuse the golden-path scope.
2. `GET /api/graph` — assert `raw_code` and `embedding` are absent recursively.
3. Capture a Function node ID.
4. `GET /api/node/{id}/code` — assert source is available on demand.

**Variables:** `active_repo_name`, `function_node_id`.

**State transitions:** None after ingestion; this compares two representations of the same stored graph.

**Cleanup:** Reuse golden-path cleanup.

**Value:** Provides an executable demonstration of a deliberate data-minimization boundary. It does not imply authorization; both endpoints are unauthenticated.

### Workflow 5: Graph-RAG metrics contract

**Purpose:** Validate the public chat envelope without trying to test LLM wording.

**Requests:**

1. Ingest and capture `total_repo_tokens`.
2. `POST /api/chat` with a repository-specific structural question.
3. Optionally ask a semantic question to exercise OpenAI query embedding plus the Anthropic agent.

**Variables:** `active_repo_name`, `ingestion_total_tokens`, `chat_question`.

**Assertions:** Nonblank answer; numeric fields; baseline equals ingestion total; tokens-saved arithmetic is consistent; efficiency is finite. Do not require a particular tool call or text.

**State transitions:** None in the database; external provider usage occurs.

**Cleanup:** Delete the ingested scope.

**Value:** Makes the project's Graph-RAG efficiency claim directly inspectable while respecting model nondeterminism.

**Automation tier:** Manual or protected live environment. Avoid required PR execution unless cost, rate limits, model availability, and secret handling are accepted.

### Workflow 6: Webhook authentication boundary

**Purpose:** Make GitHub signature failures reproducible and verify exact request-body signing.

**Requests:**

1. Signed JSON object with an unsupported/benign event type — expect `202`.
2. Same body without signature — expect `401` with missing-header detail.
3. Same body with a signature computed over different bytes — expect `401` invalid-signature detail.
4. Correctly signed malformed JSON — expect `400` valid-JSON detail.
5. Correctly signed JSON array/string — expect `400` object-required detail.

**Variables:** Private `webhook_secret`, request-local raw body and signature.

**State transitions:** The benign accepted event schedules a background task but should have no graph effect if required repository/SHA metadata is absent.

**Cleanup:** None.

**Value:** High for webhook setup and debugging, especially because the active route lacks focused native tests and GitHub's UI reports only delivery-level status.

**Automation tier:** Deterministic and suitable for a blocking API smoke folder once service startup is automated.

### Workflow 7: Repository deletion semantics

**Purpose:** Document both delete forms and their current idempotent outcome.

**Requests:**

1. Explicit path delete for a known scope — expect `200`.
2. Repeat the path delete — still expect `200` and the same success envelope.
3. Body delete with `.git` and surrounding whitespace — expect normalized `repo_name`.
4. Invalid extra-segment path/body — expect `422`.

**Variables:** `active_repo_name` or a dedicated disposable scope.

**State transitions:** Existing → absent → remains absent.

**Cleanup:** Intrinsic to the workflow.

**Value:** Useful for debugging the frontend's explicit and unload cleanup behavior and for clarifying that delete does not return `404` for an already-missing scope.

### Workflow 8: Liveness-versus-dependency diagnostic drill

**Purpose:** Show operators that `/health` is not dependency readiness.

**Requests:**

1. With the API running but Neo4j intentionally unavailable, `GET /health` — expect `200` if the already-started process remains running.
2. `GET /api/graph?repo_name=owner/repository` — expect `503` and the Neo4j-unavailable detail.

**Variables:** `base_url`, a syntactically valid scope.

**State transitions:** Requires an operator-controlled dependency outage. Application startup itself fails if Neo4j is unavailable before startup completes, so this drill applies to a post-start outage.

**Cleanup:** Restart Neo4j/API as needed; this must never run in the normal collection sequence.

**Value:** Prevents a misleading operational interpretation of the health endpoint.

**Automation tier:** Manual diagnostics only.

### Deferred workflow: webhook-to-graph completion

A real signed push → wait → graph verification scenario is attractive but should be deferred. Today the `202` response has no job or delivery identifier, background failures are log-only, removed files are not reconciled, and no status endpoint supports deterministic polling. Implementing a Postman delay loop would hide the architectural gap and create a flaky test. Revisit this after durable webhook jobs/status are added.

---

## 7. API documentation and OpenAPI strategy

### What exists

FastAPI generates `/docs` and `/openapi.json` from route signatures and Pydantic request models. This already provides discoverability and authoritative request validation for `ChatRequest`, `IngestRepositoryRequest`, and `RepositoryCleanupRequest`.

### What the generated contract cannot currently express well

- The ingestion endpoint is a streaming `StreamingResponse`; the sequence and terminal-success/error record variants are described in code/README rather than strong response models.
- Graph nodes and edges use broad `dict[str, Any]` shapes and Neo4j-derived properties.
- The webhook accepts a raw arbitrary JSON object, and signature behavior lives in a dependency rather than an OpenAPI security scheme.
- Error responses such as `401`, `400`, `404`, `500`, `502`, and `503` are not comprehensively declared as route response models.
- Operational facts—graph `LIMIT 200`, destructive replacement, background-only completion, and startup cleanup—are not machine-readable contracts.

### Source-of-truth recommendation

1. Keep **FastAPI route definitions and Pydantic models** as the application contract source of truth.
2. In a later implementation ticket, improve response models/descriptions/examples in FastAPI, especially for graph, chat, delete, and webhook responses. Document NDJSON with explicit OpenAPI media type and examples even if the stream remains hard to model fully.
3. Export or fetch the generated OpenAPI document in CI and import/generate the basic Postman request skeleton from it.
4. Maintain workflow ordering, HMAC logic, NDJSON parsing, captured variables, negative datasets, and cleanup scripts in the source-controlled Postman collection.
5. Treat updates as one-way: application/OpenAPI → collection skeleton/contract review. Do not make two-way Postman edits authoritative over Python routes.
6. Add a drift check only after the response schema is sufficiently explicit; otherwise it will create noisy confidence around an underspecified contract.

Postman can generate and synchronize a collection from OpenAPI 2.0/3.x, but synchronization settings and orphan handling require care. See [Generate collections from an API specification](https://learning.postman.com/docs/design-apis/specifications/generate-collections). For this project, generated requests should coexist with a curated workflow layer rather than overwrite it.

---

## 8. Runner, CLI, and CI/CD recommendation

### Local Collection Runner

The runner is immediately useful for:

- the ordered golden path;
- webhook signature cases;
- input-validation datasets;
- repeatable reviewer/interviewer demonstrations; and
- cleanup verification.

Configure the golden path for one iteration and serial execution. A long request timeout is necessary for ingestion and chat. Do not set iteration counts greater than one for the full ingestion folder by default.

### Postman CLI versus Newman

Use the current Postman CLI for any new automation. It runs local collection files, accepts environment files/overrides, supports iteration data, and can emit JSON/JUnit/HTML reports. Current Postman guidance explicitly recommends it over Newman for new workflows because Newman is not compatible with collection v3 used in Postman v12.

If the project has a hard requirement for a completely open-source runner and intentionally keeps collection v2.1, Newman is viable, but that constraint does not exist in this repository. Choosing Newman now would be an unnecessary limitation.

### CI sequencing

There is no CI workflow today. Recommended order of implementation:

1. Add deterministic native CI first: install backend dependencies, run pytest, run frontend Node tests, and run the Vite build.
2. Start a pinned compatible Neo4j+GDS service and run the live database tests.
3. Add a small Postman **contract smoke** folder against a running Uvicorn process:
   - health;
   - unscoped graph;
   - validation errors;
   - webhook signature boundary; and
   - delete idempotency against a disposable scope.
4. Only after secret/cost policy is decided, add the full live golden path as manual dispatch, nightly, pre-release, or post-deployment validation.

### What should block CI

- Collection parsing/script errors.
- Liveness failure after the service has been started.
- Wrong status/content type or response envelope for deterministic routes.
- Acceptance of invalid repository identifiers.
- Webhook signature bypass.
- Failure to delete only the target disposable scope in a controlled environment.
- In a deliberately enabled live smoke job, any NDJSON `error`, missing terminal record, unusable graph, failed source lookup, or inconsistent chat metrics.

### What should not block every pull request

- Exact LLM answer content or community labels.
- Tight latency thresholds for ingestion/chat.
- GitHub rate-limit or provider availability failures in a job not provisioned as a supported live integration environment.
- A two-repository isolation demo requiring two paid ingestions.

### Services and secrets needed for the full job

- Neo4j with a compatible GDS plugin and matching credentials.
- Installed backend dependencies and Uvicorn running from `backend/`.
- `OPENAI_API_KEY` for ingestion, labeling, and semantic search.
- `ANTHROPIC_API_KEY` for chat.
- Optional `GITHUB_TOKEN` for rate limit/private access.
- A separate `GITHUB_WEBHOOK_SECRET` injected into both backend and Postman job context for signature tests.

The Postman job should receive only `base_url` and webhook signing data. Provider/database secrets belong to the backend service environment.

---

## 9. Mocks, monitors, contracts, and performance

### Mock servers: do not add now

Postman mock servers return saved or scripted HTTP responses and can be useful before an API exists. Codegraph's problem is different: the API exists, while its expensive dependencies are GitHub, OpenAI, Anthropic, Neo4j, and GDS.

Current code does not expose configurable provider base URLs suitable for redirecting SDK calls to Postman mocks. A mock of the Codegraph API itself would mostly duplicate `frontend/src/api.test.js` fetch stubs and would not reproduce streaming cadence, graph analytics, or agent behavior. Static examples are still valuable for documentation; a deployed mock server is not.

Reconsider a mock only if one of these becomes real:

- frontend development must proceed independently of a changing backend contract;
- a hosted UI demo needs a safe synthetic backend;
- provider base URLs become injectable and deterministic integration simulation is desired; or
- the API is redesigned around durable job resources that can be modeled statefully.

### Monitors: defer

Postman monitors are intended for scheduled health/workflow validation and alerts. Codegraph has no deployed service, no application auth, and only a process-liveness endpoint. A cloud monitor cannot reach localhost; private API monitoring adds infrastructure/plan complexity. Monitoring `/health` alone would miss Neo4j and all providers, while scheduled ingestion/chat would incur cost and mutate ephemeral state.

If a staging service is later deployed, start with a low-frequency read-only readiness endpoint after the application implements one. Then consider a separate scheduled disposable-repository workflow with guaranteed cleanup. Current Postman documentation notes that public monitors run from Postman-hosted runners and internal APIs require private monitoring infrastructure; see [Postman monitors](https://learning.postman.com/docs/monitoring-your-api/setting-up-monitor).

### Contract/schema validation

Schema assertions add some value because the frontend is JavaScript rather than a generated typed client, but the collection should validate stable invariants instead of freezing Neo4j's dynamic node properties.

Recommended stable checks:

- named top-level fields and primitive types;
- required nested chat metrics;
- graph arrays and edge identifier relationships;
- absence of source/embedding data in graph nodes;
- normalized repository names;
- FastAPI error envelope shapes; and
- NDJSON record variants.

Avoid exhaustive schemas for every node property until explicit backend response models exist. Otherwise Postman becomes a second accidental schema source.

### Performance checks

Use response time only as informational telemetry initially. A very loose threshold for `/health` or a small graph read can catch a hung deployment. Do not enforce a universal threshold for:

- ingestion, which varies with repository size and multiple providers;
- chat, which depends on agent turns and model latency;
- webhook completion, which is asynchronous and unobservable; or
- graph size, which is capped and data-dependent.

Serious load/concurrency work should use a dedicated tool and a controlled dataset. The highest-risk behavior—two concurrent same-scope ingestions interleaving replacement writes—requires concurrency orchestration and database-state inspection that a normal Postman collection is not well suited to provide.

---

## 10. Developer experience and portfolio impact

A strong newcomer path would become:

1. clone the repository;
2. install the declared dependencies and start Neo4j, FastAPI, and optionally the dashboard;
3. import the collection and secret-free local environment;
4. add the local webhook secret only if running webhook cases;
5. run the golden-path folder;
6. inspect the live ingestion stages, graph payload, on-demand source, agent metrics, and verified cleanup; and
7. open the React dashboard to see the same data visualized.

The collection makes several technically impressive aspects visible without reading implementation first:

- a long-running NDJSON pipeline with concrete phases;
- repository-scoped graph state;
- exact source withheld from bulk graph payloads and fetched on demand;
- architectural community metadata produced after GDS clustering;
- a Graph-RAG answer accompanied by transparent context-selection metrics;
- cross-scope source isolation;
- signed webhook verification; and
- explicit state cleanup.

It also honestly exposes boundaries that strengthen an engineering discussion: liveness versus readiness, HTTP `200` stream failures, non-atomic replacement, nondeterministic/costly AI calls, incomplete webhook reconciliation, and the lack of auth/durable jobs. This is more credible portfolio material than a collection that shows only happy-path `200` assertions.

---

## 11. What should not use Postman

| Concern | Correct owner/tool | Why not Postman |
| --- | --- | --- |
| Tree-sitter language parsing and source spans | pytest unit tests | Requires precise fixtures and internal return values, not HTTP. |
| Neo4j Cypher scoping and batching | pytest mocks + live Neo4j integration tests | Needs transaction/query inspection and controlled database fixtures. |
| GDS cleanup on exceptions | pytest failure injection | Not observable through a stable public response after partial ingestion. |
| Embedding order/dimensions | pytest service tests | Faster and deterministic with mocked provider responses. |
| Agent tool selection/context extraction | pytest with mocked agent trace | Exact LLM orchestration is not a stable black-box assertion. |
| React graph rendering and interaction | Component/browser tests | Postman does not render or interact with the UI. |
| Accessibility and visual layout | Browser/accessibility tooling | HTTP payload tests cannot validate these. |
| Database migration/index correctness | Native integration tests/startup checks | Requires direct database inspection. |
| Load, soak, and race testing | k6, Locust, Gatling, or a purpose-built async harness | Requires controlled concurrency, rates, and meaningful latency distributions. |
| Security testing beyond known contracts | Dedicated SAST/DAST/dependency tools and threat review | A handful of negative requests is not a security program. |
| Production observability | Metrics, tracing, logs, alerting | Postman monitors are outside-in checks, not application telemetry. |
| Durable webhook completion | Application job/status design | Client-side delays cannot manufacture a reliable completion signal. |

---

## 12. Ticket-ready implementation roadmap

### P0 — Native reproducibility prerequisite

**Goal:** Ensure a fresh environment can install all `backend/requirements.txt` packages and run the backend suite before layering on external smoke tests.

**Acceptance criteria:** Documented install command works from a clean environment; backend tests collect; native backend/frontend checks run in CI; Neo4j integration skips are explicit or backed by a service.

### P1 — Source-controlled Postman collection and local environment

**Goal:** Add the folders, requests, examples, variable descriptions, and local environment template described above.

**Acceptance criteria:** No secrets committed; all active endpoints represented; legacy endpoints excluded; README has import/run instructions; manual requests use `{{base_url}}`.

### P1 — Golden-path chaining and cleanup

**Goal:** Implement robust NDJSON parsing, capture repository/node variables, validate graph/source/chat invariants, and always provide explicit cleanup.

**Acceptance criteria:** One runner execution demonstrates ingest → graph → source → chat → delete; streamed errors fail the run; stale variables are cleared; scripts do not assert LLM prose.

### P1 — Webhook HMAC contract folder

**Goal:** Generate correct `X-Hub-Signature-256` from exact request bytes and cover `202`, `401`, and `400` boundaries.

**Acceptance criteria:** Populated secret stays local/CI-only; valid and invalid cases are reproducible; the collection states that `202` does not prove background completion.

### P2 — Improve FastAPI/OpenAPI response contracts

**Goal:** Add explicit stable response models, documented error responses, webhook descriptions, and NDJSON media-type/examples.

**Acceptance criteria:** `/openapi.json` accurately describes stable request/response envelopes; graph dynamic fields are bounded sensibly; Postman generation does not erase custom workflow scripts.

### P2 — Data-driven deterministic smoke folder

**Goal:** Add validation/error datasets and a fast folder that does not call paid model providers.

**Acceptance criteria:** Runs against a started backend; tests health, validation, webhook signing, and safe delete behavior; emits a machine-readable CLI report.

### P2 — CI integration

**Goal:** Run the deterministic Postman folder only after native tests and service startup are established.

**Acceptance criteria:** Pinned CLI/action version; secret injection through CI; no provider keys stored in Postman files; failures block only on deterministic assertions; results are retained as artifacts.

### P3 — Optional live end-to-end smoke

**Goal:** Run the golden path manually, nightly, pre-release, or post-deployment with explicit cost and external-dependency expectations.

**Acceptance criteria:** Dedicated small public repository; serialized execution; cleanup on normal completion; documented rate-limit/provider failure policy; not a default required PR check.

### Deferred — monitors, mocks, and webhook completion workflow

Do not ticket these until the project has a deployed environment, readiness semantics, application authentication, configurable dependency endpoints, or durable webhook jobs/status. Their prerequisites matter more than the Postman artifacts themselves.

---

## Final conclusion

Postman can improve Codegraph most as an **executable narrative and black-box workflow harness**, not as a replacement testing platform. The API is small enough to keep the maintenance burden contained, yet stateful and unusual enough—NDJSON terminal errors, graph-to-source chaining, model-backed chat metrics, two cleanup forms, and exact HMAC signing—that a well-designed collection provides real value.

The recommended investment is modest: one collection, one local environment template, two small datasets, and later one deterministic CLI smoke job. Keep FastAPI/OpenAPI authoritative, keep pytest and Node tests primary, keep provider/database secrets on the server side, and defer mocks/monitors/load tests until the architecture gives them a concrete job to do.
