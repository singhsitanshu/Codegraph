# GitHub Webhook Listener

FastAPI endpoint that verifies GitHub webhook signatures and logs filenames changed
by `push` and `pull_request` events. It does not read or parse file contents.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set the same secret configured in the GitHub webhook.
uvicorn app.main:app --reload
```

Configure GitHub to deliver `push` and `pull_request` events to:

```text
https://your-host.example/webhook/github
```

Use `application/json` as the content type. Pull request webhook payloads do not
contain filenames, so the endpoint calls GitHub's pull-request files API. Set
`GITHUB_TOKEN` for private repositories and to avoid low unauthenticated rate limits.

## Test

```bash
pytest
```

## Build a Python call graph

Set the `NEO4J_*` values in `.env`, then analyze a Python file and write its
functions and calls to Neo4j:

```bash
python parse_python.py path/to/file.py
```

To inspect the extracted graph without connecting to Neo4j:

```bash
python parse_python.py path/to/file.py --dry-run
```

The parameterized Cypher statement is exposed as `UPSERT_CALL_GRAPH` in
`database.py`. Calls made at file scope originate from a synthetic `<module>`
function. Calls that cannot be resolved to a definition in the analyzed file are
stored as external `Function` nodes.

## Ask the LangGraph agent

Set `ANTHROPIC_API_KEY` and the `NEO4J_*` values in `.env`, then run:

```bash
python agent.py "Which functions call verify_signature?"
```

The graph stores an append-only list of messages in `AgentState`. Claude decides
whether to call `get_function_callers`, LangGraph executes the Neo4j-backed tool,
and control loops back to Claude until it returns a response without tool calls.

The same orchestration can be called from Python:

```python
from agent import run_agent

answer = run_agent("What calls pull_request_files?")
print(answer)
```

## Run the dashboard

The React dashboard lives in `frontend/` and expects these backend routes:

- `GET http://localhost:8000/api/graph` returning `{ "nodes": [], "edges": [] }`
- `POST http://localhost:8000/api/chat` accepting `{ "message": "..." }` and
  returning `text/event-stream` events

Start it with:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`. The FastAPI server must allow that
origin through CORS when the two development servers are run separately.
