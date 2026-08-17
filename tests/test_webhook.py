import hashlib
import hmac

from fastapi.testclient import TestClient

from app.main import app, settings


client = TestClient(app)


def signed_headers(body: bytes, event: str = "push") -> dict[str, str]:
    digest = hmac.new(
        settings.github_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return {
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": f"sha256={digest}",
        "Content-Type": "application/json",
    }


def test_push_webhook(caplog) -> None:
    body = b'{"commits":[{"added":["a.py"],"modified":["b.py"],"removed":["c.py"]}]}'
    response = client.post("/webhook/github", content=body, headers=signed_headers(body))

    assert response.status_code == 200
    assert response.json()["file_count"] == 3
    assert "a.py" in caplog.text
    assert "b.py" in caplog.text
    assert "c.py" in caplog.text


def test_rejects_bad_signature() -> None:
    response = client.post(
        "/webhook/github",
        content=b"{}",
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=bad"},
    )
    assert response.status_code == 401
