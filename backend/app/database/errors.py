"""Client-facing descriptions of Neo4j failures."""

import logging
from dataclasses import dataclass

from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable


logger = logging.getLogger(__name__)

NEO4J_ERRORS = (Neo4jError, ServiceUnavailable)
"""Exceptions raised when Neo4j rejects or cannot serve a request."""


def is_neo4j_unavailable(exc: Neo4jError | ServiceUnavailable) -> bool:
    """Return whether ``exc`` means Neo4j cannot be used at all right now."""

    return isinstance(exc, (AuthError, ServiceUnavailable))


@dataclass(frozen=True)
class Neo4jFailureDetails:
    """Client-facing messages for one operation's Neo4j failure modes."""

    authentication: str
    unavailable: str
    failure: str

    def describe(self, exc: Neo4jError | ServiceUnavailable) -> str:
        """Log ``exc`` and return the message a client should see."""

        if isinstance(exc, AuthError):
            logger.warning(self.authentication)
            return self.authentication
        if isinstance(exc, ServiceUnavailable):
            logger.warning(self.unavailable)
            return self.unavailable
        logger.exception(self.failure)
        return self.failure
