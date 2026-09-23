# Function identity parser contract (CG-002)

This contract prepares CG-002B. The Neo4j writer, graph API, and agent still use simple function names; **these parser IDs are not persisted or available to graph navigation yet**.

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

Lines are one-based and inclusive; columns are zero-based Tree-sitter byte columns. `signature` is the whitespace-normalized parameter syntax when exposed by the grammar. `has_body=false` identifies a declaration-only TypeScript overload signature; its `raw_code` is that declaration. Such signatures appear in `functions`, but remain excluded from legacy `defined_functions` and Neo4j ingestion to preserve the current graph's body choice. `unattributed_calls` on the file has the same call-site shape for calls outside a captured function body or inside an anonymous boundary that cannot be assigned confidently. The legacy `outgoing_calls` remains a file-wide list of simple call names.

The repository is required to generate `entity_id`. When supplied, it is also stored on the parsed file and each function. For backward compatibility, `parse_file` without `repository` still returns the additional lexical metadata but omits `entity_id`; callers with temporary absolute paths can later call `attach_function_entity_ids(parsed_file, repository=..., file_path=<relative path>)`. Full GitHub ingest uses this after path relativization; the webhook pipeline attaches IDs using its repository-relative event path. Neither path causes those IDs to be written to Neo4j yet.

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

## CG-002B handoff

- Change Function MERGE and lookup from `(repo_name, name)` to the persisted canonical `entity_id`, with a uniqueness constraint and a migration/rebuild plan. Preserve `name` for display and `qualified_name`, path, language, discriminator, and source range for inspection.
- Update `DEFINES` and `CALLS` construction to use caller IDs and resolved target IDs. The new `functions[].calls` are lexical call-site evidence; they do **not** identify a callee. Keep an unresolved-call representation until resolution is proven. Stop copying each file-wide `outgoing_calls` name onto every function.
- Decide how declaration-only TypeScript overload signatures map to graph entities and implementation bodies. The current compatibility path deliberately skips them in Neo4j.
- Update both full and incremental ingest, agent queries, source lookup, graph serialization, indexes, and tests together. Avoid exposing `entity_id` as a durable graph reference until these writes and reads use it consistently.
- Update local ingestion helpers (`backend/ingest_local_repo.py`, `backend/seeding.py`) to attach IDs after relativizing their absolute paths before CG-002B starts persisting `entity_id`.
- Any persistent reference should include repository and a graph snapshot/revision so deleted or re-ingested definitions can be detected. The parser ID alone cannot establish that a function currently exists in Neo4j.
