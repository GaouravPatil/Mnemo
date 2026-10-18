from mnemo.extract import validate_llm_unit
from mnemo.units import attr_keys, classify, compress, exact_tokens, split_atomic


def test_exact_tokens_capture_values():
    text = "Set MAX_RETRIES=5, timeout 30s, port 8081, version v2.4.1, file /etc/app.yaml, id LEDGER-142"
    tokens = exact_tokens(text)
    for want in ["MAX_RETRIES", "30s", "8081", "v2.4.1", "/etc/app.yaml", "LEDGER-142"]:
        assert want in tokens, want


def test_compress_keeps_values_and_negation():
    out = compress("Basically, I think the service must never log API_KEY tokens", "constraint")
    assert "never" in out
    assert exact_tokens("must never log API_KEY tokens") <= exact_tokens(out) | {
        "must",
        "never",
        "log",
        "API_KEY",
        "tokens",
    }
    out2 = compress("The timeout is not 30s anymore, it is 60s", "fact")
    assert "not" in out2
    assert "60s" in out2


def test_compress_strips_filler_and_copula():
    assert compress("Well, the cache TTL is 300s", "fact") == "cache TTL 300s"
    assert compress("We decided to use PostgreSQL 15.2", "decision") == "use PostgreSQL 15.2"


def test_classify_types():
    assert classify("Use Redis for sessions") == "fact"
    assert classify("We decided to use Redis for sessions") == "decision"
    assert classify("You must never log secrets") == "constraint"
    assert classify("Should we migrate to Redis?") == "question"
    assert classify("The migration is blocked on the cert") == "state"
    assert classify("TODO: write the migration script") == "todo"


def test_split_atomic_splits_multi_fact_sentence():
    text = "auth service runs on port 8081 and timeout 30s"
    parts = split_atomic(text)
    assert parts == ["auth service runs on port 8081", "timeout 30s"]


def test_split_atomic_rejects_lists_and_fragments():
    assert split_atomic("supports Python and Go and Rust") == ["supports Python and Go and Rust"]
    assert split_atomic("created users and orders tables") == ["created users and orders tables"]


def test_attr_keys():
    attr = attr_keys("timeout 60s and port 8443")
    assert attr["timeout"] == ["60s"]
    assert attr["port"] == ["8443"]


def test_validate_llm_unit_blocks_invention():
    source = "The timeout is 30s on port 8081"
    assert validate_llm_unit("timeout 30s", source)
    assert validate_llm_unit("the timeout is 30s", source)
    assert not validate_llm_unit("timeout 30 into port", source)
    assert not validate_llm_unit("timeout is 45s", source)
    assert not validate_llm_unit("postgres is 15.2", source)
    assert not validate_llm_unit("completely unrelated vegetables", source)
