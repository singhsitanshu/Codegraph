"""LLM-generated architectural labels for Leiden communities."""

import json
import logging
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.db import get_neo4j_driver


logger = logging.getLogger(__name__)
COMMUNITY_LABEL_MODEL = "gpt-4o-mini"
COMMUNITY_LABEL_SYSTEM_PROMPT = (
    "You are a senior software architect analyzing code clusters. Given a "
    "list of function names and file paths from a code repository module, "
    "infer the architectural purpose of this cluster. Return a concise module "
    "name and a one-sentence description."
)

FETCH_COMMUNITIES_QUERY = """
MATCH (f:Function {repo_name: $repo_name})
WHERE f.leiden_community IS NOT NULL
WITH f.leiden_community AS comm_id,
     collect(f.name)[..15] AS func_names,
     collect(DISTINCT f.file_path)[..5] AS file_paths
RETURN comm_id, func_names, file_paths
ORDER BY comm_id
"""

DELETE_COMMUNITIES_QUERY = """
MATCH (c:Community {repo_name: $repo_name})
DETACH DELETE c
"""

STORE_COMMUNITIES_QUERY = """
UNWIND $communities AS comm
MERGE (c:Community {repo_name: $repo_name, community_id: comm.id})
SET c.name = comm.name,
    c.description = comm.description
WITH c, comm
MATCH (f:Function {
    repo_name: $repo_name,
    leiden_community: comm.id
})
MERGE (f)-[:IN_COMMUNITY]->(c)
"""


class CommunityLabel(BaseModel):
    """Structured architectural summary returned by the labeling model."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("community labels must not be blank")
        return stripped


@lru_cache(maxsize=1)
def _get_community_label_client() -> AsyncOpenAI:
    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to label communities")
    return AsyncOpenAI(api_key=api_key)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


async def _generate_community_label(
    function_names: list[str],
    file_paths: list[str],
) -> CommunityLabel:
    completion = await _get_community_label_client().beta.chat.completions.parse(
        model=COMMUNITY_LABEL_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": COMMUNITY_LABEL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "file_paths": file_paths,
                        "function_names": function_names,
                    }
                ),
            },
        ],
        response_format=CommunityLabel,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        refusal = message.refusal or "model returned no structured label"
        raise RuntimeError(f"Unable to label community: {refusal}")
    return message.parsed


async def label_and_store_communities(
    repo_name: str,
) -> list[dict[str, Any]]:
    """Generate and atomically persist labels for one repository's clusters."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")

    driver = get_neo4j_driver()
    async with driver.session() as session:
        result = await session.run(
            FETCH_COMMUNITIES_QUERY,
            repo_name=normalized_repo_name,
        )
        records = await result.data()

    communities: list[dict[str, Any]] = []
    for record in records:
        community_id = record.get("comm_id")
        if not isinstance(community_id, int):
            continue
        label = await _generate_community_label(
            _string_list(record.get("func_names")),
            _string_list(record.get("file_paths")),
        )
        communities.append(
            {
                "id": community_id,
                "name": label.name,
                "description": label.description,
            }
        )

    async with driver.session() as session:

        async def replace_communities(transaction: Any) -> None:
            deleted = await transaction.run(
                DELETE_COMMUNITIES_QUERY,
                repo_name=normalized_repo_name,
            )
            await deleted.consume()
            if communities:
                stored = await transaction.run(
                    STORE_COMMUNITIES_QUERY,
                    repo_name=normalized_repo_name,
                    communities=communities,
                )
                await stored.consume()

        await session.execute_write(replace_communities)

    logger.info(
        "Stored %d architectural community label(s) for %s with %s",
        len(communities),
        normalized_repo_name,
        COMMUNITY_LABEL_MODEL,
    )
    return communities
