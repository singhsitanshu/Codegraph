"""Records produced by parsing source files and placing them in a repository."""

from dataclasses import dataclass, fields
from typing import Any


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


def field_values(record: Any) -> dict[str, Any]:
    """Return a dataclass's own field values without converting nested records."""

    return {field.name: getattr(record, field.name) for field in fields(record)}
