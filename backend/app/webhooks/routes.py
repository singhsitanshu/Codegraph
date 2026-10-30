import logging
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import JSONResponse

from app.webhooks.github_events import parse_push_change_set
from app.webhooks.pipeline import process_push_change_set
from app.webhooks.signature import verify_github_signature


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
    # The handler only runs once the signature dependency has accepted the body.
    dependencies=[Depends(verify_github_signature)],
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Validate a signed GitHub push and apply its changes after the response."""

    event_type = request.headers.get("X-GitHub-Event", "unknown").strip().lower()
    try:
        payload: Any = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook body must contain valid JSON",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook JSON payload must be an object",
        )

    # GitHub records non-2xx responses as failed deliveries, so signed events
    # that cannot be processed are acknowledged as ignored, not rejected.
    if event_type != "push":
        return _ignored(f"'{event_type}' events are not processed")
    try:
        change_set = parse_push_change_set(payload)
    except ValueError as exc:
        logger.warning("Ignoring unsupported push payload: %s", exc)
        return _ignored("push event does not contain a complete supported change set")
    if not change_set.updated_paths and not change_set.deleted_paths:
        return _ignored("no supported source files changed")

    background_tasks.add_task(process_push_change_set, change_set)
    logger.info(
        "Accepted push to %s for background processing",
        change_set.repository.full_name,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "accepted",
            "message": "Webhook processing started in background",
        },
    )


def _ignored(reason: str) -> JSONResponse:
    """Acknowledge a signed webhook that will not change any graph."""

    logger.info("Ignoring GitHub webhook: %s", reason)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"status": "ignored", "reason": reason},
    )
