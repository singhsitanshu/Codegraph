import hashlib
import hmac

from fastapi import Header, HTTPException, Request, status

from app.config import settings


async def verify_github_signature(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> bool:
    """Validate GitHub's HMAC SHA-256 signature for the raw request body."""

    if x_hub_signature_256 is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )

    raw_body = await request.body()
    digest = hmac.new(
        key=settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    expected_signature = f"sha256={digest}"

    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub webhook signature",
        )

    return True
