"""Stable parser identities and lexical call-site attribution."""

import asyncio
from pathlib import Path

import pytest

from app.services.parse_results import IdentifiedFile, ParsedSource
from app.services.parser_service import CodeParser
from app.services.source_identity import identify_parsed_source
from app.services.graph_records import extract_graph_records
from app.services.repository_ingestion import identify_repository_files
from app.utils.entity_identity import (
    generate_function_entity_id,
    normalize_repository_path,
)


REPOSITORY = "example/backend"


def parse_source(file_path: str, source: bytes) -> ParsedSource:
    return asyncio.run(CodeParser().parse_file(file_path, source))


def parse(file_path: str, source: bytes) -> IdentifiedFile:
    return identify_parsed_source(
        parse_source(file_path, source),
        repository=REPOSITORY,
        file_path=file_path,
    )


def test_same_name_in_different_files_has_different_entity_ids() -> None:
    source = b"def validate():\n    return True\n"
    auth_file = parse("src/auth.py", source)
    payments_file = parse("src/payments.py", source)
    auth = auth_file.functions[0]
    payments = payments_file.functions[0]

    assert auth.qualified_name == payments.qualified_name == "validate"
    assert auth.entity_id != payments.entity_id
    assert auth_file.file_path == "src/auth.py"
    assert payments_file.file_path == "src/payments.py"
    assert auth_file.repository == payments_file.repository == REPOSITORY


def test_same_named_methods_in_different_classes_are_distinct() -> None:
    result = parse(
        "src/services.py",
        b"class PaymentService:\n"
        b"    def validate(self):\n        pass\n"
        b"class AuthenticationService:\n"
        b"    def validate(self):\n        pass\n",
    )
    methods = result.functions

    assert [item.qualified_name for item in methods] == [
        "PaymentService.validate",
        "AuthenticationService.validate",
    ]
    assert len({item.entity_id for item in methods}) == 2


def test_repeated_python_definition_uses_occurrence_discriminator() -> None:
    result = parse(
        "src/repeated.py",
        b"def validate(value):\n    return value\n"
        b"def validate(value):\n    return not value\n",
    )
    first, second = result.functions

    assert first.qualified_name == second.qualified_name == "validate"
    assert first.definition_discriminator == "signature:(value);occurrence:1"
    assert second.definition_discriminator == "signature:(value);occurrence:2"
    assert first.entity_id != second.entity_id
    assert (first.start_line, first.end_line) == (1, 2)
    assert (second.start_line, second.end_line) == (3, 4)


def test_java_overloads_are_distinguished_by_signature() -> None:
    result = parse(
        "src/Validator.java",
        b"class Validator {\n"
        b"  Validator() { init(); }\n"
        b"  void validate(String value) { check(value); }\n"
        b"  void validate(int value) { check(value); }\n"
        b"}\n",
    )
    constructor, first, second = result.functions

    assert constructor.qualified_name == "Validator.Validator"
    assert first.qualified_name == second.qualified_name == "Validator.validate"
    assert first.signature == "(String value)"
    assert second.signature == "(int value)"
    assert first.entity_id != second.entity_id


def test_typescript_overload_signatures_are_kept_apart_from_implementation() -> None:
    source = (
        b"class Validator {\n"
        b"  validate(value: string): void;\n"
        b"  validate(value: number): void;\n"
        b"  validate(value: any): void { check(value); }\n"
        b"}\n"
    )
    parsed = parse_source("src/validator.ts", source)

    assert [item.signature for item in parsed.declarations] == [
        "(value: string)",
        "(value: number)",
    ]
    assert [item.qualified_name for item in parsed.declarations] == [
        "Validator.validate",
        "Validator.validate",
    ]
    (implementation,) = parsed.functions
    assert implementation.qualified_name == "Validator.validate"
    assert implementation.definition_discriminator == (
        "signature:(value: any);occurrence:1"
    )
    assert [call.name for call in implementation.calls] == ["check"]

    identified = parse("src/validator.ts", source)
    _, persisted_functions, _ = extract_graph_records([identified], REPOSITORY)
    assert len(persisted_functions) == 1
    assert persisted_functions[0]["entity_id"] == identified.functions[0].entity_id
    assert "check(value)" in persisted_functions[0]["raw_code"]


def test_typescript_interface_methods_use_interface_scope() -> None:
    result = parse_source(
        "src/contracts.ts",
        b"interface A { validate(x: string): void; }\n"
        b"interface B { validate(x: string): void; }\n",
    )

    assert result.functions == ()
    assert [item.qualified_name for item in result.declarations] == [
        "A.validate", "B.validate"
    ]


def test_identity_is_deterministic_and_paths_are_normalized() -> None:
    source = b"def validate(value):\n    return value\n"
    files = [
        parse("src/./payments.py", source),
        parse("src/payments.py", source),
        parse("src\\payments.py", source),
    ]
    first, second, third = (file.functions[0] for file in files)
    body_edit = parse(
        "src/payments.py", b"def validate(value):\n    return not value\n"
    ).functions[0]

    assert first.entity_id == second.entity_id == third.entity_id
    assert body_edit.entity_id == first.entity_id
    assert {file.file_path for file in files} == {"src/payments.py"}
    assert first.entity_id.startswith("fn:v1:")
    assert first.entity_id == generate_function_entity_id(
        REPOSITORY,
        "src/payments.py",
        "python",
        "validate",
        "signature:(value);occurrence:1",
    )


def test_full_ingest_attaches_identity_after_temporary_path_is_relativized(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "src" / "payments.py"
    source_file.parent.mkdir()
    source_file.write_bytes(b"def validate():\n    return True\n")
    parsed = parse_source(str(source_file), source_file.read_bytes())
    assert parsed.file_path == str(source_file)

    (identified,) = identify_repository_files(
        [parsed], tmp_path, repository=REPOSITORY
    )

    assert identified.file_path == "src/payments.py"
    assert identified.repository == REPOSITORY
    assert identified.functions[0].entity_id == parse(
        "src/payments.py", source_file.read_bytes()
    ).functions[0].entity_id


@pytest.mark.parametrize("path", ["/absolute/x.py", "../escape.py", "C:\\root\\x.py"])
def test_identity_rejects_non_relative_paths(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_repository_path(path)


def test_files_cannot_be_identified_by_temporary_absolute_paths() -> None:
    parsed = parse_source("/tmp/checkout/example.py", b"def example(): pass\n")

    with pytest.raises(ValueError, match="repository-relative"):
        identify_parsed_source(
            parsed, repository=REPOSITORY, file_path=parsed.file_path
        )


def test_function_calls_are_attributed_to_the_enclosing_body() -> None:
    result = parse_source(
        "src/calls.py",
        b"def first():\n"
        b"    api.validate()\n"
        b"    def inner():\n"
        b"        nested()\n"
        b"def second():\n"
        b"    charge()\n"
        b"outside()\n",
    )
    first, inner, second = result.functions

    assert [function.qualified_name for function in result.functions] == [
        "first", "first.inner", "second"
    ]
    assert [call.name for call in first.calls] == ["validate"]
    assert first.calls[0].syntax == "api.validate"
    assert [call.name for call in inner.calls] == ["nested"]
    assert [call.name for call in second.calls] == ["charge"]
    assert [call.name for call in result.unattributed_calls] == ["outside"]
    assert result.outgoing_calls == ("validate", "nested", "charge", "outside")


def test_anonymous_callback_call_is_not_assigned_to_outer_function() -> None:
    result = parse_source(
        "src/callback.js",
        b"function outer() { run(() => hidden()); visible(); }\n",
    )
    outer = result.functions[0]

    assert [call.name for call in outer.calls] == ["run", "visible"]
    assert [call.name for call in result.unattributed_calls] == ["hidden"]


def test_go_function_literal_call_is_not_assigned_to_outer_function() -> None:
    result = parse_source(
        "src/callback.go",
        b"package p\nfunc Outer() { f := func() { hidden() }; visible(); _ = f }\n",
    )

    assert [call.name for call in result.functions[0].calls] == ["visible"]
    assert [call.name for call in result.unattributed_calls] == ["hidden"]


@pytest.mark.parametrize(
    ("path", "source", "expected_qualified"),
    [
        ("x.py", b"class A:\n def f(self):\n  g()\n", "A.f"),
        ("x.js", b"class A { f() { g(); } }\n", "A.f"),
        ("x.ts", b"class A { f(): void { g(); } }\n", "A.f"),
        ("x.go", b"package p\ntype A struct{}\nfunc (a *A) F() { g() }\n", "A.F"),
        ("x.java", b"class A { void f() { g(); } }\n", "A.f"),
    ],
)
def test_supported_languages_emit_identity_and_call_metadata(
    path: str, source: bytes, expected_qualified: str
) -> None:
    result = parse(path, source)
    function = result.functions[0]

    assert function.qualified_name == expected_qualified
    assert function.entity_id.startswith("fn:v1:")
    assert function.raw_code
    assert function.start_line >= 1
    assert function.end_line >= function.start_line
    assert [call.name for call in function.calls] == ["g"]
