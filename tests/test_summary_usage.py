from mnemo.translate import needs_translation

HEADERS = {"X-API-Key": "test-key"}


def test_needs_translation_detects_non_english():
    assert needs_translation("यह एक परीक्षण है।")
    assert needs_translation("El servidor está en ejecución para todos.")
    assert not needs_translation("The gateway timeout is 45s.")


def test_summary_reports_counts_and_quality(client):
    client.post(
        "/memory/write",
        json={
            "space_id": "summary-space",
            "content": [
                "The gateway timeout is 45s.",
                "We decided to use PostgreSQL 15.2 on port 5433.",
                "The gateway timeout is 30s.",
            ],
        },
        headers=HEADERS,
    )
    r = client.post(
        "/memory/summary",
        json={"space_id": "summary-space", "max_tokens": 300},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]
    assert body["stats"]["units_total"] >= 1
    assert "precision_proxy" in body["quality"]
    assert "Mnemo summary: summary-space" in body["summary"]
    assert body["quality"]["exact_key_coverage"] > 0


def test_usage_report_deduplicates_by_response_id(client):
    row = {
        "model": "claude-sonnet-4-6",
        "session_id": "sess-1",
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 50,
        "response_id": "resp-1",
    }
    first = client.post(
        "/usage/report",
        json={"space_id": "usage-space", "rows": [row]},
        headers=HEADERS,
    )
    assert first.status_code == 200
    assert first.json() == {"received": 1, "inserted": 1, "deduplicated": 0}

    second = client.post(
        "/usage/report",
        json={"space_id": "usage-space", "rows": [row]},
        headers=HEADERS,
    )
    assert second.json() == {"received": 1, "inserted": 0, "deduplicated": 1}

    s = client.get("/usage/summary", params={"space_id": "usage-space"}, headers=HEADERS)
    assert s.status_code == 200
    body = s.json()
    assert body["totals"]["calls"] == 1
    assert body["totals"]["total_tokens"] == 170
    assert body["by_model"][0]["model"] == "claude-sonnet-4-6"


def test_write_language_uses_translator(svc, monkeypatch):
    class FakeTranslator:
        language = "English"

        def translate(self, text):
            return "The gateway timeout is 45s.", True

    monkeypatch.setattr("mnemo.service.get_translator", lambda cfg, language: FakeTranslator())
    out = svc.write("lang-space", "गेटवे टाइमआउट 45s है।", language="English")
    assert out["language"] == "English"
    assert out["translated"] == 1
    assert out["written"]
    assert "45s" in out["written"][0]["text"]


def test_write_language_without_llm_warns(svc):
    out = svc.write("lang-space", "The gateway timeout is 45s.", language="English")
    assert out["language"] is None
    assert out["translated"] == 0
    assert "language_warning" in out
