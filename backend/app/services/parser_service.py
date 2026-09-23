import asyncio
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from app.utils.entity_identity import (
    generate_function_entity_id,
    normalize_repository_path,
)
from app.utils.tokens import count_tokens


logger = logging.getLogger(__name__)
MAX_CONCURRENT_FILE_READS = 32
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
}


PYTHON_FUNCTION_DEFINITIONS_QUERY = """
(function_definition
  name: (identifier) @name) @definition
"""

PYTHON_FUNCTION_CALLS_QUERY = """
(call
  function: (identifier) @call)

(call
  function: (attribute
    attribute: (identifier) @call))
"""

PYTHON_CLASS_DEFINITIONS_QUERY = """
(class_definition
  name: (identifier) @name)
"""

JAVASCRIPT_FUNCTION_DEFINITIONS_QUERY = """
(function_declaration
  name: (identifier) @name) @definition

(generator_function_declaration
  name: (identifier) @name) @definition

(method_definition
  name: (property_identifier) @name) @definition

(variable_declarator
  name: (identifier) @name
  value: [(arrow_function) (function_expression)]) @definition
"""

JAVASCRIPT_FUNCTION_CALLS_QUERY = """
(call_expression
  function: (identifier) @call)

(call_expression
  function: (member_expression
    property: (property_identifier) @call))
"""

JAVASCRIPT_CLASS_DEFINITIONS_QUERY = """
(class_declaration
  name: (identifier) @name)
"""

TYPESCRIPT_FUNCTION_DEFINITIONS_QUERY = """
(function_signature
  name: (identifier) @name) @definition

(function_declaration
  name: (identifier) @name) @definition

(generator_function_declaration
  name: (identifier) @name) @definition

(method_definition
  name: (property_identifier) @name) @definition

(method_signature
  name: (property_identifier) @name) @definition

(variable_declarator
  name: (identifier) @name
  value: [(arrow_function) (function_expression)]) @definition
"""

TYPESCRIPT_FUNCTION_CALLS_QUERY = """
(call_expression
  function: (identifier) @call)

(call_expression
  function: (member_expression
    property: (property_identifier) @call))
"""

TYPESCRIPT_CLASS_DEFINITIONS_QUERY = """
(class_declaration
  name: (type_identifier) @name)

(abstract_class_declaration
  name: (type_identifier) @name)
"""

GO_FUNCTION_DEFINITIONS_QUERY = """
(function_declaration
  name: (identifier) @name) @definition

(method_declaration
  name: (field_identifier) @name) @definition
"""

GO_FUNCTION_CALLS_QUERY = """
(call_expression
  function: (identifier) @call)

(call_expression
  function: (selector_expression
    field: (field_identifier) @call))
"""

GO_CLASS_DEFINITIONS_QUERY = """
(type_spec
  name: (type_identifier) @name
  type: [(struct_type) (interface_type)])
"""

JAVA_FUNCTION_DEFINITIONS_QUERY = """
(method_declaration
  name: (identifier) @name
  body: (block)) @definition

(constructor_declaration
  name: (identifier) @name
  body: (constructor_body)) @definition
"""

JAVA_FUNCTION_CALLS_QUERY = """
(method_invocation
  name: (identifier) @call)
"""

JAVA_CLASS_DEFINITIONS_QUERY = """
(class_declaration
  name: (identifier) @name)
"""


@dataclass(frozen=True, slots=True)
class _LanguageQueries:
    """Compiled queries needed to extract one language's code relationships."""

    function_definitions: Query
    function_calls: Query
    class_definitions: Query


@dataclass(frozen=True, slots=True)
class ParsedFileProgress:
    """One completed file from a concurrently parsed batch."""

    index: int
    processed: int
    total: int
    result: dict[str, Any] | None
    source_tokens: int = 0


class CodeParser:
    """Normalize Python, JavaScript, TypeScript, TSX, Go, and Java graphs.

    Grammar packages are loaded from their precompiled Python wheels. No grammar
    compilation, C toolchain, or legacy ``Language.build_library`` call is used.
    Parser instances are retained for reuse, while per-language locks prevent a
    single parser from being used concurrently by multiple background threads.
    """

    _SUPPORTED_EXTENSIONS = frozenset(SUPPORTED_EXTENSIONS)
    PYTHON_FUNCTION_DEFINITIONS_QUERY = PYTHON_FUNCTION_DEFINITIONS_QUERY
    PYTHON_FUNCTION_CALLS_QUERY = PYTHON_FUNCTION_CALLS_QUERY
    PYTHON_CLASS_DEFINITIONS_QUERY = PYTHON_CLASS_DEFINITIONS_QUERY
    JAVASCRIPT_FUNCTION_DEFINITIONS_QUERY = (
        JAVASCRIPT_FUNCTION_DEFINITIONS_QUERY
    )
    JAVASCRIPT_FUNCTION_CALLS_QUERY = JAVASCRIPT_FUNCTION_CALLS_QUERY
    JAVASCRIPT_CLASS_DEFINITIONS_QUERY = JAVASCRIPT_CLASS_DEFINITIONS_QUERY
    TYPESCRIPT_FUNCTION_DEFINITIONS_QUERY = TYPESCRIPT_FUNCTION_DEFINITIONS_QUERY
    TYPESCRIPT_FUNCTION_CALLS_QUERY = TYPESCRIPT_FUNCTION_CALLS_QUERY
    TYPESCRIPT_CLASS_DEFINITIONS_QUERY = TYPESCRIPT_CLASS_DEFINITIONS_QUERY
    GO_FUNCTION_DEFINITIONS_QUERY = GO_FUNCTION_DEFINITIONS_QUERY
    GO_FUNCTION_CALLS_QUERY = GO_FUNCTION_CALLS_QUERY
    GO_CLASS_DEFINITIONS_QUERY = GO_CLASS_DEFINITIONS_QUERY
    JAVA_FUNCTION_DEFINITIONS_QUERY = JAVA_FUNCTION_DEFINITIONS_QUERY
    JAVA_FUNCTION_CALLS_QUERY = JAVA_FUNCTION_CALLS_QUERY
    JAVA_CLASS_DEFINITIONS_QUERY = JAVA_CLASS_DEFINITIONS_QUERY

    def __init__(self) -> None:
        """Initialize parsers and compile extraction queries for all grammars."""

        python_language = Language(tree_sitter_python.language())
        javascript_language = Language(tree_sitter_javascript.language())
        typescript_language = Language(
            tree_sitter_typescript.language_typescript()
        )
        tsx_language = Language(tree_sitter_typescript.language_tsx())
        go_language = Language(tree_sitter_go.language())
        java_language = Language(tree_sitter_java.language())

        self._languages: dict[str, Language] = {
            ".py": python_language,
            ".js": javascript_language,
            ".jsx": javascript_language,
            ".ts": typescript_language,
            ".tsx": tsx_language,
            ".go": go_language,
            ".java": java_language,
        }
        self.python_parser = Parser(python_language)
        self.javascript_parser = Parser(javascript_language)
        self.typescript_parser = Parser(typescript_language)
        self.tsx_parser = Parser(tsx_language)
        self.go_parser = Parser(go_language)
        self.java_parser = Parser(java_language)
        self._parsers: dict[str, Parser] = {
            ".py": self.python_parser,
            ".js": self.javascript_parser,
            ".jsx": self.javascript_parser,
            ".ts": self.typescript_parser,
            ".tsx": self.tsx_parser,
            ".go": self.go_parser,
            ".java": self.java_parser,
        }
        language_locks = {
            language_name: asyncio.Lock()
            for language_name in set(SUPPORTED_EXTENSIONS.values())
        }
        self._parse_locks: dict[str, asyncio.Lock] = {
            extension: language_locks[language_name]
            for extension, language_name in SUPPORTED_EXTENSIONS.items()
        }
        self._queries: dict[str, _LanguageQueries] = {
            ".py": self._compile_python_queries(python_language),
            ".js": self._compile_javascript_queries(javascript_language),
            ".jsx": self._compile_javascript_queries(javascript_language),
            ".ts": self._compile_typescript_queries(typescript_language),
            ".tsx": self._compile_typescript_queries(tsx_language),
            ".go": self._compile_go_queries(go_language),
            ".java": self._compile_java_queries(java_language),
        }

    @staticmethod
    def _compile_python_queries(language: Language) -> _LanguageQueries:
        """Compile Python definition, class, and call queries once."""

        return _LanguageQueries(
            function_definitions=Query(
                language, PYTHON_FUNCTION_DEFINITIONS_QUERY
            ),
            function_calls=Query(language, PYTHON_FUNCTION_CALLS_QUERY),
            class_definitions=Query(language, PYTHON_CLASS_DEFINITIONS_QUERY),
        )

    @staticmethod
    def _compile_typescript_queries(language: Language) -> _LanguageQueries:
        """Compile TypeScript queries for either the TypeScript or TSX grammar."""

        return _LanguageQueries(
            function_definitions=Query(
                language, TYPESCRIPT_FUNCTION_DEFINITIONS_QUERY
            ),
            function_calls=Query(language, TYPESCRIPT_FUNCTION_CALLS_QUERY),
            class_definitions=Query(
                language, TYPESCRIPT_CLASS_DEFINITIONS_QUERY
            ),
        )

    @staticmethod
    def _compile_javascript_queries(language: Language) -> _LanguageQueries:
        """Compile JavaScript queries shared by ``.js`` and ``.jsx``."""

        return _LanguageQueries(
            function_definitions=Query(
                language, JAVASCRIPT_FUNCTION_DEFINITIONS_QUERY
            ),
            function_calls=Query(language, JAVASCRIPT_FUNCTION_CALLS_QUERY),
            class_definitions=Query(
                language, JAVASCRIPT_CLASS_DEFINITIONS_QUERY
            ),
        )

    @staticmethod
    def _compile_go_queries(language: Language) -> _LanguageQueries:
        """Compile Go function, method, call, and type queries."""

        return _LanguageQueries(
            function_definitions=Query(
                language, GO_FUNCTION_DEFINITIONS_QUERY
            ),
            function_calls=Query(language, GO_FUNCTION_CALLS_QUERY),
            class_definitions=Query(language, GO_CLASS_DEFINITIONS_QUERY),
        )

    @staticmethod
    def _compile_java_queries(language: Language) -> _LanguageQueries:
        """Compile Java method, constructor, invocation, and class queries."""

        return _LanguageQueries(
            function_definitions=Query(
                language, JAVA_FUNCTION_DEFINITIONS_QUERY
            ),
            function_calls=Query(language, JAVA_FUNCTION_CALLS_QUERY),
            class_definitions=Query(language, JAVA_CLASS_DEFINITIONS_QUERY),
        )

    @classmethod
    def _normalize_extension(cls, file_extension: str) -> str:
        """Normalize and validate a source file extension."""

        normalized = file_extension.strip().lower()
        if normalized and not normalized.startswith("."):
            normalized = f".{normalized}"
        if normalized not in cls._SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(cls._SUPPORTED_EXTENSIONS))
            raise ValueError(
                f"Unsupported file extension '{file_extension}'. "
                f"Supported extensions: {supported}"
            )
        return normalized

    def get_parser(self, file_extension: str) -> Parser:
        """Return the initialized parser for any supported source extension.

        Args:
            file_extension: File suffix, with or without a leading period.

        Raises:
            ValueError: If the extension is not supported.
        """

        return self._parsers[self._normalize_extension(file_extension)]

    @staticmethod
    def _capture_text(
        query: Query,
        capture_name: str,
        root_node: Node,
        source_code: bytes,
    ) -> list[str]:
        """Run a query and decode one capture in deterministic source order."""

        captures = QueryCursor(query).captures(root_node)
        nodes = sorted(
            captures.get(capture_name, []),
            key=lambda node: (node.start_byte, node.end_byte),
        )
        return [
            source_code[node.start_byte : node.end_byte].decode(
                "utf-8", errors="replace"
            )
            for node in nodes
        ]

    @staticmethod
    def _text(node: Node, source_code: bytes) -> str:
        return source_code[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )

    @classmethod
    def _lexical_scope(cls, definition: Node, source_code: bytes) -> list[str]:
        """Collect named enclosing classes/functions, outermost first."""

        scope: list[str] = []
        parent = definition.parent
        scope_types = {
            "class_definition",
            "class_declaration",
            "abstract_class_declaration",
            "interface_declaration",
            "record_declaration",
            "internal_module",
            "function_definition",
            "function_declaration",
            "generator_function_declaration",
            "method_definition",
            "method_declaration",
            "constructor_declaration",
            "function_signature",
            "method_signature",
            "variable_declarator",
        }
        while parent is not None:
            if parent.type in scope_types:
                name = parent.child_by_field_name("name")
                if name is not None:
                    scope.append(cls._text(name, source_code))
            parent = parent.parent
        scope.reverse()
        return scope

    @classmethod
    def _definition_body(cls, definition: Node) -> Node | None:
        if definition.type == "variable_declarator":
            value = definition.child_by_field_name("value")
            return value.child_by_field_name("body") if value is not None else None
        return definition.child_by_field_name("body")

    @classmethod
    def _signature(cls, definition: Node, source_code: bytes) -> str | None:
        owner = definition
        if definition.type == "variable_declarator":
            owner = definition.child_by_field_name("value")
            if owner is None:
                return None
        parameters = owner.child_by_field_name("parameters")
        if parameters is None:
            return None
        return re.sub(r"\s+", " ", cls._text(parameters, source_code)).strip()

    @classmethod
    def _qualified_name(cls, definition: Node, name: str, source_code: bytes) -> str:
        scope = cls._lexical_scope(definition, source_code)
        if definition.type == "method_declaration":
            receiver = definition.child_by_field_name("receiver")
            if receiver is not None:
                receiver_types = [
                    child
                    for child in receiver.children
                    if child.type == "type_identifier"
                ]
                if not receiver_types:
                    stack = list(receiver.named_children)
                    while stack:
                        child = stack.pop()
                        if child.type == "type_identifier":
                            receiver_types.append(child)
                        stack.extend(child.named_children)
                if receiver_types:
                    scope.append(cls._text(receiver_types[0], source_code))
        return ".".join([*scope, name])

    @staticmethod
    def _line_end(node: Node) -> int:
        return node.end_point.row + (1 if node.end_point.column else 0)

    @classmethod
    def _capture_function_records(
        cls,
        query: Query,
        root_node: Node,
        source_code: bytes,
        file_path: str,
        language: str,
    ) -> list[tuple[Node, dict[str, Any]]]:
        """Pair each named definition with source and deterministic metadata."""

        records: list[tuple[Node, dict[str, Any]]] = []
        for _, captures in QueryCursor(query).matches(root_node):
            name_nodes = captures.get("name", [])
            definition_nodes = captures.get("definition", [])
            if len(name_nodes) != 1 or len(definition_nodes) != 1:
                continue
            name_node = name_nodes[0]
            definition_node = definition_nodes[0]
            name = cls._text(name_node, source_code)
            raw_code = cls._text(definition_node, source_code)
            signature = cls._signature(definition_node, source_code)
            body = cls._definition_body(definition_node)
            records.append(
                (
                    definition_node,
                    {
                        "name": name,
                        "qualified_name": cls._qualified_name(
                            definition_node, name, source_code
                        ),
                        "file_path": file_path,
                        "language": language,
                        "signature": signature,
                        "has_body": body is not None,
                        "start_line": definition_node.start_point.row + 1,
                        "end_line": cls._line_end(definition_node),
                        "start_column": definition_node.start_point.column,
                        "end_column": definition_node.end_point.column,
                        "raw_code": raw_code,
                        "calls": [],
                    },
                )
            )
        records.sort(key=lambda item: (item[0].start_byte, item[0].end_byte))
        occurrences: dict[tuple[str, str | None], int] = {}
        for _, record in records:
            key = (record["qualified_name"], record["signature"])
            occurrences[key] = occurrences.get(key, 0) + 1
            signature_part = record["signature"] or "unknown"
            record["definition_discriminator"] = (
                f"signature:{signature_part};occurrence:{occurrences[key]}"
            )
        return records

    @classmethod
    def _capture_call_sites(
        cls,
        query: Query,
        root_node: Node,
        source_code: bytes,
        definitions: list[tuple[Node, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Attribute syntax to the innermost captured lexical function body."""

        unattributed: list[dict[str, Any]] = []
        captures = QueryCursor(query).captures(root_node).get("call", [])
        for name_node in sorted(captures, key=lambda node: node.start_byte):
            call_node = name_node
            while call_node.parent is not None and call_node.type not in {
                "call",
                "call_expression",
                "method_invocation",
            }:
                call_node = call_node.parent
            if call_node.type not in {
                "call",
                "call_expression",
                "method_invocation",
            }:
                continue
            target = call_node.child_by_field_name("function")
            if target is None:
                target = call_node.child_by_field_name("name") or name_node
                receiver = call_node.child_by_field_name("object")
                syntax = (
                    f"{cls._text(receiver, source_code)}."
                    f"{cls._text(target, source_code)}"
                    if receiver is not None
                    else cls._text(target, source_code)
                )
            else:
                syntax = cls._text(target, source_code)
            call = {
                "name": cls._text(name_node, source_code),
                "syntax": syntax,
                "start_line": call_node.start_point.row + 1,
                "end_line": cls._line_end(call_node),
                "start_column": call_node.start_point.column,
                "end_column": call_node.end_point.column,
                "resolution": "unresolved",
            }
            candidates: list[tuple[int, Node, dict[str, Any]]] = []
            for definition, record in definitions:
                body = cls._definition_body(definition)
                if body is None or not (
                    body.start_byte <= call_node.start_byte
                    and call_node.end_byte <= body.end_byte
                ):
                    continue
                candidates.append((body.end_byte - body.start_byte, definition, record))
            if candidates:
                _, definition, owner = min(candidates, key=lambda item: item[0])
                current = call_node.parent
                anonymous_boundary = False
                while current is not None and current != definition:
                    if current.type in {
                        "lambda",
                        "lambda_expression",
                        "arrow_function",
                        "function_expression",
                        "function",
                        "generator_function",
                        "func_literal",
                    }:
                        if not (
                            definition.type == "variable_declarator"
                            and current == definition.child_by_field_name("value")
                        ):
                            anonymous_boundary = True
                            break
                    current = current.parent
                if not anonymous_boundary:
                    owner["calls"].append(call)
                    continue
            unattributed.append(call)
        return unattributed

    def _parse_source(
        self,
        file_path: str,
        extension: str,
        source_code: bytes,
    ) -> dict[str, Any]:
        """Synchronously parse and query source code in a worker thread."""

        parser = self.get_parser(extension)
        tree = parser.parse(source_code)
        root_node = tree.root_node
        queries = self._queries[extension]

        if root_node.has_error:
            logger.warning("Tree-sitter found syntax errors while parsing %s", file_path)

        language = SUPPORTED_EXTENSIONS[extension]
        definitions = self._capture_function_records(
            queries.function_definitions,
            root_node,
            source_code,
            file_path,
            language,
        )
        unattributed_calls = self._capture_call_sites(
            queries.function_calls, root_node, source_code, definitions
        )
        functions = [record for _, record in definitions]

        return {
            "file_path": file_path,
            "defined_classes": self._capture_text(
                queries.class_definitions,
                "name",
                root_node,
                source_code,
            ),
            "defined_functions": [
                function["name"] for function in functions if function["has_body"]
            ],
            "functions": functions,
            "unattributed_calls": unattributed_calls,
            "outgoing_calls": self._capture_text(
                queries.function_calls,
                "call",
                root_node,
                source_code,
            ),
        }

    async def parse_file(
        self,
        file_path: str,
        source_code: bytes,
        *,
        repository: str | None = None,
        repository_relative_path: str | None = None,
    ) -> dict[str, Any]:
        """Extract classes, functions, and outgoing calls from one source file.

        Parsing is CPU-bound and therefore runs in a worker thread so callers do
        not block FastAPI's event loop. Results preserve source order and are
        shaped for direct transformation into Neo4j nodes and relationships.

        Args:
            file_path: Logical or filesystem path used to select the grammar and
                identify the resulting file record.
            source_code: UTF-8 encoded source bytes in a supported language.
            repository: Optional repository scope. When supplied, function
                entity IDs are generated from the repository and relative path.
            repository_relative_path: Stable path to use when ``file_path`` is
                a temporary absolute path. Required in that case if repository
                identity is requested.

        Returns:
            A dictionary containing ``file_path``, ``defined_classes``,
            ``defined_functions``, structured ``functions`` with raw code and
            lexical metadata, ``outgoing_calls``, and ``unattributed_calls``.

        Raises:
            TypeError: If ``source_code`` is not bytes.
            ValueError: If ``file_path`` has an unsupported extension.
                Also raised if a requested identity has an invalid relative path.
        """

        if not isinstance(source_code, bytes):
            raise TypeError("source_code must be bytes")

        extension = self._normalize_extension(Path(file_path).suffix)
        async with self._parse_locks[extension]:
            result = await asyncio.to_thread(
                self._parse_source,
                file_path,
                extension,
                source_code,
            )
        if repository is not None:
            attach_function_entity_ids(
                result,
                repository=repository,
                file_path=repository_relative_path or file_path,
            )
        return result


def attach_function_entity_ids(
    parsed_file: dict[str, Any],
    *,
    repository: str,
    file_path: str,
) -> dict[str, Any]:
    """Attach repository identity after a file has a repository-relative path.

    Kept separate so full ingest can parse temporary absolute paths and attach
    keys only after converting them to stable repository-relative paths.
    """

    normalized_path = normalize_repository_path(file_path)
    normalized_repository = repository.strip()
    if not normalized_repository:
        raise ValueError("repository must not be blank")
    parsed_file["file_path"] = normalized_path
    parsed_file["repository"] = normalized_repository
    for function in parsed_file.get("functions", []):
        function["file_path"] = normalized_path
        function["repository"] = normalized_repository
        function["entity_id"] = generate_function_entity_id(
            repository=normalized_repository,
            file_path=normalized_path,
            language=function["language"],
            qualified_name=function["qualified_name"],
            discriminator=function["definition_discriminator"],
        )
    return parsed_file


async def parse_changed_files_with_progress(
    file_paths: list[str],
) -> AsyncIterator[ParsedFileProgress]:
    """Parse files concurrently and yield once whenever a file completes.

    Failed files yield a progress item whose ``result`` is ``None``. This lets
    streaming callers advance their progress bar without persisting bad input.
    The ``index`` field lets batch callers restore the input ordering even
    though files can complete out of order.
    """

    total = len(file_paths)
    if total == 0:
        return

    code_parser = CodeParser()
    file_read_slots = asyncio.Semaphore(MAX_CONCURRENT_FILE_READS)

    async def parse_path(
        index: int,
        file_path: str,
    ) -> tuple[int, dict[str, Any] | None, int]:
        path = Path(file_path)
        source_tokens = 0
        try:
            async with file_read_slots:
                source_code = await asyncio.to_thread(path.read_bytes)
                source_text = source_code.decode("utf-8", errors="replace")
                source_tokens = await asyncio.to_thread(
                    count_tokens,
                    source_text,
                )
                result = await code_parser.parse_file(file_path, source_code)
            result["source_tokens"] = source_tokens
            return index, result, source_tokens
        except FileNotFoundError:
            logger.info("Skipping missing or deleted source file: %s", file_path)
        except UnicodeDecodeError as exc:
            logger.warning("Skipping source file %s: %s", file_path, exc)
        except OSError as exc:
            logger.warning("Unable to read source file %s: %s", file_path, exc)
        except ValueError as exc:
            logger.warning("Skipping unsupported source file %s: %s", file_path, exc)
        except Exception as exc:
            logger.warning(
                "Tree-sitter failed to parse source file %s: %s",
                file_path,
                exc,
                exc_info=True,
            )
        return index, None, source_tokens

    tasks = [
        asyncio.create_task(parse_path(index, file_path))
        for index, file_path in enumerate(file_paths)
    ]
    try:
        for processed, completed_task in enumerate(
            asyncio.as_completed(tasks),
            start=1,
        ):
            index, result, source_tokens = await completed_task
            yield ParsedFileProgress(
                index=index,
                processed=processed,
                total=total,
                result=result,
                source_tokens=source_tokens,
            )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def parse_changed_files(
    file_paths: list[str],
) -> list[dict[str, Any]]:
    """Parse source files and return successful results in input order."""

    parsed_files: list[dict[str, Any] | None] = [
        None for _ in file_paths
    ]
    async for progress in parse_changed_files_with_progress(file_paths):
        parsed_files[progress.index] = progress.result
    return [result for result in parsed_files if result is not None]
