# Repository-scoped backend

Run this backend from the `backend` directory so Python resolves the intended
`app` package:

```bash
uvicorn app.main:app --reload
```

## Ingest or re-ingest a repository

Repository nodes are scoped by the canonical `owner/repository` value returned
by the ingestion endpoint. After a complete parse succeeds, calling the
endpoint replaces only that repository's scoped `File` and `Function` nodes in
one Neo4j transaction. This removes files/functions deleted upstream without
touching other repositories. Webhook writes remain incremental.

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
