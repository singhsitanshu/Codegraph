import asyncio
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from tree_sitter import Language, Node, Parser, Query, QueryCursor

from app.services.languages import LANGUAGE_BY_EXTENSION, LANGUAGES, LanguageSpec
from app.utils.entity_identity import (
    generate_function_entity_id,
    normalize_repository_path,
)
from app.utils.tokens import count_tokens


logger = logging.getLogger(__name__)
MAX_CONCURRENT_FILE_READS = 32


@dataclass(frozen=True, slots=True)
class _LanguageQueries:
    """Compiled queries needed to extract one language's code relationships."""

    function_definitions: Query
    function_calls: Query
    class_definitions: Query


@dataclass(frozen=True, slots=True)
class _LoadedLanguage:
    """A language's reusable parser, compiled queries and parse lock."""

    spec: LanguageSpec
    parser: Parser
    queries: _LanguageQueries
    lock: asyncio.Lock

    @classmethod
    def load(cls, spec: LanguageSpec) -> "_LoadedLanguage":
        language = Language(spec.grammar())
        return cls(
            spec=spec,
            parser=Parser(language),
            queries=_LanguageQueries(
                function_definitions=Query(
                    language, spec.function_definitions_query
                ),
                function_calls=Query(language, spec.function_calls_query),
                class_definitions=Query(language, spec.class_definitions_query),
            ),
            lock=asyncio.Lock(),
        )


@dataclass(frozen=True, slots=True)
class CallSite:
    """One call expression. The parser records the callee name, not its target."""

    name: str
    syntax: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int


@dataclass(frozen=True, slots=True)
class FunctionDeclaration:
    """A named definition's lexical identity metadata and source span.

    Used on its own for declaration-only signatures without a body, such as
    TypeScript overload or interface method signatures.
    """

    name: str
    qualified_name: str
    signature: str | None
    definition_discriminator: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    raw_code: str


@dataclass(frozen=True, slots=True)
class ParsedFunction(FunctionDeclaration):
    """An executable definition and the calls attributed to its body."""

    calls: tuple[CallSite, ...]


@dataclass(frozen=True, slots=True)
class IdentifiedFunction(ParsedFunction):
    """An executable definition with its repository-scoped ``entity_id``."""

    entity_id: str


@dataclass(frozen=True, slots=True)
class ParsedSource:
    """Syntax extracted from one source file, before repository identity.

    ``file_path`` is the path the parser was given, which may be a temporary
    absolute path. Executable definitions and declaration-only signatures are
    kept apart so consumers never have to filter one out of the other.
    """

    file_path: str
    language: str
    defined_classes: tuple[str, ...]
    functions: tuple[ParsedFunction, ...]
    declarations: tuple[FunctionDeclaration, ...]
    unattributed_calls: tuple[CallSite, ...]
    outgoing_calls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IdentifiedFile:
    """A parsed file placed in a repository, ready for the graph writer.

    Built only by :func:`identify_parsed_source`: ``file_path`` is a normalized
    repository-relative path and every function's ``entity_id`` was generated
    from ``repository``, ``file_path`` and ``language``.
    """

    repository: str
    file_path: str
    language: str
    functions: tuple[IdentifiedFunction, ...]


@dataclass(frozen=True, slots=True)
class ParsedFileProgress:
    """One completed file from a concurrently parsed batch.

    ``result`` is ``None`` when the file could not be read or parsed.
    ``source_tokens`` counts the file's source whenever it could be read.
    """

    index: int
    processed: int
    total: int
    source_tokens: int
    result: ParsedSource | None


@dataclass(frozen=True, slots=True)
class ParsedBatch:
    """Files parsed by :func:`parse_changed_files`, in input order."""

    files: list[ParsedSource]
    source_tokens: int


@dataclass(frozen=True, slots=True)
class _CapturedDefinition:
    """A definition node, its body (``None`` for a declaration) and metadata."""

    node: Node
    body: Node | None
    declaration: FunctionDeclaration


class CodeParser:
    """Normalize source files in every language registered in ``LANGUAGES``.

    Grammar packages are loaded from their precompiled Python wheels. No grammar
    compilation, C toolchain, or legacy ``Language.build_library`` call is used.
    Parser instances are retained for reuse, while per-language locks prevent a
    single parser from being used concurrently by multiple background threads.
    """

    def __init__(self) -> None:
        """Initialize parsers and compile extraction queries for all grammars."""

        self._languages: dict[str, _LoadedLanguage] = {
            extension: language
            for language in map(_LoadedLanguage.load, LANGUAGES)
            for extension in language.spec.extensions
        }

    @classmethod
    def _normalize_extension(cls, file_extension: str) -> str:
        """Normalize and validate a source file extension."""

        normalized = file_extension.strip().lower()
        if normalized and not normalized.startswith("."):
            normalized = f".{normalized}"
        if normalized not in LANGUAGE_BY_EXTENSION:
            supported = ", ".join(sorted(LANGUAGE_BY_EXTENSION))
            raise ValueError(
                f"Unsupported file extension '{file_extension}'. "
                f"Supported extensions: {supported}"
            )
        return normalized

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
    def _lexical_scope(
        cls, spec: LanguageSpec, definition: Node, source_code: bytes
    ) -> list[str]:
        """Collect named enclosing classes/functions, outermost first."""

        scope: list[str] = []
        parent = definition.parent
        while parent is not None:
            if parent.type in spec.scope_node_types:
                name = parent.child_by_field_name("name")
                if name is not None:
                    scope.append(cls._text(name, source_code))
            parent = parent.parent
        scope.reverse()
        return scope

    @classmethod
    def _definition_body(cls, spec: LanguageSpec, definition: Node) -> Node | None:
        if definition.type in spec.assigned_function_node_types:
            value = definition.child_by_field_name("value")
            return value.child_by_field_name("body") if value is not None else None
        return definition.child_by_field_name("body")

    @classmethod
    def _signature(
        cls, spec: LanguageSpec, definition: Node, source_code: bytes
    ) -> str | None:
        owner = definition
        if definition.type in spec.assigned_function_node_types:
            owner = definition.child_by_field_name("value")
            if owner is None:
                return None
        parameters = owner.child_by_field_name("parameters")
        if parameters is None:
            return None
        return re.sub(r"\s+", " ", cls._text(parameters, source_code)).strip()

    @classmethod
    def _qualified_name(
        cls,
        spec: LanguageSpec,
        definition: Node,
        name: str,
        source_code: bytes,
    ) -> str:
        scope = cls._lexical_scope(spec, definition, source_code)
        if definition.type in spec.receiver_method_node_types:
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
    def _capture_definitions(
        cls,
        spec: LanguageSpec,
        query: Query,
        root_node: Node,
        source_code: bytes,
    ) -> list[_CapturedDefinition]:
        """Pair each named definition with its body and deterministic metadata."""

        matches: list[tuple[Node, str, str | None]] = []
        for _, captures in QueryCursor(query).matches(root_node):
            name_nodes = captures.get("name", [])
            definition_nodes = captures.get("definition", [])
            if len(name_nodes) != 1 or len(definition_nodes) != 1:
                continue
            definition_node = definition_nodes[0]
            matches.append(
                (
                    definition_node,
                    cls._text(name_nodes[0], source_code),
                    cls._signature(spec, definition_node, source_code),
                )
            )
        matches.sort(key=lambda item: (item[0].start_byte, item[0].end_byte))

        definitions: list[_CapturedDefinition] = []
        occurrences: dict[tuple[str, str | None], int] = {}
        for definition_node, name, signature in matches:
            qualified_name = cls._qualified_name(
                spec, definition_node, name, source_code
            )
            key = (qualified_name, signature)
            occurrences[key] = occurrences.get(key, 0) + 1
            definitions.append(
                _CapturedDefinition(
                    node=definition_node,
                    body=cls._definition_body(spec, definition_node),
                    declaration=FunctionDeclaration(
                        name=name,
                        qualified_name=qualified_name,
                        signature=signature,
                        definition_discriminator=(
                            f"signature:{signature or 'unknown'};"
                            f"occurrence:{occurrences[key]}"
                        ),
                        start_line=definition_node.start_point.row + 1,
                        end_line=cls._line_end(definition_node),
                        start_column=definition_node.start_point.column,
                        end_column=definition_node.end_point.column,
                        raw_code=cls._text(definition_node, source_code),
                    ),
                )
            )
        return definitions

    @classmethod
    def _capture_call_sites(
        cls,
        spec: LanguageSpec,
        query: Query,
        root_node: Node,
        source_code: bytes,
        definitions: list[_CapturedDefinition],
    ) -> tuple[dict[int, list[CallSite]], list[CallSite]]:
        """Attribute syntax to the innermost captured lexical function body.

        Returns the calls owned by each definition, keyed by the definition
        node's ID, and the calls no definition could confidently own.
        """

        owned: dict[int, list[CallSite]] = {}
        unattributed: list[CallSite] = []
        owners_by_body: dict[int, Node] = {}
        for definition in definitions:
            if definition.body is not None:
                owners_by_body.setdefault(definition.body.id, definition.node)
        captures = QueryCursor(query).captures(root_node).get("call", [])
        for name_node in sorted(captures, key=lambda node: node.start_byte):
            call_node = name_node
            while (
                call_node.parent is not None
                and call_node.type not in spec.call_node_types
            ):
                call_node = call_node.parent
            if call_node.type not in spec.call_node_types:
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
            call = CallSite(
                name=cls._text(name_node, source_code),
                syntax=syntax,
                start_line=call_node.start_point.row + 1,
                end_line=cls._line_end(call_node),
                start_column=call_node.start_point.column,
                end_column=call_node.end_point.column,
            )
            # The nearest enclosing body is the innermost lexical owner. Walking
            # ancestors avoids checking every definition for every call site.
            current = call_node
            definition = None
            while current is not None:
                definition = owners_by_body.get(current.id)
                if definition is not None:
                    break
                current = current.parent
            if definition is not None:
                current = call_node.parent
                anonymous_boundary = False
                while current is not None and current != definition:
                    if current.type in spec.anonymous_function_node_types:
                        if not (
                            definition.type in spec.assigned_function_node_types
                            and current == definition.child_by_field_name("value")
                        ):
                            anonymous_boundary = True
                            break
                    current = current.parent
                if not anonymous_boundary:
                    owned.setdefault(definition.id, []).append(call)
                    continue
            unattributed.append(call)
        return owned, unattributed

    def _parse_source(
        self,
        file_path: str,
        language: _LoadedLanguage,
        source_code: bytes,
    ) -> ParsedSource:
        """Synchronously parse and query source code in a worker thread."""

        tree = language.parser.parse(source_code)
        root_node = tree.root_node
        queries = language.queries

        if root_node.has_error:
            logger.warning("Tree-sitter found syntax errors while parsing %s", file_path)

        definitions = self._capture_definitions(
            language.spec,
            queries.function_definitions,
            root_node,
            source_code,
        )
        owned_calls, unattributed_calls = self._capture_call_sites(
            language.spec,
            queries.function_calls,
            root_node,
            source_code,
            definitions,
        )

        return ParsedSource(
            file_path=file_path,
            language=language.spec.name,
            defined_classes=tuple(
                self._capture_text(
                    queries.class_definitions,
                    "name",
                    root_node,
                    source_code,
                )
            ),
            functions=tuple(
                ParsedFunction(
                    **_field_values(definition.declaration),
                    calls=tuple(owned_calls.get(definition.node.id, ())),
                )
                for definition in definitions
                if definition.body is not None
            ),
            declarations=tuple(
                definition.declaration
                for definition in definitions
                if definition.body is None
            ),
            unattributed_calls=tuple(unattributed_calls),
            outgoing_calls=tuple(
                self._capture_text(
                    queries.function_calls,
                    "call",
                    root_node,
                    source_code,
                )
            ),
        )

    async def parse_file(
        self,
        file_path: str,
        source_code: bytes,
    ) -> ParsedSource:
        """Extract classes, functions, and outgoing calls from one source file.

        Parsing is CPU-bound and therefore runs in a worker thread so callers do
        not block FastAPI's event loop. Results preserve source order. Pass the
        result to :func:`identify_parsed_source` once its repository-relative
        path is known to obtain the graph writer's input.

        Args:
            file_path: Logical or filesystem path used to select the grammar and
                identify the resulting file record.
            source_code: UTF-8 encoded source bytes in a supported language.

        Raises:
            TypeError: If ``source_code`` is not bytes.
            ValueError: If ``file_path`` has an unsupported extension.
        """

        if not isinstance(source_code, bytes):
            raise TypeError("source_code must be bytes")

        extension = self._normalize_extension(Path(file_path).suffix)
        language = self._languages[extension]
        async with language.lock:
            return await asyncio.to_thread(
                self._parse_source,
                file_path,
                language,
                source_code,
            )


def _field_values(record: Any) -> dict[str, Any]:
    """Return a dataclass's own field values without converting nested records."""

    return {field.name: getattr(record, field.name) for field in fields(record)}


def identify_parsed_source(
    parsed_source: ParsedSource,
    *,
    repository: str,
    file_path: str,
) -> IdentifiedFile:
    """Place a parsed file in a repository and generate its function identities.

    Kept separate from parsing so full ingest can parse temporary absolute paths
    and identify files only after converting them to repository-relative paths.

    Raises:
        ValueError: If ``file_path`` is not repository-relative.
    """

    normalized_path = normalize_repository_path(file_path)
    return IdentifiedFile(
        repository=repository,
        file_path=normalized_path,
        language=parsed_source.language,
        functions=tuple(
            IdentifiedFunction(
                **_field_values(function),
                entity_id=generate_function_entity_id(
                    repository=repository,
                    file_path=normalized_path,
                    language=parsed_source.language,
                    qualified_name=function.qualified_name,
                    discriminator=function.definition_discriminator,
                ),
            )
            for function in parsed_source.functions
        ),
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
    ) -> tuple[int, ParsedSource | None, int]:
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
                source_tokens=source_tokens,
                result=result,
            )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def parse_changed_files(file_paths: list[str]) -> ParsedBatch:
    """Parse source files, keeping successful results in input order."""

    parsed_by_index: dict[int, ParsedSource] = {}
    source_tokens = 0
    async for progress in parse_changed_files_with_progress(file_paths):
        source_tokens += progress.source_tokens
        if progress.result is not None:
            parsed_by_index[progress.index] = progress.result
    return ParsedBatch(
        files=[parsed_by_index[index] for index in sorted(parsed_by_index)],
        source_tokens=source_tokens,
    )
