HEADERS = {"X-API-Key": "test-key"}
EXT_ORIGIN = "chrome-extension://" + "a" * 32


def test_cors_preflight_allows_chrome_extension(client):
    r = client.options(
        "/memory/read",
        headers={
            "Origin": EXT_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == EXT_ORIGIN
    assert "x-api-key" in r.headers["access-control-allow-headers"].lower()


def test_cors_blocks_web_origins(client):
    r = client.options(
        "/memory/read",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )
    assert "access-control-allow-origin" not in r.headers


def test_cors_env_adds_explicit_origin(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from mnemo.api import create_app
    from mnemo.config import Config

    monkeypatch.setenv("MNEMO_CORS_ORIGINS", "https://app.example")
    cfg = Config.from_env(db_path=str(tmp_path / "cors.db"), api_key="test-key")
    c = TestClient(create_app(cfg))
    r = c.get("/health", headers={"Origin": "https://app.example"})
    assert r.headers.get("access-control-allow-origin") == "https://app.example"


def test_health_needs_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_auth_is_required(client):
    r = client.post("/memory/read", json={"space_id": "s"})
    assert r.status_code == 401
    r = client.post("/memory/read", json={"space_id": "s"}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_write_read_unit_delete_flow(client):
    w = client.post(
        "/memory/write",
        json={
            "space_id": "api-space",
            "content": "We decided to use PostgreSQL 15.2 on port 5433.",
            "source_model": "model-a",
        },
        headers=HEADERS,
    )
    assert w.status_code == 200
    written = w.json()["written"]
    assert written and "5433" in written[0]["text"]
    uid = written[0]["id"]

    r = client.post(
        "/memory/read",
        json={"space_id": "api-space", "query": "database", "max_tokens": 300},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert "PostgreSQL 15.2" in body["context"]
    assert body["tokens"] <= 300

    g = client.get(f"/memory/unit/{uid}", headers=HEADERS)
    assert g.status_code == 200
    assert "port 5433" in g.json()["source_text"]
    assert g.json()["source_model"] == "model-a"

    d = client.delete(f"/memory/unit/{uid}", headers=HEADERS)
    assert d.status_code == 200
    assert client.get(f"/memory/unit/{uid}", headers=HEADERS).status_code == 404
    r2 = client.post("/memory/read", json={"space_id": "api-space", "max_tokens": 300}, headers=HEADERS)
    assert "5433" not in r2.json()["context"]


def test_unknown_unit_404(client):
    assert client.get("/memory/unit/nope", headers=HEADERS).status_code == 404
    assert client.delete("/memory/unit/nope", headers=HEADERS).status_code == 404


def test_invalid_requests_422(client):
    assert (
        client.post("/memory/read", json={"space_id": "s", "max_tokens": 0}, headers=HEADERS).status_code == 422
    )
    assert (
        client.post(
            "/memory/read", json={"space_id": "s", "format": "yaml"}, headers=HEADERS
        ).status_code
        == 422
    )


def test_cross_model_handoff_via_api(client):
    client.post(
        "/memory/write",
        json={
            "space_id": "handoff",
            "source_model": "claude-sonnet-4",
            "content": [
                {"model": "claude-sonnet-4", "text": "The migration deadline is 2026-05-01."},
                {"model": "claude-sonnet-4", "text": "We decided to cut over behind feature flag FF_CUTOVER."},
                {"model": "claude-sonnet-4", "text": "The rollback script is /opt/rollback.sh."},
            ],
        },
        headers=HEADERS,
    )
    r = client.post(
        "/memory/read",
        json={
            "space_id": "handoff",
            "query": "how do I roll back the migration?",
            "max_tokens": 400,
            "target_model": "gpt-4o",
        },
        headers=HEADERS,
    )
    body = r.json()
    assert "/opt/rollback.sh" in body["context"]
    assert "2026-05-01" in body["context"]
    assert "FF_CUTOVER" in body["context"]
    assert body["tokenizer"] == "o200k_base"
