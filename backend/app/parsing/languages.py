"""Registry of the source languages the parser understands.

Each supported language is described by exactly one :class:`LanguageSpec`.
Supported extensions, parsers, compiled queries, parse locks and every
language-specific node type the parser inspects are derived from
:data:`LANGUAGES`, so supporting a new language means adding one entry here
plus its grammar package in ``backend/requirements.txt``.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from types import MappingProxyType

import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    """Everything the parser needs to know about one Tree-sitter grammar.

    Queries use the captures ``@name`` and ``@definition`` for function
    definitions, ``@call`` for the called name, and ``@name`` for classes.
    """

    name: str
    """Language recorded on parsed files and in function identities."""
    extensions: tuple[str, ...]
    """Lowercase file suffixes, including the leading dot."""
    grammar: Callable[[], object]
    """Returns the grammar's precompiled language pointer."""
    function_definitions_query: str
    function_calls_query: str
    class_definitions_query: str
    scope_node_types: frozenset[str]
    """Named enclosing nodes that contribute to a qualified name."""
    call_node_types: frozenset[str]
    """Nodes that represent a whole call expression."""
    anonymous_function_node_types: frozenset[str]
    """Unnamed functions whose calls are not attributed to the enclosing one."""
    assigned_function_node_types: frozenset[str] = frozenset()
    """Definitions whose parameters and body live on their ``value`` field."""
    receiver_method_node_types: frozenset[str] = frozenset()
    """Definitions qualified by the type named in their ``receiver`` field."""


PYTHON = LanguageSpec(
    name="python",
    extensions=(".py",),
    grammar=tree_sitter_python.language,
    function_definitions_query="""
(function_definition
  name: (identifier) @name) @definition
""",
    function_calls_query="""
(call
  function: (identifier) @call)

(call
  function: (attribute
    attribute: (identifier) @call))
""",
    class_definitions_query="""
(class_definition
  name: (identifier) @name)
""",
    scope_node_types=frozenset({"class_definition", "function_definition"}),
    call_node_types=frozenset({"call"}),
    anonymous_function_node_types=frozenset({"lambda"}),
)

JAVASCRIPT = LanguageSpec(
    name="javascript",
    extensions=(".js", ".jsx"),
    grammar=tree_sitter_javascript.language,
    function_definitions_query="""
(function_declaration
  name: (identifier) @name) @definition

(generator_function_declaration
  name: (identifier) @name) @definition

(method_definition
  name: (property_identifier) @name) @definition

(variable_declarator
  name: (identifier) @name
  value: [(arrow_function) (function_expression)]) @definition
""",
    function_calls_query="""
(call_expression
  function: (identifier) @call)

(call_expression
  function: (member_expression
    property: (property_identifier) @call))
""",
    class_definitions_query="""
(class_declaration
  name: (identifier) @name)
""",
    scope_node_types=frozenset(
        {
            "class_declaration",
            "function_declaration",
            "generator_function_declaration",
            "method_definition",
            "variable_declarator",
        }
    ),
    call_node_types=frozenset({"call_expression"}),
    anonymous_function_node_types=frozenset(
        {"arrow_function", "function_expression", "generator_function"}
    ),
    assigned_function_node_types=frozenset({"variable_declarator"}),
)

TYPESCRIPT = LanguageSpec(
    name="typescript",
    extensions=(".ts",),
    grammar=tree_sitter_typescript.language_typescript,
    function_definitions_query="""
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
""",
    function_calls_query="""
(call_expression
  function: (identifier) @call)

(call_expression
  function: (member_expression
    property: (property_identifier) @call))
""",
    class_definitions_query="""
(class_declaration
  name: (type_identifier) @name)

(abstract_class_declaration
  name: (type_identifier) @name)
""",
    scope_node_types=frozenset(
        {
            "class_declaration",
            "abstract_class_declaration",
            "interface_declaration",
            "internal_module",
            "function_declaration",
            "generator_function_declaration",
            "method_definition",
            "function_signature",
            "method_signature",
            "variable_declarator",
        }
    ),
    call_node_types=frozenset({"call_expression"}),
    anonymous_function_node_types=frozenset(
        {"arrow_function", "function_expression", "generator_function"}
    ),
    assigned_function_node_types=frozenset({"variable_declarator"}),
)

# TSX is TypeScript's grammar with JSX; it shares every query and node type.
TSX = replace(
    TYPESCRIPT,
    name="tsx",
    extensions=(".tsx",),
    grammar=tree_sitter_typescript.language_tsx,
)

GO = LanguageSpec(
    name="go",
    extensions=(".go",),
    grammar=tree_sitter_go.language,
    function_definitions_query="""
(function_declaration
  name: (identifier) @name) @definition

(method_declaration
  name: (field_identifier) @name) @definition
""",
    function_calls_query="""
(call_expression
  function: (identifier) @call)

(call_expression
  function: (selector_expression
    field: (field_identifier) @call))
""",
    class_definitions_query="""
(type_spec
  name: (type_identifier) @name
  type: [(struct_type) (interface_type)])
""",
    scope_node_types=frozenset({"function_declaration", "method_declaration"}),
    call_node_types=frozenset({"call_expression"}),
    anonymous_function_node_types=frozenset({"func_literal"}),
    receiver_method_node_types=frozenset({"method_declaration"}),
)

JAVA = LanguageSpec(
    name="java",
    extensions=(".java",),
    grammar=tree_sitter_java.language,
    function_definitions_query="""
(method_declaration
  name: (identifier) @name
  body: (block)) @definition

(constructor_declaration
  name: (identifier) @name
  body: (constructor_body)) @definition
""",
    function_calls_query="""
(method_invocation
  name: (identifier) @call)
""",
    class_definitions_query="""
(class_declaration
  name: (identifier) @name)
""",
    scope_node_types=frozenset(
        {
            "class_declaration",
            "interface_declaration",
            "record_declaration",
            "method_declaration",
            "constructor_declaration",
            "variable_declarator",
        }
    ),
    call_node_types=frozenset({"method_invocation"}),
    anonymous_function_node_types=frozenset({"lambda_expression"}),
)

LANGUAGES: tuple[LanguageSpec, ...] = (PYTHON, JAVASCRIPT, TYPESCRIPT, TSX, GO, JAVA)

LANGUAGE_BY_EXTENSION: MappingProxyType[str, LanguageSpec] = MappingProxyType(
    {extension: spec for spec in LANGUAGES for extension in spec.extensions}
)
if len({spec.name for spec in LANGUAGES}) != len(LANGUAGES) or len(
    LANGUAGE_BY_EXTENSION
) != sum(len(spec.extensions) for spec in LANGUAGES):
    raise RuntimeError("Language names and extensions must be unique")

SUPPORTED_EXTENSIONS: dict[str, str] = {
    extension: spec.name for extension, spec in LANGUAGE_BY_EXTENSION.items()
}
