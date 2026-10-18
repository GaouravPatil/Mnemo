from mnemo.units import content_words, exact_tokens

CONVERSATION = [
    ("claude-sonnet-4", "Our repo is github.com/acme/ledger, backend is Django 4.2.3."),
    ("gpt-4o", "Noted. The database setup matters a lot."),
    ("claude-sonnet-4", "We decided to use PostgreSQL 15.2 at db.internal:5432 for the ledger service."),
    ("gpt-4o", "Understood. I will remember that."),
    (
        "claude-sonnet-4",
        "The API port was changed to 8081, but wait: correction, the API port is now 8443 and the timeout is 45s.",
    ),
    ("gpt-4o", "Noted. The config lives in /etc/ledger/app.yaml and MAX_RETRIES is 5."),
    (
        "claude-sonnet-4",
        "Ticket LEDGER-142 tracks the TLS work; it is currently blocked on the cert rotation scheduled 2026-03-15.",
    ),
    ("gpt-4o", "Basically the cache TTL is 300s on Redis 7.2.4."),
    ("claude-sonnet-4", "Yes, the cache TTL is 300s on Redis 7.2.4."),
]

CRITICAL = [
    "github.com/acme/ledger",
    "Django 4.2.3",
    "PostgreSQL 15.2",
    "db.internal",
    "5432",
    "8443",
    "45s",
    "/etc/ledger/app.yaml",
    "MAX_RETRIES",
    "LEDGER-142",
    "2026-03-15",
    "300s",
    "Redis 7.2.4",
]


def write_conversation(svc, space="acme", model="claude-sonnet-4"):
    body = [{"model": m, "text": t} for m, t in CONVERSATION]
    return svc.write(space, body, source_model=model)


def test_all_critical_values_retrievable_exact(svc):
    write_conversation(svc)
    out = svc.read("acme", max_tokens=2000)
    ctx = out["context"]
    for fact in CRITICAL:
        assert fact in ctx, f"missing exact fact: {fact}"
    assert out["stats"]["units_omitted"] == 0


def test_superseded_fact_excluded_by_default_but_recoverable(svc):
    write_conversation(svc)
    out = svc.read("acme", max_tokens=2000)
    assert "8081" not in out["context"]
    assert "8443" in out["context"]

    full = svc.read("acme", max_tokens=2000, include_superseded=True)
    assert "8081" in full["context"]
    assert full["stats"]["superseded_excluded"] == 0

    assert svc.read("acme", max_tokens=2000)["stats"]["superseded_excluded"] >= 1


def test_duplicate_fact_stored_and_returned_once(svc):
    write_conversation(svc)
    out = svc.read("acme", max_tokens=2000)
    assert out["context"].count("cache TTL 300s") == 1
    assert 5 <= out["stats"]["units_total"] <= 12
    assert "matters a lot" not in out["context"]
    assert "remember" not in out["context"]


def test_superseded_unit_detail_keeps_source(svc):
    result = write_conversation(svc)
    statuses = {w["text"]: w for w in result["written"]}
    old = next(w for w in result["written"] if "8081" in w["text"])
    detail = svc.get_unit(old["id"])
    assert "8081" in detail["text"]
    assert detail["superseded_by"]
    assert "8081" in detail["source_text"]
    assert "8081" in detail["write"]["content"]
    assert detail["version"] >= 1
    assert any(h["relation"] == "replaced_by" for h in detail["history"])
    assert statuses  # written entries visible in response


def test_no_hallucination_words_come_only_from_source(svc):
    write_conversation(svc)
    source_words = set()
    source_exact = set()
    for _, text in CONVERSATION:
        source_words |= content_words(text)
        source_exact |= exact_tokens(text)
    out = svc.read("acme", max_tokens=2000)
    body = [ln for ln in out["context"].splitlines() if not ln.startswith("#")]
    assert body
    for line in body:
        assert exact_tokens(line) <= source_exact, line
        assert content_words(line) <= source_words, line


def test_negations_and_constraints_survive(svc):
    svc.write(
        "acme",
        "You must never log API tokens. Do not use eval in this codebase.",
        source_model="gpt-4o",
    )
    ctx = svc.read("acme", max_tokens=400)["context"]
    assert "never log API tokens" in ctx
    assert "not use eval" in ctx


def test_open_questions_classified_and_kept(svc):
    svc.write("acme", "Should we shard the ledger table by account_id?", source_model="gpt-4o")
    out = svc.read("acme", max_tokens=400)
    assert any(u["type"] == "question" for u in out["omitted"]) or "shard the ledger table" in out["context"]
