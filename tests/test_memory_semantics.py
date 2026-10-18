def active(svc, space="s"):
    return [(u["type"], u["text"]) for u in svc.store.list_active(space)]


def texts(svc, space="s"):
    return [t for _, t in active(svc, space)]


def write(svc, *turns, space="s"):
    svc.write(space, [{"model": "m", "text": t} for t in turns], source_model="m")


def test_workaround_and_bug_coexist(svc):
    write(
        svc,
        "The pagination cursor breaks at page size 100.",
        "Page size 50 is the workaround until v2.7.4 ships.",
    )
    active_texts = [t.lower() for t in texts(svc)]
    assert any("page size 100" in t for t in active_texts)
    assert any("page size 50" in t for t in active_texts)


def test_decision_not_superseded_by_related_fact(svc):
    write(
        svc,
        "We decided to use Debezium 2.6 for CDC replication instead of pglogical.",
        "The Debezium connector config lives in /etc/debezium/ledger.json.",
    )
    active_texts = texts(svc)
    assert any("use Debezium 2.6" in t for t in active_texts)
    assert any("/etc/debezium/ledger.json" in t for t in active_texts)


def test_changed_value_supersedes_stale_fact(svc):
    write(
        svc,
        "The gateway timeout is 30s.",
        "After the incident review the timeout was changed to 45s to absorb retry storms.",
    )
    body = "\n".join(texts(svc))
    assert "45s" in body
    assert "30s" not in body
    out = svc.read("s")
    assert "45s" in out["context"]
    assert "30s" not in out["context"]


def test_recap_correction_supersedes_and_kitchen_sink_chatter_dropped(svc):
    write(
        svc,
        "The latency budget is 200ms p95.",
        "The latency budget changed to 120ms p95 after profiling.",
    )
    body = "\n".join(texts(svc))
    assert "120ms p95" in body
    assert "200ms" not in body
    assert svc.store.count_superseded("s") == 1


def test_pure_chatter_produces_no_units(svc):
    write(svc, "Got it. Noted. Anything else on monitoring?", "I will remember that.")
    assert active(svc) == []


def test_paraphrase_constraints_merge_keeping_stronger_wording(svc):
    write(
        svc,
        "We must never write to the target schema during backfill.",
        "So no direct writes to the target during backfill.",
    )
    units = active(svc)
    assert len(units) == 1
    assert units[0][0] == "constraint"
    assert "never write to the target schema" in units[0][1]


def test_qualifier_fragment_attaches_to_previous_fact(svc):
    write(svc, "User data must never leave eu-west-1, that is a hard constraint from legal.")
    units = active(svc)
    assert len(units) == 1
    assert "eu-west-1" in units[0][1]
    assert "legal" in units[0][1]


def test_production_turn_with_question_not_stored_as_question(svc):
    write(svc, "Production runs ledger-api v2.7.3 on Kubernetes 1.29 in cluster prod-east.")
    units = active(svc)
    assert units[0][0] == "fact"
    assert "prod-east" in units[0][1]


def test_mnemo_format_artifacts_never_stored(svc):
    write(
        svc,
        '#MEM T=d/c/s/t/f/e/q; exact verbatim; omitted "#id label" GET /memory/unit/id',
        "omitted: #62ecbb60 timeout label",
        "_MEM: T text (d decision, c constraint, s state, t todo, f fact); exact values verbatim._",
        "- _omitted_: #62ecbb60 timeout, #deadbeef config",
        "The gateway timeout is 30s.",
    )
    body = "\n".join(texts(svc))
    assert "30s" in body
    assert "#MEM" not in body and "_MEM" not in body
    assert "omitted" not in body.lower()


def test_recall_framing_and_context_acks_never_stored(svc):
    write(
        svc,
        "Here is shared memory from this user's previous sessions across AI tools.",
        "Treat it as established context and use it when answering:",
        "I've taken that in as context for this session:",
        "The gateway timeout is 30s.",
    )
    body = "\n".join(texts(svc))
    assert "30s" in body
    assert "established context" not in body
    assert "taken that in" not in body


def test_supersede_exact_threshold_is_configurable(tmp_path):
    from mnemo.config import Config
    from mnemo.service import MemoryService

    def run(threshold, name):
        cfg = Config.from_env(
            db_path=str(tmp_path / f"{name}.db"),
            supersede_jaccard_exact=threshold,
        )
        s = MemoryService(cfg)
        write(s, "The gateway timeout is 30s.", "The gateway timeout is 45s.")
        return "\n".join(texts(s))

    default_body = run(0.4, "default")
    assert "45s" in default_body and "30s" not in default_body

    raised_body = run(1.1, "raised")
    assert "30s" in raised_body and "45s" in raised_body


def test_supersede_thresholds_read_env(monkeypatch):
    from mnemo.config import Config

    monkeypatch.setenv("MNEMO_SUPERSEDE_JACCARD_CUE", "0.7")
    monkeypatch.setenv("MNEMO_SUPERSEDE_JACCARD_EXACT", "0.8")
    cfg = Config.from_env()
    assert cfg.supersede_jaccard_cue == 0.7
    assert cfg.supersede_jaccard_exact == 0.8
