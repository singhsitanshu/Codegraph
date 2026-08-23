import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Query, QueryCursor


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
  name: (identifier) @name)
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
  name: (identifier) @name)

(generator_function_declaration
  name: (identifier) @name)

(method_definition
  name: (property_identifier) @name)

(variable_declarator
  name: (identifier) @name
  value: [(arrow_function) (function_expression)])
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
(function_declaration
  name: (identifier) @name)

(generator_function_declaration
  name: (identifier) @name)

(method_definition
  name: (property_identifier) @name)

(variable_declarator
  name: (identifier) @name
  value: [(arrow_function) (function_expression)])
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
  name: (identifier) @name)

(method_declaration
  name: (field_identifier) @name)
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
  body: (block))

(constructor_declaration
  name: (identifier) @name
  body: (constructor_body))
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
    result: dict[str, str | list[str]] | None


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

    def _parse_source(
        self,
        file_path: str,
        extension: str,
        source_code: bytes,
    ) -> dict[str, str | list[str]]:
        """Synchronously parse and query source code in a worker thread."""

        parser = self.get_parser(extension)
        tree = parser.parse(source_code)
        root_node = tree.root_node
        queries = self._queries[extension]

        if root_node.has_error:
            logger.warning("Tree-sitter found syntax errors while parsing %s", file_path)

        return {
            "file_path": file_path,
            "defined_classes": self._capture_text(
                queries.class_definitions,
                "name",
                root_node,
                source_code,
            ),
            "defined_functions": self._capture_text(
                queries.function_definitions,
                "name",
                root_node,
                source_code,
            ),
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
    ) -> dict[str, str | list[str]]:
        """Extract classes, functions, and outgoing calls from one source file.

        Parsing is CPU-bound and therefore runs in a worker thread so callers do
        not block FastAPI's event loop. Results preserve source order and are
        shaped for direct transformation into Neo4j nodes and relationships.

        Args:
            file_path: Logical or filesystem path used to select the grammar and
                identify the resulting file record.
            source_code: UTF-8 encoded source bytes in a supported language.

        Returns:
            A dictionary containing ``file_path``, ``defined_classes``,
            ``defined_functions``, and ``outgoing_calls``.

        Raises:
            TypeError: If ``source_code`` is not bytes.
            ValueError: If ``file_path`` has an unsupported extension.
        """

        if not isinstance(source_code, bytes):
            raise TypeError("source_code must be bytes")

        extension = self._normalize_extension(Path(file_path).suffix)
        async with self._parse_locks[extension]:
            return await asyncio.to_thread(
                self._parse_source,
                file_path,
                extension,
                source_code,
            )


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
    ) -> tuple[int, dict[str, str | list[str]] | None]:
        path = Path(file_path)
        try:
            async with file_read_slots:
                source_code = await asyncio.to_thread(path.read_bytes)
                result = await code_parser.parse_file(file_path, source_code)
            return index, result
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
        return index, None

    tasks = [
        asyncio.create_task(parse_path(index, file_path))
        for index, file_path in enumerate(file_paths)
    ]
    try:
        for processed, completed_task in enumerate(
            asyncio.as_completed(tasks),
            start=1,
        ):
            index, result = await completed_task
            yield ParsedFileProgress(
                index=index,
                processed=processed,
                total=total,
                result=result,
            )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def parse_changed_files(
    file_paths: list[str],
) -> list[dict[str, str | list[str]]]:
    """Parse source files and return successful results in input order."""

    parsed_files: list[dict[str, str | list[str]] | None] = [
        None for _ in file_paths
    ]
    async for progress in parse_changed_files_with_progress(file_paths):
        parsed_files[progress.index] = progress.result
    return [result for result in parsed_files if result is not None]
