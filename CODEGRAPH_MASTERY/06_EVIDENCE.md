# Evidence ledger — pinned revision and reproducible boundaries

[Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](05_MOCK_INTERVIEWS.md) · [Next](07_FINAL_REVIEW.md)

## Contents

- [Revision and inspection census](#revision-and-inspection-census)
- [Current validation record](#current-validation-record)
- [Dependency and runtime record](#dependency-and-runtime-record)
- [Tracked file census](#tracked-file-census)
- [Active Python symbol index](#active-python-symbol-index)
- [Active query and prompt definitions](#active-query-and-prompt-definitions)
- [Complete active test inventory](#complete-active-test-inventory)
- [Git chronology](#git-chronology)
- [Benchmark search and documentary discrepancies](#benchmark-search-and-documentary-discrepancies)
- [External primary references consulted](#external-primary-references-consulted)

---

## Revision and inspection census

- Branch: `main`
- HEAD: `79fa7689754af893e871436a911a0c4d245c6a43`
- Initial working tree: clean. No source/config/schema/history modifications were made.
- Evidence date: 2026-09-24. All source line numbers refer to this revision.
- Full active implementation, tests, configuration definitions, frontend helpers/components, documentation, Postman scripts and available Git history were inspected. Legacy prototype behavior was kept separate. Generated dependency directories were used for version/default inspection, not treated as application source.
- No application startup, database mutation, real model inference, repository ingestion, live Postman lifecycle or external repository modification was performed. Public packages were downloaded to a temporary directory for isolated testing.
- Configured API-key presence was checked without printing values: OpenAI present, Anthropic present, GitHub token absent; webhook secret configured/defaulted. Presence does not verify validity, entitlement or model availability.

## Current validation record

| Check | Outcome | Boundary |
|---|---|---|
| Saved backend venv test collection | 10 import errors; only 10 cases collected before errors | Missing openai/tiktoken and several grammar distributions. |
| Temporary-dependency backend run | 92 passed, 4 skipped, 3 warnings, 2.55 s | TCP connects disabled; Neo4j target overridden to unused localhost port in process; existing tests, no source edits. |
| Frontend Node tests | 13 passed, 0 failures | API helpers and utilities; no browser/component execution. |
| Vite build | Passed, 1292 transformed modules | Temporary output; main JS 631.14 kB / 199.13 kB gzip, CSS 49.31 kB / 9.71 kB gzip; large-chunk warning. |
| Additional local probes | Passed | Actual grammar→ETL transformations, temporary ZIP traversal fixture, direct HMAC dependency with fixture secret; no network/DB/model. |
| Live database, ANN, GDS, provider, browser and Postman workflows | Not run | Not established by mocked tests or static query inspection. |

The four skipped tests are `test_neo4j_ast_write`, `test_api_graph_endpoint`, `test_delete_repository_graph_removes_only_scoped_nodes`, and `test_blast_radius_does_not_cross_repository_boundaries` in `backend/tests/test_pipeline.py`. Their fixtures delete test-scoped persistent nodes and were intentionally prevented from contacting a database.

### Backend command used

```python
import os, sys, socket
sys.path.insert(0, '/private/tmp/codegraph-mastery-deps')
sys.path.insert(0, str(repository_root / 'backend'))
os.environ['NEO4J_URI'] = 'bolt://127.0.0.1:1'
def no_network(*args, **kwargs):
    raise OSError('Network disabled for read-only audit')
socket.socket.connect = no_network
import pytest
pytest.main(['backend/tests', '-q', '-p', 'no:cacheprovider',
             '--basetemp=/private/tmp/codegraph-mastery-pytest-tmp'])
```

The process also used `PYTHONDONTWRITEBYTECODE=1`. Dependencies were added only to the temporary import path. Commands are a record, not instructions to run potentially mutating live integration tests against a valuable database.

### Exact backend result

```text
........................................................................ [ 75%]
...sss.......s..........                                                 [100%]
=============================== warnings summary ===============================
backend/.venv/lib/python3.13/site-packages/starlette/testclient.py:53
  /Users/sitanshusingh/Documents/AI Software Engineer/backend/.venv/lib/python3.13/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

backend/tests/test_ingest_repo.py::test_ingest_repository_rejects_non_github_url
backend/tests/test_repository_deletion.py::test_delete_repository_endpoint_rejects_invalid_scope
  /Users/sitanshusingh/Documents/AI Software Engineer/backend/.venv/lib/python3.13/site-packages/fastapi/routing.py:352: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    return await dependant.call(**values)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
92 passed, 4 skipped, 3 warnings in 2.55s
```

### Additional probe results

The five snippets verify the critical parser/persistence distinction without a database. Python correctly owns x under a and y under b, while ETL produces four calls; Java overload records have separate IDs but flatten to one legacy function. The following output is from this audit, not fabricated sample provider responses.

```jsonl
{"file": "x.py", "lexical": [{"qualified_name": "a", "signature": "()", "has_body": true, "calls": ["x"]}, {"qualified_name": "b", "signature": "()", "has_body": true, "calls": ["y"]}], "unattributed": [], "legacy_functions": ["a", "b"], "legacy_calls": [["a", "x"], ["a", "y"], ["b", "x"], ["b", "y"]]}
{"file": "x.js", "lexical": [{"qualified_name": "f", "signature": "(x)", "has_body": true, "calls": ["send"]}, {"qualified_name": "outer", "signature": "()", "has_body": true, "calls": ["run", "visible"]}], "unattributed": ["hidden"], "legacy_functions": ["f", "outer"], "legacy_calls": [["f", "send"], ["f", "run"], ["f", "hidden"], ["f", "visible"], ["outer", "send"], ["outer", "run"], ["outer", "hidden"], ["outer", "visible"]]}
{"file": "x.ts", "lexical": [{"qualified_name": "V.check", "signature": "(x: string)", "has_body": false, "calls": []}, {"qualified_name": "V.check", "signature": "(x: any)", "has_body": true, "calls": ["validate"]}], "unattributed": [], "legacy_functions": ["check"], "legacy_calls": [["check", "validate"]]}
{"file": "x.go", "lexical": [{"qualified_name": "A.F", "signature": "()", "has_body": true, "calls": ["g"]}], "unattributed": [], "legacy_functions": ["F"], "legacy_calls": [["F", "g"]]}
{"file": "x.java", "lexical": [{"qualified_name": "V.check", "signature": "(String x)", "has_body": true, "calls": ["validate"]}, {"qualified_name": "V.check", "signature": "(int x)", "has_body": true, "calls": ["validate"]}], "unattributed": [], "legacy_functions": ["check"], "legacy_calls": [["check", "validate"]]}
Archive traversal fixture: rejected before extraction
HMAC dependency fixtures: missing/invalid rejected; correct exact-byte signature accepted
Configuration availability (presence only): {"GITHUB_TOKEN": false, "OPENAI_API_KEY": true, "ANTHROPIC_API_KEY": true, "GITHUB_WEBHOOK_SECRET": true}
No external network, model invocation, or database write was allowed.
```

## Dependency and runtime record

Python project requirements are unpinned. Existing saved environment: Python 3.13.5; fastapi 0.141.1; pydantic 2.13.4; pydantic-settings 2.15.0; uvicorn 0.52.3; httpx 0.28.1; langgraph 1.2.11; langchain-anthropic 1.5.6; neo4j 6.2.0; pytest 9.1.1; tree-sitter 0.26.0; tree-sitter-python 0.25.0; tree-sitter-typescript 0.23.2. OpenAI, tiktoken, JS/Go/Java grammar distributions were absent.

The temporary overlay installed openai 3.19.2, tiktoken 0.14.0, JS/Go grammars 0.25.0 and Java grammar 0.23.5. Its dependency resolution also supplied pydantic 2.13.5, pydantic-core 2.46.5, anyio 4.15.1, httpx2/httpcore2 2.13.1, jiter 0.17.0, typing-extensions 4.16.0, regex 2026.9.10 and requests 2.34.2. These are audit environment facts, not newly pinned repository requirements.

Node v26.7.0; frontend lock resolves React/React DOM 19.2.8, @xyflow/react 12.11.3, d3-force 3.0.0, react-markdown 10.1.0, react-syntax-highlighter 16.1.1, remark-gfm 4.0.1, Tailwind 4.3.3 and Vite 7.3.6. Compose declares Neo4j 2026.07.1 and startup GDS plugin resolution; live server/GDS/Cypher defaults unverified.

### Locally inspected framework defaults

- `backend/.venv/lib/python3.13/site-packages/langgraph/prebuilt/chat_agent_executor.py`: default state messages/add_messages plus remaining_steps; create_react_agent default version v2; tool routing/remaining-step handling delegated to library.
- `langgraph/prebuilt/tool_node.py:383`: default handler returns ToolInvocationError messages and raises other exceptions; `:1268` returns an error ToolMessage for an unknown tool name.
- `langgraph/_internal/_config.py:32`: `LANGGRAPH_DEFAULT_RECURSION_LIMIT` environment override, otherwise 10007 in this installed version. The application does not set its own limit.
- `langchain_anthropic/chat_models.py:980/999/1003`: max_tokens and timeout fields default None in inspected class, max_retries 2. Application does not explicitly override those values.
- The prebuilt AgentStatePydantic example default of 25 must not be confused with the default TypedDict runtime path. No live agent call was used to measure these defaults.

## Tracked file census

Binary metadata/store files are listed for completeness; they are not architecture evidence. Environment examples are identified but credential values are not reproduced.

```text
.DS_Store
.env.example
.gitignore
.pnpm-store/v11/index.db
.pnpm-store/v11/projects/b42b7e462a52f91015b1ef8365995382
CG-001-architecture-investigation.md
POSTMAN_TECHNICAL_ASSESSMENT.md
README.md
agent.py
app/.DS_Store
app/__init__.py
app/main.py
backend/.env.example
backend/FUNCTION_IDENTITY.md
backend/README.md
backend/app/__init__.py
backend/app/agent/__init__.py
backend/app/agent/graph.py
backend/app/api/__init__.py
backend/app/api/dependencies.py
backend/app/api/webhooks.py
backend/app/config.py
backend/app/db/__init__.py
backend/app/db/gds_ops.py
backend/app/db/graph_ops.py
backend/app/db/neo4j_client.py
backend/app/main.py
backend/app/services/__init__.py
backend/app/services/community_summarizer.py
backend/app/services/embedding_service.py
backend/app/services/github_service.py
backend/app/services/parser_service.py
backend/app/services/pipeline.py
backend/app/utils/__init__.py
backend/app/utils/entity_identity.py
backend/app/utils/tokens.py
backend/ingest_local_repo.py
backend/requirements.txt
backend/seeding.py
backend/tests/__init__.py
backend/tests/test_agent_tools.py
backend/tests/test_community_summarizer.py
backend/tests/test_database_initialization.py
backend/tests/test_embedding_service.py
backend/tests/test_function_identity.py
backend/tests/test_gds_ops.py
backend/tests/test_graph_scoping.py
backend/tests/test_graph_serialization.py
backend/tests/test_ingest_repo.py
backend/tests/test_parser_service.py
backend/tests/test_pipeline.py
backend/tests/test_repository_deletion.py
backend/tests/test_tokens.py
database.py
docker-compose.yml
dockerTest.py
frontend/index.html
frontend/package.json
frontend/pnpm-lock.yaml
frontend/pnpm-workspace.yaml
frontend/src/App.jsx
frontend/src/api.js
frontend/src/api.test.js
frontend/src/colors.test.js
frontend/src/communities.test.js
frontend/src/components/CodePanel.tsx
frontend/src/components/GraphLegend.tsx
frontend/src/index.css
frontend/src/main.jsx
frontend/src/utils/colors.js
frontend/src/utils/communities.js
frontend/vite.config.js
parse_python.py
postman/README.md
postman/collections/codegraph-api.postman_collection.json
postman/environments/codegraph-local.example.postman_environment.json
requirements.txt
tests/test_webhook.py
```

## Active Python symbol index

| File | Symbol and line |
|---|---|
| `backend/app/agent/graph.py` | `query_graph_blast_radius`:104, `list_codebase_structure`:141, `list_functions_in_file`:163, `query_outgoing_dependencies`:195, `list_external_dependencies`:237, `semantic_code_search`:267, `analyze_architectural_subsystems`:318, `_get_code_agent`:336, `_message_text`:355, `_tool_context_text`:369, `_run_code_agent`:384, `ask_code_agent`:418, `ask_code_agent_with_metrics`:425 |
| `backend/app/api/dependencies.py` | `verify_github_signature`:9 |
| `backend/app/api/webhooks.py` | `github_webhook`:23 |
| `backend/app/config.py` | `Settings`:9 |
| `backend/app/db/__init__.py` | `get_neo4j_driver`:52, `close_neo4j_driver`:64, `_json_value`:73, `_serialize_node`:88, `_serialize_relationship`:141, `fetch_graph_data`:166, `fetch_node_code`:213, `fetch_repository_total_tokens`:235 |
| `backend/app/db/gds_ops.py` | `run_leiden_clustering`:53 |
| `backend/app/db/graph_ops.py` | `DatabaseWriteProgress`:94, `chunk_data`:101, `_string_list`:113, `_extract_etl_records`:123, `_function_embedding_text`:208, `_resolve_total_repo_tokens`:217, `save_parsed_ast_to_neo4j_with_progress`:238, `run_transaction`:260, `execute`:265, `save_parsed_ast_to_neo4j`:327, `delete_repository_graph`:344, `delete`:351, `delete_all_repository_graphs`:362, `delete`:365 |
| `backend/app/db/neo4j_client.py` | `_initialize_driver`:45, `initialize_database`:70, `get_db_session`:94, `close_driver`:117 |
| `backend/app/main.py` | `lifespan`:61, `ChatRequest`:73, `message_must_not_be_blank`:81, `repo_name_must_be_canonical`:91, `IngestRepositoryRequest`:97, `url_must_not_be_blank`:104, `RepositoryCleanupRequest`:113, `repo_name_must_be_canonical`:120, `_normalize_repo_identifier`:126, `_parse_github_repository_url`:139, `_discover_repository_source_files`:154, `_use_repository_relative_paths`:170, `get_graph`:210, `get_node_code`:249, `_delete_repository_scope`:301, `cleanup_repository`:329, `delete_repository`:336, `chat`:350, `_ndjson_record`:370, `_stream_repository_ingestion`:376, `ingest_repository`:521, `health_check`:545 |
| `backend/app/services/community_summarizer.py` | `CommunityLabel`:53, `strip_text`:61, `_get_community_label_client`:69, `_string_list`:76, `_generate_community_label`:82, `label_and_store_communities`:110, `replace_communities`:146 |
| `backend/app/services/embedding_service.py` | `_get_embedding_client`:18, `generate_embeddings`:27, `generate_embedding`:54 |
| `backend/app/services/github_service.py` | `_github_headers`:29, `_extract_zip_safely`:38, `download_and_extract_repo`:59, `cleanup_downloaded_repo`:106, `fetch_raw_file_content`:114 |
| `backend/app/services/parser_service.py` | `_LanguageQueries`:167, `ParsedFileProgress`:176, `CodeParser`:186, `__init__`:214, `_compile_python_queries`:269, `_compile_typescript_queries`:281, `_compile_javascript_queries`:295, `_compile_go_queries`:309, `_compile_java_queries`:321, `_normalize_extension`:333, `get_parser`:347, `_capture_text`:360, `_text`:381, `_lexical_scope`:387, `_definition_body`:419, `_signature`:426, `_qualified_name`:438, `_line_end`:460, `_capture_function_records`:464, `_capture_call_sites`:519, `_parse_source`:601, `parse_file`:651, `attach_function_entity_ids`:706, `parse_changed_files_with_progress`:737, `parse_path`:755, `parse_changed_files`:813 |
| `backend/app/services/pipeline.py` | `_unique_paths`:17, `_extract_push_files`:23, `_extract_pull_request_files`:39, `_extract_repository`:63, `_extract_commit_sha`:89, `process_github_event`:111, `fetch_and_parse`:152 |
| `backend/app/utils/entity_identity.py` | `normalize_repository_path`:16, `generate_function_entity_id`:37 |
| `backend/app/utils/tokens.py` | `_encoding_for_model`:14, `count_tokens`:23 |

## Active query and prompt definitions

These exact definitions are included to make query claims inspectable without a database. Execution/performance analysis is in [Cypher query atlas](01_FOUNDATIONS.md#8-cypher-query-atlas-and-complexity). Query presence proves implementation, not live syntax acceptance.

### `backend/app/agent/graph.py:21` — CALLERS_QUERY

```cypher
MATCH (caller:Function {repo_name: $repo_name})-[:CALLS]->
      (target:Function {name: $func_name, repo_name: $repo_name})
OPTIONAL MATCH (file:File {repo_name: $repo_name})-[:DEFINES]->(caller)
RETURN DISTINCT caller.name AS caller,
       collect(DISTINCT file.path) AS file_paths,
       coalesce(target.is_external, false) AS target_is_external
ORDER BY caller
LIMIT 100
```

### `backend/app/agent/graph.py:32` — CODEBASE_STRUCTURE_QUERY

```cypher
MATCH (f:File {repo_name: $repo_name})
RETURN f.path AS file_path
ORDER BY f.path
```

### `backend/app/agent/graph.py:38` — FUNCTIONS_IN_FILE_QUERY

```cypher
MATCH (f:File {path: $file_path, repo_name: $repo_name})-[:DEFINES]->
      (fn:Function)
RETURN fn.name AS function_name
ORDER BY fn.name
```

### `backend/app/agent/graph.py:45` — OUTGOING_DEPENDENCIES_QUERY

```cypher
MATCH (caller:Function {name: $func_name, repo_name: $repo_name})-[:CALLS]->
      (target:Function {repo_name: $repo_name})
RETURN target.name AS target_name,
       target.file AS target_file,
       target.is_external AS is_external
ORDER BY target.name, target.file
```

### `backend/app/agent/graph.py:54` — EXTERNAL_DEPENDENCIES_QUERY

```cypher
MATCH (fn:ExternalFunction {repo_name: $repo_name})
RETURN fn.name AS function_name
ORDER BY fn.name
```

### `backend/app/agent/graph.py:60` — SEMANTIC_CODE_SEARCH_QUERY

```cypher
MATCH (node:Function)
  SEARCH node IN (
    VECTOR INDEX function_embeddings
    FOR $query_vector
    LIMIT $top_k
  ) SCORE AS score
WHERE node.repo_name = $repo_name
RETURN node.name AS function_name,
       node.file_path AS file_path,
       score
ORDER BY score DESC
```

### `backend/app/agent/graph.py:74` — ARCHITECTURAL_SUBSYSTEMS_QUERY

```cypher
MATCH (c:Community {repo_name: $repo_name})
OPTIONAL MATCH (f:Function {repo_name: $repo_name})-[:IN_COMMUNITY]->(c)
RETURN c.community_id AS id,
       c.name AS module_title,
       c.description AS module_description,
       count(f) AS function_count
ORDER BY function_count DESC
```

### `backend/app/agent/graph.py:84` — CODE_AGENT_SYSTEM_PROMPT

```text
You are an expert Senior Staff Engineer analyzing a codebase.
You MUST format your responses for maximum readability.
- Never output large walls of text.
- Use Markdown headings (`##`) to organize your thoughts.
- Use bullet points or numbered lists when listing functions, files, or steps.
- Enclose file names and function names in backticks (for example, `api.py` and `send()`).
- Use fenced code blocks with a language identifier (for example, ```python) when writing or displaying code snippets.
- Be concise, direct, and highly structured.

You are analyzing only the GitHub repository `{repo_name}`. When calling graph
tools, always use that exact repository name. Do not mix results from other
repositories.

When asked to explain the architecture or high-level structure of a repository,
use the `analyze_architectural_subsystems` tool. It returns labeled architectural
modules with a title, description, and function count. Use those stored labels
to present a high-level architectural summary.
```

### `backend/app/db/__init__.py:12` — GRAPH_QUERY

```cypher
MATCH (file:File {repo_name: $repo_name})
OPTIONAL MATCH (file)-[:DEFINES]->(function:Function {repo_name: $repo_name})
WITH collect(DISTINCT file) + collect(DISTINCT function) AS repository_nodes
UNWIND repository_nodes AS n
OPTIONAL MATCH (n)-[r:DEFINES|CALLS]->(m {repo_name: $repo_name})
OPTIONAL MATCH (n:Function)-[:IN_COMMUNITY]->(
    n_community:Community {repo_name: $repo_name}
)
OPTIONAL MATCH (m:Function)-[:IN_COMMUNITY]->(
    m_community:Community {repo_name: $repo_name}
)
RETURN n,
       r,
       m,
       n_community.name AS n_community_name,
       n_community.description AS n_community_description,
       m_community.name AS m_community_name,
       m_community.description AS m_community_description
LIMIT 200
```

### `backend/app/db/__init__.py:34` — NODE_CODE_QUERY

```cypher
MATCH (function:Function {repo_name: $repo_name})
WHERE elementId(function) = $node_id
RETURN function.raw_code AS code,
       function.file_path AS file_path,
       function.name AS name
LIMIT 1
```

### `backend/app/db/__init__.py:43` — REPOSITORY_TOKEN_QUERY

```cypher
MATCH (repository:Repository {repo_name: $repo_name})
RETURN coalesce(repository.total_tokens, 0) AS total_tokens
LIMIT 1
```

### `backend/app/db/gds_ops.py:12` — COUNT_REPOSITORY_FUNCTIONS_QUERY

```cypher
MATCH (f:Function {repo_name: $repo_name})
RETURN count(f) AS node_count
```

### `backend/app/db/gds_ops.py:17` — PROJECT_CODEBASE_GRAPH_QUERY

```cypher
MATCH (s:Function {repo_name: $repo_name})
OPTIONAL MATCH (s)-[r:CALLS]->(t:Function {repo_name: $repo_name})
WITH gds.graph.project(
  $graph_name,
  s,
  t,
  {
    sourceNodeLabels: labels(s),
    targetNodeLabels: labels(t),
    relationshipType: type(r)
  },
  {undirectedRelationshipTypes: ['*']}
) AS g
RETURN
  g.graphName AS graphName,
  g.nodeCount AS nodeCount,
  g.relationshipCount AS relationshipCount
```

### `backend/app/db/gds_ops.py:37` — RUN_LEIDEN_QUERY

```cypher
CALL gds.leiden.write(
  $graph_name,
  {writeProperty: 'leiden_community'}
)
YIELD communityCount, modularity
RETURN communityCount, modularity
```

### `backend/app/db/gds_ops.py:46` — DROP_CODEBASE_GRAPH_QUERY

```cypher
CALL gds.graph.drop($graph_name, false)
YIELD graphName
RETURN graphName
```

### `backend/app/db/graph_ops.py:17` — DELETE_REPOSITORY_QUERY

```cypher
MATCH (node)
WHERE (node:Repository OR node:File OR node:Function OR node:Community)
  AND node.repo_name = $repo_name
DETACH DELETE node
```

### `backend/app/db/graph_ops.py:24` — DELETE_REPOSITORY_GRAPH_QUERY

```cypher
MATCH (n {repo_name: $repo_name})
DETACH DELETE n
```

### `backend/app/db/graph_ops.py:29` — DELETE_ALL_REPOSITORY_GRAPHS_QUERY

```cypher
MATCH (n)
WHERE n.repo_name IS NOT NULL
DETACH DELETE n
```

### `backend/app/db/graph_ops.py:35` — MERGE_FILES_QUERY

```cypher
UNWIND $batch AS file
MERGE (repository:Repository {repo_name: $repo_name})
ON CREATE SET repository.name = $repo_name
MERGE (f:File {path: file.path, repo_name: $repo_name})
SET f.updated_at = datetime()
MERGE (repository)-[:CONTAINS]->(f)
```

### `backend/app/db/graph_ops.py:44` — MERGE_REPOSITORY_TOKENS_QUERY

```cypher
MERGE (repository:Repository {repo_name: $repo_name})
SET repository.name = $repo_name,
    repository.total_tokens = $total_tokens,
    repository.tokenizer_model = $tokenizer_model,
    repository.tokens_updated_at = datetime()
```

### `backend/app/db/graph_ops.py:52` — MERGE_FUNCTIONS_QUERY

```cypher
UNWIND $batch AS func
MATCH (f:File {path: func.file_path, repo_name: $repo_name})
MERGE (fn:Function {name: func.name, repo_name: $repo_name})
REMOVE fn:ExternalFunction
SET fn.file = coalesce(fn.file, func.file_path),
    fn.file_path = func.file_path,
    fn.raw_code = func.raw_code,
    fn.embedding = func.embedding,
    fn.external = false,
    fn.is_external = false
MERGE (f)-[:DEFINES]->(fn)
```

### `backend/app/db/graph_ops.py:66` — MERGE_CALLS_QUERY

```cypher
UNWIND $batch AS call
MATCH (caller:Function {
    name: call.caller_name,
    repo_name: $repo_name
})
MERGE (target:Function {
    name: call.target_name,
    repo_name: $repo_name
})
ON CREATE SET target.external = true
MERGE (caller)-[relationship:CALLS]->(target)
SET relationship.inferred_from_file_scope = true,
    relationship.source_files = CASE
        WHEN call.file_path IN coalesce(relationship.source_files, [])
        THEN coalesce(relationship.source_files, [])
        ELSE coalesce(relationship.source_files, []) + call.file_path
    END
```

### `backend/app/db/graph_ops.py:86` — TAG_EXTERNAL_FUNCTIONS_QUERY

```cypher
MATCH (fn:Function {repo_name: $repo_name})
WHERE NOT ()-[:DEFINES]->(fn)
SET fn:ExternalFunction, fn.is_external = true
```

### `backend/app/db/neo4j_client.py:20` — DATABASE_INDEX_QUERIES

```cypher
CREATE INDEX repository_repo_name IF NOT EXISTS FOR (r:Repository) ON (r.repo_name);
CREATE INDEX file_repo_path IF NOT EXISTS FOR (f:File) ON (f.repo_name, f.path);
CREATE INDEX func_repo_name IF NOT EXISTS FOR (fn:Function) ON (fn.repo_name, fn.name);
CREATE INDEX ext_func_repo_name IF NOT EXISTS FOR (ext:ExternalFunction) ON (ext.repo_name, ext.name);
CREATE INDEX community_repo_id IF NOT EXISTS FOR (c:Community) ON (c.repo_name, c.community_id);
CREATE INDEX func_repo_community IF NOT EXISTS FOR (fn:Function) ON (fn.repo_name, fn.leiden_community);
CREATE VECTOR INDEX `function_embeddings` IF NOT EXISTS FOR (fn:Function) ON (fn.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}};
```

### `backend/app/db/neo4j_client.py:40` — AWAIT_INDEXES_QUERY

```cypher
CALL db.awaitIndexes(300)
```

### `backend/app/services/community_summarizer.py:17` — COMMUNITY_LABEL_SYSTEM_PROMPT

```text
You are a senior software architect analyzing code clusters. Given a list of function names and file paths from a code repository module, infer the architectural purpose of this cluster. Return a concise module name and a one-sentence description.
```

### `backend/app/services/community_summarizer.py:24` — FETCH_COMMUNITIES_QUERY

```cypher
MATCH (f:Function {repo_name: $repo_name})
WHERE f.leiden_community IS NOT NULL
WITH f.leiden_community AS comm_id,
     collect(f.name)[..15] AS func_names,
     collect(DISTINCT f.file_path)[..5] AS file_paths
RETURN comm_id, func_names, file_paths
ORDER BY comm_id
```

### `backend/app/services/community_summarizer.py:34` — DELETE_COMMUNITIES_QUERY

```cypher
MATCH (c:Community {repo_name: $repo_name})
DETACH DELETE c
```

### `backend/app/services/community_summarizer.py:39` — STORE_COMMUNITIES_QUERY

```cypher
UNWIND $communities AS comm
MERGE (c:Community {repo_name: $repo_name, community_id: comm.id})
SET c.name = comm.name,
    c.description = comm.description
WITH c, comm
MATCH (f:Function {
    repo_name: $repo_name,
    leiden_community: comm.id
})
MERGE (f)-[:IN_COMMUNITY]->(c)
```

## Complete active test inventory

Names, source lines and parameterized case counts are extracted from the actual test syntax. Assertions are summarized in [the test-suite review](02_APPLICATION_AND_AUDIT.md#22-test-suite-and-postman); the list below permits precise follow-up reading.

### `backend/tests/test_agent_tools.py` — 11 cases

- `test_code_agent_system_prompt_requires_structured_markdown` at line 30 — 1 case.
- `test_list_codebase_structure_returns_newline_separated_paths` at line 63 — 1 case.
- `test_list_functions_in_file_formats_function_names` at line 80 — 1 case.
- `test_query_outgoing_dependencies_formats_targets_and_locations` at line 105 — 1 case.
- `test_blast_radius_surfaces_external_target_status` at line 138 — 1 case.
- `test_list_external_dependencies_formats_repository_boundary` at line 164 — 1 case.
- `test_semantic_code_search_embeds_and_formats_scoped_matches` at line 185 — 1 case.
- `test_analyze_architectural_subsystems_returns_scoped_communities` at line 237 — 1 case.
- `test_code_agent_registers_all_repository_tools` at line 259 — 1 case.
- `test_tool_context_includes_only_context_sent_by_graph_tools` at line 285 — 1 case.
- `test_code_agent_reports_graph_context_efficiency` at line 298 — 1 case.

### `backend/tests/test_community_summarizer.py` — 3 cases

- `test_label_and_store_communities_replaces_repository_labels_atomically` at line 26 — 1 case.
- `test_generate_community_label_uses_structured_output` at line 106 — 1 case.
- `test_label_and_store_communities_rejects_blank_repository` at line 136 — 1 case.

### `backend/tests/test_database_initialization.py` — 1 cases

- `test_initialize_database_creates_and_awaits_indexes_once` at line 8 — 1 case.

### `backend/tests/test_embedding_service.py` — 3 cases

- `test_generate_embeddings_batches_and_restores_response_order` at line 21 — 1 case.
- `test_generate_embedding_returns_the_single_vector` at line 46 — 1 case.
- `test_generate_embeddings_rejects_blank_input` at line 58 — 1 case.

### `backend/tests/test_function_identity.py` — 19 cases

- `test_same_name_in_different_files_has_different_entity_ids` at line 26 — 1 case.
- `test_same_named_methods_in_different_classes_are_distinct` at line 37 — 1 case.
- `test_repeated_python_definition_uses_occurrence_discriminator` at line 54 — 1 case.
- `test_java_overloads_are_distinguished_by_signature` at line 70 — 1 case.
- `test_typescript_overload_signatures_and_implementation_are_distinct` at line 88 — 1 case.
- `test_typescript_interface_methods_use_interface_scope` at line 113 — 1 case.
- `test_identity_is_deterministic_and_paths_are_normalized` at line 126 — 1 case.
- `test_full_ingest_attaches_identity_after_temporary_path_is_relativized` at line 148 — 1 case.
- `test_identity_rejects_non_relative_paths` at line 168 — 3 cases.
- `test_function_calls_are_attributed_to_the_enclosing_body` at line 173 — 1 case.
- `test_anonymous_callback_call_is_not_assigned_to_outer_function` at line 198 — 1 case.
- `test_go_function_literal_call_is_not_assigned_to_outer_function` at line 209 — 1 case.
- `test_supported_languages_emit_identity_and_call_metadata` at line 233 — 5 cases.

### `backend/tests/test_gds_ops.py` — 6 cases

- `test_run_leiden_clustering_projects_writes_and_drops_graph` at line 40 — 1 case.
- `test_projection_uses_modern_undirected_cypher_aggregation` at line 72 — 1 case.
- `test_run_leiden_clustering_drops_graph_when_algorithm_fails` at line 80 — 1 case.
- `test_run_leiden_clustering_drops_graph_when_projection_consume_fails` at line 98 — 1 case.
- `test_run_leiden_clustering_skips_empty_repository` at line 129 — 1 case.
- `test_run_leiden_clustering_rejects_blank_repository` at line 144 — 1 case.

### `backend/tests/test_graph_scoping.py` — 10 cases

- `test_graph_read_starts_from_repository_scoped_files` at line 46 — 1 case.
- `test_function_write_includes_raw_code` at line 55 — 1 case.
- `test_node_code_read_uses_graph_id_and_repository_scope` at line 59 — 1 case.
- `test_chunk_data_uses_bounded_slices` at line 65 — 1 case.
- `test_three_pass_write_receives_repository_scope` at line 72 — 1 case.
- `test_large_repository_uses_one_transaction_per_micro_batch` at line 151 — 1 case.
- `test_external_postprocessing_remains_repository_scoped` at line 207 — 1 case.
- `test_repository_replacement_includes_community_nodes` at line 213 — 1 case.
- `test_full_ingestion_stores_repository_token_baseline` at line 218 — 1 case.
- `test_repository_token_baseline_read_is_scoped` at line 271 — 1 case.

### `backend/tests/test_graph_serialization.py` — 3 cases

- `test_function_serialization_exposes_leiden_community_alias` at line 11 — 1 case.
- `test_function_serialization_exposes_stored_community_metadata` at line 33 — 1 case.
- `test_function_serialization_omits_source_and_embedding_from_graph_payload` at line 53 — 1 case.

### `backend/tests/test_ingest_repo.py` — 5 cases

- `test_parse_github_repository_url` at line 25 — 1 case.
- `test_repository_discovery_includes_every_supported_language` at line 31 — 1 case.
- `test_ingest_repository_uses_relative_paths_and_always_cleans_up` at line 51 — 1 case.
- `test_ingest_repository_rejects_non_github_url` at line 151 — 1 case.
- `test_downloaded_repository_lives_until_explicit_cleanup` at line 160 — 1 case.

### `backend/tests/test_parser_service.py` — 14 cases

- `test_supported_extension_mapping_covers_all_requested_languages` at line 25 — 1 case.
- `test_code_parser_normalizes_supported_languages` at line 108 — 7 cases.
- `test_code_parser_extracts_exact_function_source` at line 132 — 1 case.
- `test_parse_changed_files_skips_one_parser_failure` at line 155 — 2 cases.
- `test_failed_parse_still_contributes_to_repository_token_baseline` at line 189 — 1 case.
- `test_parse_changed_files_skips_unreadable_file` at line 227 — 1 case.
- `test_parse_progress_advances_for_every_file` at line 243 — 1 case.

### `backend/tests/test_pipeline.py` — 11 cases

- `test_neo4j_ast_write` at line 105 — 1 case.
- `test_api_graph_endpoint` at line 152 — 1 case.
- `test_delete_repository_graph_removes_only_scoped_nodes` at line 188 — 1 case.
- `test_api_graph_is_blank_without_repository_scope` at line 212 — 1 case.
- `test_api_graph_passes_normalized_repository_scope` at line 224 — 1 case.
- `test_api_node_code_is_repository_scoped` at line 240 — 1 case.
- `test_api_node_code_returns_404_for_unknown_function` at line 260 — 1 case.
- `test_api_node_code_requires_repository_scope` at line 274 — 1 case.
- `test_api_chat_endpoint` at line 283 — 1 case.
- `test_api_chat_rejects_unscoped_frontend_payload` at line 321 — 1 case.
- `test_blast_radius_does_not_cross_repository_boundaries` at line 336 — 1 case.

### `backend/tests/test_repository_deletion.py` — 7 cases

- `test_delete_repository_graph_uses_scoped_detach_delete` at line 17 — 1 case.
- `test_delete_all_repository_graphs_removes_only_scoped_nodes` at line 44 — 1 case.
- `test_lifespan_cleans_stale_graphs_on_startup` at line 69 — 1 case.
- `test_delete_repository_endpoint_normalizes_and_deletes_scope` at line 92 — 1 case.
- `test_delete_repository_endpoint_rejects_invalid_scope` at line 107 — 1 case.
- `test_browser_cleanup_endpoint_accepts_json_scope` at line 118 — 1 case.
- `test_browser_cleanup_endpoint_rejects_invalid_scope` at line 135 — 1 case.

### `backend/tests/test_tokens.py` — 3 cases

- `test_count_tokens_uses_requested_model_encoding` at line 10 — 1 case.
- `test_count_tokens_falls_back_for_unknown_model` at line 27 — 1 case.
- `test_count_tokens_validates_inputs` at line 50 — 1 case.

**Total: 96 active backend cases.**

## Git chronology

Commit subjects are historical records; they do not establish personal motives, benchmark results or manual authorship.

```text
79fa768 2026-09-23 feat: implemented parser and function-identity foundation needed for the next phase of our assistant-to-graph integration.
17d36c0 2026-09-16 feat: automated Postman API workflows chaining repository ingestion, graph retrieval, source lookup, Graph-RAG queries, and cleanup using dynamic variables, NDJSON assertions, negative tests, and HMAC-SHA256 signed webhook validation.
9546f58 2026-09-16 Made the Local API Test Environment Reproducible
abd6f25 2026-08-31 Overhauled readme
a529636 2026-08-26 Added fullscreen button for viewing graph
8d1c3a4 2026-08-23 Implemented up to date Neo4j search, removed deprecated db.index.vector.queryNodes
47f0049 2026-08-23 Implemented token efficiency tracking end to end. -
3a1b28f 2026-08-22 Overhauled filter system
6822eef 2026-08-22 Graph filters UI rehaul
4a173a3 2026-08-22 Patched issues with Java repo ingestion
c011222 2026-08-21 Cluster filtering UI
3c963ac 2026-08-21 Implemented descriptions of clusters
05f89ad 2026-08-21 Patched issues with architecture labeling using Leiden community detection
6319d2d 2026-08-21 Container patch
77d357d 2026-08-21 Patched issue with Neo4j plugins
078c163 2026-08-21 Leiden community detection integration and visualization
d3ec9ab 2026-08-20 Implemented semantic search using vector embeddings
2c8d2bf 2026-08-20 Implemented database cleanup upon application exit
e2cda94 2026-08-19 Implemented multi language tree sitter parsing
d0e5f5f 2026-08-19 Improved agent readability
e014d9e 2026-08-18 Optimization of repo ingestion
4ff44cd 2026-08-18 Added progress bar for ingestion
15b8962 2026-08-18 Patched issue with dynamic ingestion pipline
6f49012 2026-08-18 Tools and agent now track external functions
930d2a3 2026-08-18 New tools for agent added
1397f03 2026-08-18 Patched issue with graph sync disconnected with repo ingestion
0d1692c 2026-08-18 Transition to ingesting GitHub repos
a8ccd49 2026-08-17 Minor adjustment to graph UI
ec8dee2 2026-08-17 Updated graph UI
febafa8 2026-08-17 Patched issues with Neo4j syncing and agent communication
ad3ec25 2026-08-17 Patched issues with Neo4j Python connection
d03c176 2026-08-17 Backend/Webook connection
6918655 2026-08-16 Initial Commit
```

## Benchmark search and documentary discrepancies

- Current source/docs and available historical changes were searched for 737,000/737000, 18,000/18000 and 97.5. No reproducible benchmark artifact supporting the supplied numeric claim was found.
- `47f0049` introduces token accounting. A calculation mechanism is not evidence of a particular run.
- README documents 77 tests at 2026-09-16. The new identity module adds 19 cases, yielding 96 now. The supplied 82-case claim does not match HEAD.
- CG-001 describes a pre-upgrade parser; HEAD adds lexical fields but retains the warned-about persistence gap.
- Root prototype SSE chat, one-tool agent and PR files API are not active backend features.
- There are no stored query plans, answer-quality datasets, latency distributions, provider-spend logs or Leiden-versus-baseline ablations in the tracked application artifacts.

## External primary references consulted

External references clarify algorithm/library concepts only; current application behavior was established from source. Version-dependent live behavior remains unverified.

- [Tree-sitter basic parsing](https://tree-sitter.github.io/tree-sitter/using-parsers/2-basic-parsing.html) — concrete tree and syntax spans.
- [Tree-sitter query syntax](https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html) — capture pattern concepts.
- [Neo4j Leiden](https://neo4j.com/docs/graph-data-science/current/algorithms/leiden/) — current documented objective/configuration defaults.
- [Original Leiden paper](https://arxiv.org/abs/1810.08473) — refinement/connectivity theory, not a CodeGraph result.
- [Neo4j vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/) — vector index/version semantics.
- [Cypher SEARCH](https://neo4j.com/docs/cypher-manual/25/clauses/search/) — in-index versus post-filtering; SEARCH is Cypher 25-only, introduced in Neo4j 2026.01. Current query has no explicit `CYPHER 25` prefix, so database default language compatibility must be checked in deployment.

---

[Back to contents](#contents) · [Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](05_MOCK_INTERVIEWS.md) · [Next](07_FINAL_REVIEW.md)
