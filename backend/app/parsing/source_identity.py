"""Attach repository identity to files the parser extracted."""

from app.parsing.entity_identity import (
    generate_function_entity_id,
    normalize_repository_path,
)
from app.parsing.parse_results import (
    IdentifiedFile,
    IdentifiedFunction,
    ParsedSource,
    field_values,
)


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
                **field_values(function),
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
