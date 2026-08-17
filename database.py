import os
from collections.abc import Iterable
from typing import Any

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase


load_dotenv()


UPSERT_CALL_GRAPH = """
UNWIND $functions AS function
MERGE (f:Function {id: function.id})
SET f.name = function.name,
    f.qualified_name = function.qualified_name,
    f.file = function.file,
    f.line = function.line,
    f.external = function.external
WITH count(*) AS ignored
UNWIND $calls AS call
MATCH (caller:Function {id: call.caller_id})
MATCH (callee:Function {id: call.callee_id})
MERGE (caller)-[r:CALLS]->(callee)
SET r.locations = call.locations,
    r.count = size(call.locations)
"""

GET_FUNCTION_CALLERS = """
MATCH (caller:Function)-[:CALLS]->(callee:Function)
WHERE callee.name = $function_name
   OR callee.qualified_name = $function_name
RETURN DISTINCT caller.id AS id,
       caller.name AS name,
       caller.qualified_name AS qualified_name,
       caller.file AS file,
       caller.line AS line
ORDER BY caller.file, caller.line, caller.qualified_name
"""


class Neo4jDatabase:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self._driver: Driver = GraphDatabase.driver(
            uri or os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                user or os.getenv("NEO4J_USER", "neo4j"),
                password or self._required_env("NEO4J_PASSWORD"),
            ),
        )

    @staticmethod
    def _required_env(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise ValueError(f"{name} must be set")
        return value

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def write_call_graph(
        self,
        functions: Iterable[dict[str, Any]],
        calls: Iterable[dict[str, Any]],
    ) -> None:
        with self._driver.session(database=self.database) as session:
            session.run(
                UPSERT_CALL_GRAPH,
                functions=list(functions),
                calls=list(calls),
            ).consume()

    def get_function_callers(self, function_name: str) -> list[dict[str, Any]]:
        with self._driver.session(database=self.database) as session:
            result = session.run(
                GET_FUNCTION_CALLERS,
                function_name=function_name,
            )
            return [record.data() for record in result]

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
