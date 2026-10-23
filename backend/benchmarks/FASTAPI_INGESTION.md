# FastAPI ingestion verification

Measured on 2026-10-16 against `tiangolo/fastapi`, redirected by GitHub to
`fastapi/fastapi`, archive `fastapi-fastapi-bb7f314`. Each run downloaded and parsed
all 1,172 supported files and persisted all 5,322 function definitions. Tests and
documentation examples were included by the normal source discovery rules.

All runs used live GitHub and OpenAI requests and an isolated Neo4j 2026.07.1
container with Graph Data Science. No embeddings, database writes, clustering, or
community labels were mocked. Timing starts at repository download and ends after
the ingestion stream finishes and temporary source files are cleaned up. Database
startup/schema initialization and post-ingestion integrity checks are outside that
interval, as they are outside normal repository ingestion in a running backend.

| Run | Full ingestion | Embedding inputs sent | Embedding API requests | Community label API requests |
| --- | ---: | ---: | ---: | ---: |
| Before this embedding fix | 122.993 s | 5,322 | 54 | 107 |
| After, empty embedding cache | 28.844 s | 5,319 | 11 | 14 |
| After, full re-ingestion in a new process | 30.907 s | 0 | 0 | 14 |

Raw reports: [before](results/fastapi-before.json),
[after with empty cache](results/fastapi-after-cold.json),
[after with populated cache](results/fastapi-after-warm.json).

The before run already included the earlier parser/index/singleton-label
optimizations. Its embedding/write phase took 41.584 seconds and its community
labeling phase took 71.981 seconds. The empty-cache after run took 9.173 seconds
for embeddings/writes and 14.073 seconds for labeling. External API latency varies;
these are observed complete runs, not guarantees for every machine or connection.

## What changed

The legacy per-file/simple-name embedding count on this snapshot was 5,012.
Persisting every distinct definition increased that to 5,322 (6.2%). Only three of
the new inputs are identical: 5,319 unique text inputs remain necessary under the
current qualified-name/file-path embedding contract. The fix keeps every distinct
function and reuses exact vectors, rather than dropping definitions or source files.

- Group definitions by exact embedding text and expand each vector back to all
  corresponding entities. This also deduplicates repeated inputs across request
  boundaries.
- Persist reusable vectors in a SQLite cache keyed by model, dimension, and text.
  Re-ingestion and backend restarts reuse them; failures do not stop ingestion.
- Use 512 unique inputs per embedding request and at most four requests at once,
  while preserving independent bounded Neo4j write batches.
- Batch eight multi-function community labels per request, up to four requests
  concurrently. The structured schema requires a field for each community, so
  results cannot be assigned by an unreliable list position or repeated ID.

## Verification

The final populated-cache run enforced `--require-under 60` and verified:

- 5,322 persisted Functions, 5,322 distinct entity IDs, and 5,322 embeddings.
- Every vector has 1,536 dimensions.
- Exactly 5,322 `DEFINES` links, with no missing or mismatched defining file paths.
- Every Function has a persisted community relationship and the graph is `ready`.
- Source lookup by active graph node ID returns the correct code and file path.

`python -m pytest -q -rs`: **129 passed**, no skipped tests. The disposable Neo4j
tests executed, including index-plan, identity, call, refresh, serialization, and
source-code checks. One pre-existing dependency deprecation warning remains.

## Reproduce

Use a disposable Neo4j instance with GDS; the command replaces the requested
repository's graph. Set `NEO4J_PASSWORD` for that instance and `OPENAI_API_KEY` in
the environment or backend configuration. From `backend/`:

```bash
python -u benchmarks/ingestion.py \
  --repo tiangolo/fastapi \
  --neo4j-uri bolt://127.0.0.1:17687 \
  --cache-path /tmp/fastapi-embedding-cache.sqlite3 \
  --output benchmarks/results/fastapi-run.json \
  --require-under 60
```

Use a new cache path for a cold run; run the same command in a new process for a
warm run. The harness makes real API requests, writes stage timings and integrity
results to JSON, and exits unsuccessfully on an ingestion failure, graph-integrity
failure, or elapsed time at or above the requested threshold. Logs are stored
beside the JSON report and ignored by Git.
