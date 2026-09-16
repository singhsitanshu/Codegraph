# CodeGraph API in Postman

This directory contains one Postman Collection v2.1 JSON file for the **active** `backend/app` FastAPI service and a secret-free local environment example. The `01 - Repository Workflow` folder is an automated API lifecycle check, not a replacement for backend pytest or frontend Node tests. The root-level prototype API is intentionally excluded.

## Start the application

Follow the [project quick start](../README.md#quick-start): start Docker/Neo4j with GDS, install the packages from `backend/requirements.txt`, configure `backend/.env`, and start FastAPI **from `backend/`** with `uvicorn app.main:app --reload`. `GET http://localhost:8000/health` should return `{"status":"ok"}`. The React frontend is optional when exercising the API through Postman.

## Import and select

1. In Postman, import `collections/codegraph-api.postman_collection.json`.
2. Import `environments/codegraph-local.example.postman_environment.json`.
3. Select **CodeGraph Local (example)** as the active environment.
4. Review `repository_url`. The example points to [`pallets/itsdangerous`](https://github.com/pallets/itsdangerous), a small public Python repository with several functions; Python is a supported parser language. You may substitute another small public or backend-token-accessible HTTPS GitHub repository. Keep `base_url` at `http://localhost:8000` for the default local API.
5. In Collection Runner, select only **01 - Repository Workflow**, keep the request order, set **one iteration**, and run serially. Do not run simultaneous instances against the same repository scope.

The workflow automatically chains seven requests:

1. Health confirms process liveness and clears dynamic values from an interrupted prior run.
2. Ingestion parses each NDJSON line, rejects error records even when HTTP is `200`, and captures the API-returned canonical `repo_name` and token baseline.
3. Graph checks for nodes, excludes bulk source and embedding vectors, then captures an internal Function's ID and name.
4. Source fetches that Function's code through the repository-scoped endpoint.
5. Chat checks that its answer is nonempty and token metrics are internally consistent; it never compares model-generated wording.
6. Path-based delete permanently removes the selected repository graph.
7. Cleanup reads the graph again, requires empty `nodes` and `edges`, then clears the captured values.

The workflow mutates Neo4j and makes GitHub, OpenAI, and Anthropic calls. Use a local instance with valid backend configuration and expect provider usage/cost. A failed ingestion can leave a partially rebuilt scope. Collection Runner may continue to later requests after an assertion fails, so inspect the run report; if cleanup did not succeed, remove the scope manually. Run the folder, not the entire collection. `00 - Health` is a standalone liveness request. The path-based delete in the workflow is the preferred normal cleanup mechanism.

## Focused failure cases

`02 - Validation and Failure Cases` covers insecure and non-GitHub ingestion URLs, a malformed repository scope, a missing chat scope, unknown function source (`404`), streamed ingestion failure, and repeated deletion. The invalid URLs and malformed chat/graph requests fail before external services. The nonexistent-repository ingestion case does contact GitHub; its expected `200` NDJSON stream must contain an `error` record and no successful `progress: 100` record. This is an intentional demonstration that HTTP success does not imply ingestion success.

The two delete requests must run consecutively. The first generates a unique synthetic `postman-validation/delete-…` scope and the second deletes that same scope again, asserting the API's existing `200` success response both times. They require Neo4j but do not use `active_repo_name`; the temporary variable is cleared after the second success. You can run the first eight requests in this folder in order, or send individual cases. Exclude **Browser-lifecycle cleanup (compatibility; manual only)** from a folder run: it is a separate destructive frontend-compatibility request that uses `active_repo_name`.

## GitHub webhook HMAC checks

In your selected **private** local Postman environment, set `webhook_secret` to the same value as `GITHUB_WEBHOOK_SECRET` in `backend/.env`. The committed example leaves it empty; never commit or share a populated environment export. Run the six requests in `03 - GitHub Webhook` individually or in order. Use a Postman runtime with [Web Crypto support](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-require).

The folder's pre-request script writes each case's literal payload to `webhook_raw_body`, resolves the exact raw request body that Postman will transmit, signs its UTF-8 bytes with HMAC-SHA256, and sets `webhook_signature` to `sha256=<lowercase hex digest>`. The valid case sends a JSON object with `X-GitHub-Event: ping`; it has no repository or commit data and exercises authentication without a meaningful graph update. The negative cases omit the signature header, alter a valid digest, sign body A while transmitting different body B, or correctly sign malformed/non-object JSON. Do not prettify, re-serialize, or otherwise change a signed raw body after signing: any byte change invalidates its HMAC.

`202 Accepted` confirms that the webhook passed request validation and was scheduled for in-process background processing. It does **not** prove that background graph processing completed successfully. The API exposes no durable webhook job ID or completion endpoint, so this collection has no sleep or polling step.

## Configuration and secret boundary

Postman sends requests only to CodeGraph's public HTTP API. OpenAI and Anthropic keys, Neo4j credentials, and any GitHub access token stay in the ignored `backend/.env` file; they are not collection or Postman environment variables. The webhook-signing test is the sole exception: it needs a **private local copy** of `GITHUB_WEBHOOK_SECRET` in Postman's `webhook_secret` environment variable. The committed example environment contains no secrets.

The collection uses the Postman [Collection v2.1 format](https://schema.getpostman.com/json/collection/v2.1.0/collection.json), which Postman can [import as native data](https://learning.postman.com/docs/getting-started/importing-and-exporting/importing-data). No Postman CLI, monitor, or mock server is required for this ticket.
