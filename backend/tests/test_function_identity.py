"""Stable parser identities and lexical call-site attribution."""

import asyncio
from pathlib import Path

import pytest

from app.services.parser_service import CodeParser
from app.db.graph_ops import _extract_etl_records
from app.main import _use_repository_relative_paths
from app.utils.entity_identity import (
    generate_function_entity_id,
    normalize_repository_path,
)


REPOSITORY = "example/backend"


def parse(file_path: str, source: bytes) -> dict:
    return asyncio.run(
        CodeParser().parse_file(file_path, source, repository=REPOSITORY)
    )


def test_same_name_in_different_files_has_different_entity_ids() -> None:
    source = b"def validate():\n    return True\n"
    auth = parse("src/auth.py", source)["functions"][0]
    payments = parse("src/payments.py", source)["functions"][0]

    assert auth["qualified_name"] == payments["qualified_name"] == "validate"
    assert auth["entity_id"] != payments["entity_id"]
    assert auth["file_path"] == "src/auth.py"
    assert payments["file_path"] == "src/payments.py"


def test_same_named_methods_in_different_classes_are_distinct() -> None:
    result = parse(
        "src/services.py",
        b"class PaymentService:\n"
        b"    def validate(self):\n        pass\n"
        b"class AuthenticationService:\n"
        b"    def validate(self):\n        pass\n",
    )
    methods = result["functions"]

    assert [item["qualified_name"] for item in methods] == [
        "PaymentService.validate",
        "AuthenticationService.validate",
    ]
    assert len({item["entity_id"] for item in methods}) == 2


def test_repeated_python_definition_uses_occurrence_discriminator() -> None:
    result = parse(
        "src/repeated.py",
        b"def validate(value):\n    return value\n"
        b"def validate(value):\n    return not value\n",
    )
    first, second = result["functions"]

    assert first["qualified_name"] == second["qualified_name"] == "validate"
    assert first["definition_discriminator"] == "signature:(value);occurrence:1"
    assert second["definition_discriminator"] == "signature:(value);occurrence:2"
    assert first["entity_id"] != second["entity_id"]
    assert (first["start_line"], first["end_line"]) == (1, 2)
    assert (second["start_line"], second["end_line"]) == (3, 4)


def test_java_overloads_are_distinguished_by_signature() -> None:
    result = parse(
        "src/Validator.java",
        b"class Validator {\n"
        b"  Validator() { init(); }\n"
        b"  void validate(String value) { check(value); }\n"
        b"  void validate(int value) { check(value); }\n"
        b"}\n",
    )
    constructor, first, second = result["functions"]

    assert constructor["qualified_name"] == "Validator.Validator"
    assert first["qualified_name"] == second["qualified_name"] == "Validator.validate"
    assert first["signature"] == "(String value)"
    assert second["signature"] == "(int value)"
    assert first["entity_id"] != second["entity_id"]


def test_typescript_overload_signatures_and_implementation_are_distinct() -> None:
    result = parse(
        "src/validator.ts",
        b"class Validator {\n"
        b"  validate(value: string): void;\n"
        b"  validate(value: number): void;\n"
        b"  validate(value: any): void { check(value); }\n"
        b"}\n",
    )
    functions = result["functions"]

    assert len(functions) == 3
    assert {function["qualified_name"] for function in functions} == {
        "Validator.validate"
    }
    assert len({function["entity_id"] for function in functions}) == 3
    assert [function["has_body"] for function in functions] == [False, False, True]
    assert result["defined_functions"] == ["validate"]
    assert functions[0]["calls"] == functions[1]["calls"] == []
    assert [call["name"] for call in functions[2]["calls"]] == ["check"]
    _, legacy_functions, _ = _extract_etl_records([result])
    assert len(legacy_functions) == 1
    assert "check(value)" in legacy_functions[0]["raw_code"]


def test_typescript_interface_methods_use_interface_scope() -> None:
    result = parse(
        "src/contracts.ts",
        b"interface A { validate(x: string): void; }\n"
        b"interface B { validate(x: string): void; }\n",
    )

    assert [item["qualified_name"] for item in result["functions"]] == [
        "A.validate", "B.validate"
    ]
    assert len({item["entity_id"] for item in result["functions"]}) == 2


def test_identity_is_deterministic_and_paths_are_normalized() -> None:
    source = b"def validate(value):\n    return value\n"
    first = parse("src/./payments.py", source)["functions"][0]
    second = parse("src/payments.py", source)["functions"][0]
    third = parse("src\\payments.py", source)["functions"][0]
    body_edit = parse(
        "src/payments.py", b"def validate(value):\n    return not value\n"
    )["functions"][0]

    assert first["entity_id"] == second["entity_id"] == third["entity_id"]
    assert body_edit["entity_id"] == first["entity_id"]
    assert first["file_path"] == second["file_path"] == third["file_path"] == "src/payments.py"
    assert first["entity_id"].startswith("fn:v1:")
    assert first["entity_id"] == generate_function_entity_id(
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
    parsed = asyncio.run(
        CodeParser().parse_file(str(source_file), source_file.read_bytes())
    )

    _use_repository_relative_paths([parsed], str(tmp_path), repository=REPOSITORY)

    assert parsed["file_path"] == "src/payments.py"
    assert parsed["functions"][0]["file_path"] == "src/payments.py"
    assert parsed["functions"][0]["entity_id"] == parse(
        "src/payments.py", source_file.read_bytes()
    )["functions"][0]["entity_id"]


@pytest.mark.parametrize("path", ["/absolute/x.py", "../escape.py", "C:\\root\\x.py"])
def test_identity_rejects_non_relative_paths(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_repository_path(path)


def test_function_calls_are_attributed_to_the_enclosing_body() -> None:
    result = parse(
        "src/calls.py",
        b"def first():\n"
        b"    api.validate()\n"
        b"    def inner():\n"
        b"        nested()\n"
        b"def second():\n"
        b"    charge()\n"
        b"outside()\n",
    )
    first, inner, second = result["functions"]

    assert [function["qualified_name"] for function in result["functions"]] == [
        "first", "first.inner", "second"
    ]
    assert [call["name"] for call in first["calls"]] == ["validate"]
    assert first["calls"][0]["syntax"] == "api.validate"
    assert first["calls"][0]["resolution"] == "unresolved"
    assert [call["name"] for call in inner["calls"]] == ["nested"]
    assert [call["name"] for call in second["calls"]] == ["charge"]
    assert [call["name"] for call in result["unattributed_calls"]] == ["outside"]
    assert result["outgoing_calls"] == ["validate", "nested", "charge", "outside"]


def test_anonymous_callback_call_is_not_assigned_to_outer_function() -> None:
    result = parse(
        "src/callback.js",
        b"function outer() { run(() => hidden()); visible(); }\n",
    )
    outer = result["functions"][0]

    assert [call["name"] for call in outer["calls"]] == ["run", "visible"]
    assert [call["name"] for call in result["unattributed_calls"]] == ["hidden"]


def test_go_function_literal_call_is_not_assigned_to_outer_function() -> None:
    result = parse(
        "src/callback.go",
        b"package p\nfunc Outer() { f := func() { hidden() }; visible(); _ = f }\n",
    )

    assert [call["name"] for call in result["functions"][0]["calls"]] == [
        "visible"
    ]
    assert [call["name"] for call in result["unattributed_calls"]] == [
        "hidden"
    ]


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
    function = result["functions"][0]

    assert function["qualified_name"] == expected_qualified
    assert function["entity_id"].startswith("fn:v1:")
    assert function["raw_code"]
    assert function["start_line"] >= 1
    assert function["end_line"] >= function["start_line"]
    assert [call["name"] for call in function["calls"]] == ["g"]
