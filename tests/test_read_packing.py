import json

FACTS = [
    "You must never commit secrets to the repo.",
    "We decided to shard the ledger table by account_id.",
    "The deployment uses Kubernetes 1.29 on cluster prod-east.",
    "The queue runs on RabbitMQ 3.13.7 with 8 consumers.",
    "The staging database is at db.staging:5432.",
    "Billing exports land in /var/exports/billing each night.",
    "The retry window is 45s for webhook deliveries.",
    "MAX_UPLOAD_MB is set to 25 in the gateway config.",
    "The legacy importer was decommissioned on 2026-01-30.",
    "Support tickets are triaged in REV-8801.",
    "The frontend caches assets with a 12h TTL.",
    "Ops approved the failover drill for 2026-04-12.",
    "The audit log stream is append-only.",
    "Rate limiting uses a 1000 rps budget per tenant.",
    "The canary weight is 5 percent during rollout.",
]


def seed(svc, space="pack"):
    svc.write(space, [{"model": "seed", "text": f} for f in FACTS], source_model="seed")


def test_budget_never_exceeded(svc):
    seed(svc)
    for budget in [1, 3, 8, 15, 30, 60, 120, 250, 500, 1000]:
        out = svc.read("pack", max_tokens=budget, target_model="gpt-4o")
        counter = svc.counter("gpt-4o")
        assert out["tokens"] == counter.count(out["context"])
        assert out["tokens"] <= budget, f"budget {budget} exceeded: {out['tokens']}"


def test_omitted_index_reports_dropped_units(svc):
    seed(svc)
    out = svc.read("pack", max_tokens=140)
    assert out["stats"]["units_omitted"] > 0
    assert len(out["omitted"]) == out["stats"]["units_omitted"]
    ids = {o["id"] for o in out["omitted"]}
    assert "omitted:" in out["context"]
    indexed = "\n".join(ln for ln in out["context"].splitlines() if not ln.startswith("#MEM"))
    assert any(f"#{oid}" in indexed for oid in ids) or "units" in indexed


def test_json_format_is_minimal_and_parseable(svc):
    seed(svc)
    out = svc.read("pack", max_tokens=800, format="json")
    doc = json.loads(out["context"])
    assert doc["v"] == 1
    assert isinstance(doc["u"], list) and doc["u"]
    assert isinstance(doc["h"], str)
    assert ", " not in out["context"]
    assert ": " not in out["context"]
    lines = doc["u"]
    assert all(len(item) == 2 for item in lines)


def test_markdown_format(svc):
    seed(svc)
    out = svc.read("pack", max_tokens=800, format="markdown")
    assert "- **" in out["context"]


def test_ranking_query_relevance(svc):
    seed(svc)
    out = svc.read("pack", query="which message queue consumers are running?", max_tokens=800)
    lines = [ln for ln in out["context"].splitlines() if not ln.startswith("#")]
    assert "RabbitMQ 3.13.7" in lines[0]


def test_type_priority_without_query(svc):
    seed(svc)
    out = svc.read("pack", max_tokens=800)
    lines = [ln for ln in out["context"].splitlines() if not ln.startswith("#")]
    assert lines[0].startswith("c ")
    assert lines[1].startswith("d ")


def test_tokenizer_follows_target_model(svc):
    seed(svc)
    assert svc.read("pack", max_tokens=100, target_model="gpt-4o")["tokenizer"] == "o200k_base"
    assert svc.read("pack", max_tokens=100, target_model="claude-sonnet-4")["tokenizer"] == "cl100k_base"
    assert svc.read("pack", max_tokens=100)["tokenizer"] == "cl100k_base"


def test_types_filter(svc):
    seed(svc)
    out = svc.read("pack", max_tokens=800, types=["constraint"])
    lines = [ln for ln in out["context"].splitlines() if not ln.startswith("#")]
    assert len(lines) == 1
    assert "never commit secrets" in lines[0]
