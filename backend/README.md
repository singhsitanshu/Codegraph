# Repository-scoped backend

Run this backend from the `backend` directory so Python resolves the intended
`app` package:

```bash
uvicorn app.main:app --reload
```

## Ingest or re-ingest a repository

Repository nodes are scoped by the canonical `owner/repository` value returned
by the ingestion endpoint. After a complete parse succeeds, calling the
endpoint replaces that repository's scoped graph through multiple bounded
Neo4j transactions. This removes files/functions deleted upstream without
touching other repositories, but a failure partway through can leave a partial
replacement. Webhook writes remain incremental.

```bash
curl -X POST http://localhost:8000/api/ingest-repo \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://github.com/psf/requests"}'
```

The downloader reads the repository's current `default_branch` from GitHub,
so the endpoint works with `main`, `master`, or another configured branch.
Set `GITHUB_TOKEN` in `.env` for private repositories and higher API limits.
Set `OPENAI_API_KEY` as well; ingestion batches function metadata through
`text-embedding-3-small` and stores the resulting vectors for semantic search.
Repositories ingested before this feature must be re-ingested to populate their
function embeddings.

The Neo4j server must also have a compatible Graph Data Science plugin
installed. After dependencies are written, ingestion projects only the active
repository's function-call graph, runs Leiden community detection, writes each
function's `leiden_community`, and drops the temporary in-memory graph.
The included development `docker-compose.yml` installs and allows the GDS
procedures. Recreate the Neo4j service once after pulling this change:

```bash
docker compose up -d --force-recreate neo4j
```

## Ingestion performance

Call attribution walks the syntax tree's enclosing bodies, and target resolution
builds one repository lookup index before processing call sites. Unresolved calls
use separate indexed Function and File lookups in Neo4j. These paths preserve the
identity and ambiguity rules without repeatedly scanning every definition or node.

Embedding inputs are deduplicated across all definitions in an ingestion. Requests
contain up to 512 unique inputs with at most four requests in flight; Neo4j writes
remain bounded independently. Separate function entities can reuse an identical
vector without sharing an identity. A local SQLite cache keyed by embedding model,
dimensions, and exact normalized input persists across full graph rebuilds and
backend restarts. It defaults to `backend/.cache/embeddings.sqlite3`; override
`EMBEDDING_CACHE_PATH` with a writable path, or set it to an empty string to disable
the cache. A changed input/model/dimension triggers fresh embedding generation.
Cache failures are logged and fall back to normal generation. Cache files can be
removed to reclaim disk space; this only makes the next ingest regenerate vectors.

Single-function communities receive labels from their qualified function name and
file path without an AI request. Other communities are labeled eight per request,
with at most four concurrent requests. Required structured response keys bind each
label to its community. All labels are stored together after successful generation.

The ingestion stream reports completed function and dependency counts. Backend
logs also report time spent preparing records, embedding/writing functions,
writing dependencies, clustering, and labeling. These timings help distinguish
local work from Neo4j and external API latency when investigating a slow ingest.

The measured `tiangolo/fastapi` ingestion fell from 123.0 seconds to 28.8 seconds
with an empty cache. Full re-ingestion in a new process took 30.9 seconds and made
no embedding requests. See [the benchmark report](benchmarks/FASTAPI_INGESTION.md)
for raw measurements, graph verification, and the reproduction command.

## Graph-RAG token efficiency

Full repository ingestion counts every supported source file with the
`gpt-4o` tiktoken encoding and stores the baseline on the repository's scoped
`Repository` node. Chat requests count the Neo4j tool outputs actually added
to the LangGraph trace and return the comparison alongside the answer:

```json
{
  "response": "...",
  "metrics": {
    "full_repo_tokens": 150000,
    "context_tokens": 4200,
    "tokens_saved": 145800,
    "efficiency_percentage": 97.2
  }
}
```

Re-ingest repositories created before this feature to populate their token
baseline. Until then, their full-repository metric is reported as zero.

## Legacy unscoped Neo4j data

Nodes created before repository scoping cannot be assigned safely because they
do not retain enough ownership metadata. Re-ingest each repository with the
endpoint above; this creates fully scoped replacement nodes without exposing
legacy nodes to repository-scoped agent queries.

After verifying every required repository has been re-ingested, legacy nodes
can be removed in Neo4j Browser:

```cypher
MATCH (node)
WHERE (node:File OR node:Function) AND node.repo_name IS NULL
DETACH DELETE node
```

This deletion is intentionally manual because automatically guessing ownership
for existing nodes could mix tenant data.
