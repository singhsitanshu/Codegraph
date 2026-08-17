import logging
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import JSONResponse

from app.api.dependencies import verify_github_signature
from app.services.pipeline import process_github_event


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    signature_verified: Annotated[bool, Depends(verify_github_signature)],
) -> JSONResponse:
    """Acknowledge a verified GitHub webhook and process it after the response."""

    # FastAPI resolves the dependency before entering this handler. Keeping the
    # value explicit makes that security boundary visible and type checked.
    if not signature_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub signature verification failed",
        )

    event_type = request.headers.get("X-GitHub-Event", "unknown")
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

    background_tasks.add_task(process_github_event, payload, event_type)
    logger.info("Accepted GitHub event '%s' for background processing", event_type)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "accepted",
            "message": "Webhook processing started in background",
        },
    )
