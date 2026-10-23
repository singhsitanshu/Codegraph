"""LLM-generated architectural labels for Leiden communities."""

import asyncio
import json
import logging
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, create_model, field_validator

from app.config import settings
from app.db import get_neo4j_driver


logger = logging.getLogger(__name__)
COMMUNITY_LABEL_MODEL = "gpt-4o-mini"
MAX_CONCURRENT_COMMUNITY_LABELS = 4
COMMUNITY_LABEL_BATCH_SIZE = 8
MIN_LABELED_COMMUNITY_SIZE = 3
UNGROUPED_COMMUNITY_ID = -1
UNGROUPED_COMMUNITY_NAME = "Ungrouped"
UNGROUPED_COMMUNITY_DESCRIPTION = (
    f"Functions whose detected community had fewer than "
    f"{MIN_LABELED_COMMUNITY_SIZE} members; they do not form a subsystem."
)
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
     count(f) AS function_count,
     collect(coalesce(f.qualified_name, f.name))[..15] AS func_names,
     collect(DISTINCT f.file_path)[..5] AS file_paths
RETURN comm_id, function_count, func_names, file_paths
ORDER BY comm_id
"""

UNGROUP_SMALL_COMMUNITIES_QUERY = """
MATCH (f:Function {repo_name: $repo_name})
WHERE f.leiden_community IN $community_ids
SET f.leiden_community = $ungrouped_id
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


def _community_size(record: dict[str, Any]) -> int:
    size = record.get("function_count")
    if isinstance(size, int) and not isinstance(size, bool):
        return size
    return len(_string_list(record.get("func_names")))


async def _generate_community_labels(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Required schema keys bind each result to its input. Asking the model to
    # repeat ids in a list allowed omitted/duplicate ids despite valid JSON.
    response_type = create_model(
        "CommunityLabels",
        **{f"community_{record['comm_id']}": (CommunityLabel, ...) for record in records},
    )
    completion = await _get_community_label_client().beta.chat.completions.parse(
        model=COMMUNITY_LABEL_MODEL,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": COMMUNITY_LABEL_SYSTEM_PROMPT +
                " Label each community independently under its supplied key.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    [
                        {
                            "key": f"community_{record['comm_id']}",
                            "file_paths": _string_list(record.get("file_paths")),
                            "function_names": _string_list(record.get("func_names")),
                        }
                        for record in records
                    ]
                ),
            },
        ],
        response_format=response_type,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        refusal = message.refusal or "model returned no structured label"
        raise RuntimeError(f"Unable to label community: {refusal}")
    labels = []
    for record in records:
        label = getattr(message.parsed, f"community_{record['comm_id']}", None)
        if not isinstance(label, CommunityLabel):
            raise RuntimeError("Community label response is missing a required key")
        labels.append({"id": record["comm_id"], **label.model_dump()})
    return labels


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

    records = [record for record in records if isinstance(record.get("comm_id"), int)]
    # Tiny clusters carry no architectural signal and would each cost model
    # tokens, so they are pooled into one unlabeled community.
    small_community_ids = [
        record["comm_id"]
        for record in records
        if _community_size(record) < MIN_LABELED_COMMUNITY_SIZE
    ]
    small_ids = set(small_community_ids)
    model_records = [record for record in records if record["comm_id"] not in small_ids]
    batches = [
        model_records[offset:offset + COMMUNITY_LABEL_BATCH_SIZE]
        for offset in range(0, len(model_records), COMMUNITY_LABEL_BATCH_SIZE)
    ]
    labels_by_id: dict[int, dict[str, Any]] = {}
    for offset in range(0, len(batches), MAX_CONCURRENT_COMMUNITY_LABELS):
        tasks = [
            asyncio.create_task(_generate_community_labels(batch))
            for batch in batches[offset:offset + MAX_CONCURRENT_COMMUNITY_LABELS]
        ]
        try:
            for labels in await asyncio.gather(*tasks):
                labels_by_id.update({label["id"]: label for label in labels})
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    communities = [labels_by_id[record["comm_id"]] for record in model_records]
    if small_community_ids:
        communities.append(
            {
                "id": UNGROUPED_COMMUNITY_ID,
                "name": UNGROUPED_COMMUNITY_NAME,
                "description": UNGROUPED_COMMUNITY_DESCRIPTION,
            }
        )

    async with driver.session() as session:

        async def replace_communities(transaction: Any) -> None:
            deleted = await transaction.run(
                DELETE_COMMUNITIES_QUERY,
                repo_name=normalized_repo_name,
            )
            await deleted.consume()
            if small_community_ids:
                ungrouped = await transaction.run(
                    UNGROUP_SMALL_COMMUNITIES_QUERY,
                    repo_name=normalized_repo_name,
                    community_ids=small_community_ids,
                    ungrouped_id=UNGROUPED_COMMUNITY_ID,
                )
                await ungrouped.consume()
            if communities:
                stored = await transaction.run(
                    STORE_COMMUNITIES_QUERY,
                    repo_name=normalized_repo_name,
                    communities=communities,
                )
                await stored.consume()

        await session.execute_write(replace_communities)

    logger.info(
        "Stored %d architectural community label(s) for %s with %s; "
        "%d community(ies) under %d functions grouped as %s",
        len(model_records),
        normalized_repo_name,
        COMMUNITY_LABEL_MODEL,
        len(small_community_ids),
        MIN_LABELED_COMMUNITY_SIZE,
        UNGROUPED_COMMUNITY_NAME,
    )
    return communities
