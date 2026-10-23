# Function identity parser contract (CG-002)

This is the parser contract for function identity. Since CG-002B the Neo4j writer persists these IDs and merges `Function` nodes by `entity_id`; see [Graph persistence (CG-002B)](#graph-persistence-cg-002b).

## Parsed output

`CodeParser.parse_file(path, source, repository="owner/repo")` preserves the file-level `file_path`, `defined_classes`, `defined_functions`, and `outgoing_calls` fields. Each `functions[]` item preserves `name` and `raw_code` and adds:

```json
{
  "name": "validate",
  "repository": "example/backend",
  "qualified_name": "PaymentService.validate",
  "file_path": "src/payments.py",
  "language": "python",
  "signature": "(self, value)",
  "definition_discriminator": "signature:(self, value);occurrence:1",
  "entity_id": "fn:v1:<64 lowercase SHA-256 hex characters>",
  "has_body": true,
  "start_line": 42,
  "end_line": 58,
  "start_column": 4,
  "end_column": 21,
  "raw_code": "def validate(self, value): ...",
  "calls": [
    {
      "name": "check",
      "syntax": "self.check",
      "start_line": 45,
      "end_line": 45,
      "start_column": 8,
      "end_column": 25,
      "resolution": "unresolved"
    }
  ]
}
```

Lines are one-based and inclusive; columns are zero-based Tree-sitter byte columns. `signature` is the whitespace-normalized parameter syntax when exposed by the grammar. `has_body=false` identifies a declaration-only TypeScript overload signature; its `raw_code` is that declaration. Such signatures appear in `functions`, but remain excluded from legacy `defined_functions` and from Neo4j, which stores executable bodies only. `unattributed_calls` on the file has the same call-site shape for calls outside a captured function body or inside an anonymous boundary that cannot be assigned confidently. The legacy `outgoing_calls` remains a file-wide list of simple call names.

The repository is required to generate `entity_id`. When supplied, it is also stored on the parsed file and each function. For backward compatibility, `parse_file` without `repository` still returns the additional lexical metadata but omits `entity_id`; callers with temporary absolute paths can later call `attach_function_entity_ids(parsed_file, repository=..., file_path=<relative path>)`. Full GitHub ingest uses this after path relativization; the webhook pipeline attaches IDs using its repository-relative event path; the local helpers (`ingest_local_repo.py`, `seeding.py`) attach them after relativizing their absolute paths.

## Canonical key

`generate_function_entity_id` in `app/utils/entity_identity.py` computes `fn:v1:` plus SHA-256 over a compact UTF-8 JSON array of:

1. Trimmed repository string, preserving case.
2. Repository-relative POSIX file path; backslashes and dot segments are normalized, and absolute/escaping paths are rejected.
3. Lowercase language key (`python`, `javascript`, `typescript`, `tsx`, `go`, `java`).
4. Lexically qualified name, preserving case.
5. Definition discriminator: `signature:<normalized parameters>;occurrence:<source-order count among the same qualified name and signature>`. When the grammar has no parameter node, the signature part is `unknown` and occurrence supplies the fallback.

The key does not use source code body text, Python `hash()`, Neo4j `elementId`, or React Flow IDs. Unchanged source and canonical path produce the same ID on repeated parses. A path, scope, signature, or occurrence-order change can change an ID. A body-only edit leaves the ID unchanged. Reordering identical signatures can change which physical definition owns occurrence 1 or 2; there is no stable semantic distinction in the current syntax data for those repetitions.

## Language rules

| Language | Captured definitions and qualified name | Discriminator |
| --- | --- | --- |
| Python | Existing `function_definition`, including top-level, class methods, and nested functions. Names are joined from enclosing named classes/functions, e.g. `PaymentService.validate` or `outer.inner`. | Parameter syntax plus occurrence. Decorators and runtime rebinding do not prove symbol identity. |
| JavaScript/JSX | Existing named declarations, generators, class/object `method_definition`, and `variable_declarator` with arrow/function expression. Named lexical ancestors are joined. Anonymous expressions without a captured declarator remain unmodeled. | Parameter syntax plus occurrence. |
| TypeScript/TSX | JavaScript forms plus `function_signature` and `method_signature` for overload and interface declarations. Class and interface scopes are included. Declarations and implementations each get an ID; declarations have no body. | Typed parameter syntax plus occurrence. Return type is not part of the key; identical parameter syntax uses occurrence. |
| Go | Existing functions and methods; method receiver type is prepended, e.g. `Client.Send`. | Parameter syntax plus occurrence. Pointer/value receiver spelling is not separately encoded when the receiver type name is the same. |
| Java | Existing methods with bodies and constructors; enclosing classes are prepended, e.g. `Client.send`, `Client.Client`. | Parameter syntax plus occurrence, distinguishing ordinary overloads. Abstract declarations without bodies remain outside the current capture query. |

## Calls and uncertainty

Calls are attributed to the innermost captured definition **only when the call expression is inside its Tree-sitter body**. Syntax such as `self.check`, `api.call`, and receiver-qualified method calls is retained as evidence, while `resolution` remains `unresolved`. A call inside a nested captured function belongs to that nested function. A call in a default argument, at file scope, or inside an uncaptured anonymous function/lambda is put in `unattributed_calls`. This does not resolve dynamic dispatch, imports, overload targets, cross-file calls, or the true callee node.

## Graph persistence (CG-002B)

`app/db/graph_ops.py` writes the parsed functions to Neo4j:

| Entity | Identity | Notes |
| --- | --- | --- |
| `Function` | `entity_id` (unique constraint `function_entity_id`), always written with `repo_name` | Stores `name` for display plus `qualified_name`, `file_path`/`file`, `language`, `signature`, `definition_discriminator`, source range, `raw_code`, `embedding`, and `ambiguous_calls`. `File-[:DEFINES]->Function`. |
| `ExternalFunction` | `(repo_name, name)` | A callee name with no matching definition in the repository. It carries `external`/`is_external = true` and **no** `Function` label, so it never merges with a definition or joins GDS clustering. |
| `CALLS` | one edge per (caller, target) | `resolution`, `call_count`, `source_file`. |

- **IDs.** The writer recomputes each ID with `generate_function_entity_id`. A supplied `entity_id` that was generated for a different repository or path is rejected. A missing ID is generated, and a function without identity metadata is skipped with a warning. Parsed paths must be repository-relative. Declaration-only TypeScript overloads (`has_body=false`) are not persisted.
- **Calls.** Only the call sites in each function's `functions[].calls` are used. The file-wide `outgoing_calls` is no longer copied onto every function, and `unattributed_calls` are not persisted. Each callee name is resolved to exactly one definition, trying in order:
  1. the nearest enclosing lexical scope in the caller's file (`lexical_scope`);
  2. a unique same-file name (`same_file`);
  3. a unique repository-wide name (`repository_unique`).

  A name that matches several definitions at the first step that finds any matches gets no edge; it is listed in the caller's `ambiguous_calls`. A name with no match becomes an `ExternalFunction` call. This resolution is name-based inference, not binding analysis.
- **Full ingest** (`replace_existing=True`) deletes the repository's nodes and rebuilds them. This is also the migration path for graphs written by the old name-keyed writer. Do not backfill `entity_id` onto legacy nodes.
- **Incremental ingest** (the webhook) treats parsed files and `deleted_file_paths` as a change set:
  - It reads the other files' definitions so call resolution sees the whole repository.
  - It deletes Functions in the affected files whose IDs disappeared, including legacy nodes without an `entity_id`, and deletes removed File nodes.
  - It rebuilds outgoing `CALLS` from the changed files and drops orphaned `ExternalFunction` nodes.
  - Surviving IDs keep their incoming edges, for example after a body-only edit.
  - Limitation: calls in unchanged files are not re-resolved. A newly added definition does not take over an existing external or ambiguous call until the next full ingest.
- **Clustering.** Leiden (`app/db/gds_ops.py`) works on more than the resolved Function-to-Function calls. Those alone leave most functions isolated, which gives each its own community. The projection adds two kinds of undirected links: `File-[:DEFINES]->Function`, and calls to `ExternalFunction` nodes. The final community ID is written to `Function` nodes only. Each run logs function, projection and community counts plus the singleton ratio, and warns when the ratio is above 25%. Communities with fewer than 3 functions get no LLM label; they are pooled into one `Ungrouped` community (`community_id = -1`).
- **Reads.** The graph API still uses Neo4j `elementId` for React Flow node IDs and source lookup; `data.entity_id` carries the application identity. Agent tools match by simple or qualified name and report each matching definition separately.
- **Open.** Durable references should also carry a graph revision so that deleted or re-ingested definitions can be detected. The parser ID alone cannot prove a function still exists in Neo4j.
