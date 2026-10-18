import os
import sys
import tempfile
import time

from mnemo.config import Config
from mnemo.service import MemoryService
from mnemo.tokens import TokenCounter

BUDGET = 600
TIGHT_BUDGET = 150

SAMPLES = [
    {
        "name": "api-incident",
        "space": "bench-api",
        "task": "What do I need to know to fix the pagination bug and ship the hotfix?",
        "conversation": [
            ("claude-sonnet-4", "Hey, quick context dump for the pagination bug. Our repo is github.com/acme/ledger and the API gateway service is ledger-api."),
            ("gpt-4o", "Got it. I will remember that. What version runs in production right now?"),
            ("claudalipnee-sonnet-4", "Production runs ledger-api v2.7.3 on Kubernetes 1.29 in cluster prod-east."),
            ("gpt-4o", "Okay, thanks. What exactly is failing?"),
            ("claude-sonnet-4", "Well, basically the pagination cursor breaks when page size is 100 and we see error code PGR-4091 in the gateway logs."),
            ("gpt-4o", "Noted. Do we know which file is involved?"),
            ("claude-sonnet-4", "I think the bug is in services/pagination.py around the cursor encoding logic."),
            ("gpt-4o", "Understood. There is a workaround for customers: set page size to 50."),
            ("claude-sonnet-4", "Yes, page size 50 works as the workaround until v2.7.4 ships."),
            ("gpt-4o", "Thanks for the context. Let me make sure I have the picture right: the repo is github.com/acme/ledger, the affected service is ledger-api, and production is on v2.7.3 in prod-east. The cursor bug only reproduces at page size 100, correct?"),
            ("claude-sonnet-4", "That is right. To add detail, the cursor encoding base64-encodes the last row sort key, and at exactly 100 items the payload crosses the 4 KB boundary and the decoder returns a malformed cursor."),
            ("gpt-4o", "Makes sense. So clients hitting page size 100 see PGR-4091, and the temporary workaround is page size 50. I will remember the workaround is temporary until v2.7.4 ships."),
            ("claude-sonnet-4", "Correct. For completeness, the gateway timeout was 30s, and after the incident review the timeout was changed to 45s to absorb retry storms."),
            ("gpt-4o", "Got it. Noted. Anything else on monitoring?"),
            ("claude-sonnet-4", "On monitoring, we watch ledger_api_p99_latency_ms on the grafana.internal/d/ledger-api dashboard, and the alert threshold is 800ms over 5 minutes."),
            ("gpt-4o", "Okay. I will remember the dashboard and the alert threshold. What about the deploy process for the hotfix?"),
            ("claude-sonnet-4", "For deploys, hotfixes need ops approval and we must never skip the canary stage. The canary runs for 20 minutes before full rollout."),
            ("gpt-4o", "Understood. To recap ownership: Priya owns the cursor fix in LEDGER-142, the hotfix review is scheduled 2026-03-15, and the config file to check is /etc/ledger-api/gateway.yaml."),
            ("claude-sonnet-4", "That recap is accurate. One more thing: the gateway config file /etc/ledger-api/gateway.yaml contains MAX_PAGE_SIZE 100, keep that in mind because raising it above 100 would make the cursor bug worse."),
            ("gpt-4o", "That interaction matters a lot, thanks. So MAX_PAGE_SIZE is 100 and changing it is risky because of the cursor bug at page size 100."),
            ("claude-sonnet-4", "Exactly. I think that is everything for the handoff. Good luck with the fix."),
            ("gpt-4o", "Thanks, I have all the context I need now."),
        ],
        "critical": [
            "github.com/acme/ledger",
            "ledger-api v2.7.3",
            "Kubernetes 1.29",
            "prod-east",
            "PGR-4091",
            "services/pagination.py",
            "page size 50",
            "45s",
            "ledger_api_p99_latency_ms",
            "grafana.internal/d/ledger-api",
            "LEDGER-142",
            "MAX_PAGE_SIZE",
            "/etc/ledger-api/gateway.yaml",
            "2026-03-15",
            "never skip the canary",
        ],
        "stale": ["30s"],
    },
    {
        "name": "db-migration",
        "space": "bench-db",
        "task": "Summarize the migration plan and its constraints for the cutover.",
        "conversation": [
            ("claude-sonnet-4", "Planning notes for the ledger DB migration. Source is MySQL 8.0.34, target is PostgreSQL 16.2."),
            ("gpt-4o", "Got it. How big is the dataset?"),
            ("claude-sonnet-4", "The main table has 12,000,000 rows, roughly 24,000,000 with the audit tables."),
            ("gpt-4o", "Understood. What is the downtime budget?"),
            ("claude-sonnet-4", "The cutover must keep downtime under 15m."),
            ("gpt-4o", "Okay, I will remember that. Which tool does the CDC?"),
            ("claude-sonnet-4", "We decided to use Debezium 2.6 for CDC replication."),
            ("gpt-4o", "Noted. When is the cutover?"),
            ("claude-sonnet-4", "The cutover date is 2026-04-15."),
            ("gpt-4o", "Makes sense. What about the backfill batch size?"),
            ("claude-sonnet-4", "The backfill batch size is 5000 rows per transaction for now."),
            ("gpt-4o", "Understood. And the rollback plan?"),
            ("claude-sonnet-4", "The rollback script is /opt/rollback.sh and the feature flag is FF_CUTOVER."),
            ("gpt-4o", "Okay. Any constraints on writes during backfill?"),
            ("claude-sonnet-4", "We must never write to the target schema during backfill, only CDC applies changes."),
            ("gpt-4o", "Noted. Who tracks this?"),
            ("claude-sonnet-4", "TODO: PLAT-2210 tracks the migration, Dana owns it."),
            ("gpt-4o", "Got it. The staging database is db.staging:5432 for rehearsal."),
            ("claude-sonnet-4", "Yes, staging is db.staging:5432 and we rehearse there weekly."),
            ("gpt-4o", "What is the benchmark target?"),
            ("claude-sonnet-4", "The target is 2400 tps sustained after cutover."),
            ("gpt-4o", "Understood. Do we keep MySQL around after cutover?"),
            ("claude-sonnet-4", "We decided to keep MySQL read-only for 2 weeks after cutover, then decommission it."),
            ("gpt-4o", "Thanks. Let me recap the plan to make sure I have it: source MySQL 8.0.34 with 12,000,000 rows in the main table, target PostgreSQL 16.2, CDC by Debezium 2.6, cutover on 2026-05-01, downtime under 15m. Correct?"),
            ("claude-sonnet-4", "That recap is correct. For background, we evaluated pglogical first, but we decided to use Debezium 2.6 for CDC replication instead of pglogical, and the Debezium connector config lives in /etc/debezium/ledger.json."),
            ("gpt-4o", "Got it. I will remember the Debezium decision and the connector config path. Any operational constraints I should keep in mind?"),
            ("claude-sonnet-4", "Yes, two hard constraints. First, we must never write to the target schema during backfill, only CDC applies changes. Second, the replication slot must be monitored because it can grow unbounded if the consumer stalls."),
            ("gpt-4o", "Understood. So no direct writes to the target during backfill, CDC only, and watch the replication slot. What does the backfill look like end to end?"),
            ("claude-sonnet-4", "The backfill copies table by table in dependency order, pausing between tables to let CDC catch up. We track progress in the migration log and the estimated total runtime is about 6 hours."),
            ("gpt-4o", "Makes sense. And the rollback story if something goes wrong?"),
            ("claude-sonnet-4", "If we need to roll back, /opt/rollback.sh flips writes back to MySQL and the feature flag FF_CUTOVER gets disabled. The rollback was rehearsed and it takes 10 minutes."),
            ("gpt-4o", "Noted. So roll back with /opt/rollback.sh, disable FF_CUTOVER, known to take 10 minutes. Who is on point?"),
            ("claude-sonnet-4", "Dana owns the migration tracked in PLAT-2210, and the weekly rehearsal happens on staging at db.staging:5432. The benchmark requirement is 2400 tps sustained after cutover."),
            ("gpt-4o", "Understood. Do we rehearse on the same staging database?"),
            ("claude-sonnet-4", "Yes, rehearsals run on db.staging:5432 every week. Also the migration log path is /var/log/migrate/ledger.log if you need to follow progress."),
            ("gpt-4o", "Thanks. Let me confirm the dates one more time: cutover 2026-05-01, MySQL kept read-only for 2 weeks after, backfill batch size 2000 rows per transaction. Anything I missed?"),
            ("claude-sonnet-4", "That is complete. The only open item is whether we keep the audit tables in the same instance, but no decision has been made on that."),
            ("gpt-4o", "Great, I have it. Thanks for the thorough handoff."),
        ],
        "critical": [
            "MySQL 8.0.34",
            "PostgreSQL 16.2",
            "12,000,000 rows",
            "15m",
            "Debezium 2.6",
            "2026-05-01",
            "2000 rows per transaction",
            "/opt/rollback.sh",
            "FF_CUTOVER",
            "never write to the target schema",
            "PLAT-2210",
            "db.staging:5432",
            "2400 tps",
            "read-only for 2 weeks",
        ],
        "stale": ["2026-04-15", "5000 rows per transaction"],
    },
    {
        "name": "recsys-research",
        "space": "bench-rec",
        "task": "What did we learn about the recommendation model experiment and what is next?",
        "conversation": [
            ("local-llama-3", "Research notes on the recommender. We decided to use bge-m3 for embeddings and hnswlib for the vector index."),
            ("gpt-4o", "Got it. What recall do we get?"),
            ("local-llama-3", "Recall is 0.87 at k=20 with ef_search 128."),
            ("gpt-4o", "Understood. What is the latency budget?"),
            ("local-llama-3", "The latency budget is 200ms p95 for the retrieval stage."),
            ("gpt-4o", "Noted. What about the model architecture?"),
            ("local-llama-3", "We decided to use matrix factorization for ranking."),
            ("gpt-4o", "Makes sense. Any data constraints?"),
            ("local-llama-3", "User data must never leave eu-west-1, that is a hard constraint."),
            ("gpt-4o", "Okay, I will remember that. Which experiment is this?"),
            ("local-llama-3", "Experiment EXP-77 shows CTR +4.2% over the baseline."),
            ("gpt-4o", "Noted. What open questions remain?"),
            ("local-llama-3", "Open question: how do we handle cold start users with no history?"),
            ("gpt-4o", "Got it. Where is the evaluation notebook?"),
            ("local-llama-3", "The evaluation notebook is /lab/recsys/eval.ipynb and the dataset is s3://rec-data/interactions_2026q1."),
            ("gpt-4o", "Understood. Is the rollout flagged?"),
            ("local-llama-3", "Yes, the feature flag is rec_v2, currently at 10 percent of traffic."),
            ("gpt-4o", "Thanks. Does the incremental index update job run nightly?"),
            ("local-llama-3", "The index update job runs nightly at 02:30 UTC and takes about 40 minutes."),
            ("gpt-4o", "Thanks. Let me recap to be safe: embeddings from bge-m3, index in hnswlib, recall 0.87 at k=20 with ef_search 128, and the ranking model is a two-tower model. Correct?"),
            ("local-llama-3", "Close. The latency budget changed to 120ms p95 after profiling, and we decided to use a two-tower model for ranking instead of matrix factorization."),
            ("gpt-4o", "Got it, thanks for the correction: latency budget 120ms p95 now, and the ranking decision is the two-tower model. I will remember that."),
            ("local-llama-3", "For background, the embedding service wraps bge-m3 behind an internal API and the batch size for embedding is 64 texts per call."),
            ("gpt-4o", "Understood. What does the evaluation pipeline look like?"),
            ("local-llama-3", "The evaluation notebook is /lab/recsys/eval.ipynb, and the interactions dataset is s3://rec-data/interactions_2026q1. We run weekly evaluations and the last run was EXP-77 with CTR +4.2% over the baseline."),
            ("gpt-4o", "Noted. So the notebook and dataset are the place to reproduce EXP-77. What is the rollout status?"),
            ("local-llama-3", "The feature flag rec_v2 is at 10 percent of traffic. The index update job runs nightly at 02:30 UTC and takes about 40 minutes, so avoid deploys during that window."),
            ("gpt-4o", "Good to know. Any other constraints I should be careful about?"),
            ("local-llama-3", "Yes, user data must never leave eu-west-1, that is a hard constraint from legal. We need recall above 0.9 before we ship the two-tower model."),
            ("gpt-4o", "Understood. Is the cold start problem resolved?"),
            ("local-llama-3", "No, it remains an open question: how do we handle cold start users with no history?"),
            ("gpt-4o", "Understood. I have everything, thanks for the thorough handoff."),
        ],
        "critical": [
            "bge-m3",
            "hnswlib",
            "0.87",
            "ef_search 128",
            "120ms p95",
            "two-tower model",
            "never leave eu-west-1",
            "EXP-77",
            "CTR +4.2%",
            "cold start users",
            "/lab/recsys/eval.ipynb",
            "s3://rec-data/interactions_2026q1",
            "rec_v2",
            "02:30 UTC",
            "40 minutes",
            "recall above 0.9",
        ],
        "stale": ["200ms"],
    },
]


def run_sample(sample, counter):
    path = os.path.join(tempfile.mkdtemp(prefix="mnemo-bench-"), "bench.db")
    svc = MemoryService(Config.from_env(db_path=path))
    turns = [{"model": m, "text": t} for m, t in sample["conversation"]]
    raw = "\n".join(t for _, t in sample["conversation"])
    original = counter.count(raw)

    t0 = time.perf_counter()
    svc.write(sample["space"], turns, source_model=sample["conversation"][0][0])
    write_ms = (time.perf_counter() - t0) * 1000

    out = svc.read(sample["space"], query=sample["task"], max_tokens=BUDGET)
    tight = svc.read(sample["space"], query=sample["task"], max_tokens=TIGHT_BUDGET)

    missing = [c for c in sample["critical"] if c not in out["context"]]
    stale = [c for c in sample["stale"] if c in out["context"]]
    return {
        "name": sample["name"],
        "original": original,
        "stored": out["stats"]["stored_tokens"],
        "returned": out["stats"]["returned_tokens"],
        "tight": tight["stats"]["returned_tokens"],
        "tight_omitted": tight["stats"]["units_omitted"],
        "omitted": out["stats"]["units_omitted"],
        "units": out["stats"]["units_total"],
        "superseded": out["stats"]["superseded_excluded"],
        "missing": missing,
        "stale": stale,
        "write_ms": write_ms,
    }


def main():
    counter = TokenCounter()
    results = [run_sample(s, counter) for s in SAMPLES]
    failures = []

    print(f"Mnemo benchmark (tokenizer={counter.name}, budget={BUDGET}, tight={TIGHT_BUDGET})\n")
    header = f"{'sample':<16}{'orig':>7}{'stored':>8}{'stored%':>9}{'ctx':>6}{'ctx%':>8}{'omitted':>9}{'facts':>8}{'stale':>7}"
    print(header)
    print("-" * len(header))
    for r, s in zip(results, SAMPLES):
        stored_pct = 1 - r["stored"] / r["original"]
        ctx_pct = 1 - r["returned"] / r["original"]
        facts = f"{len(s['critical']) - len(r['missing'])}/{len(s['critical'])}"
        stale = "ok" if not r["stale"] else f"LEAK:{','.join(r['stale'])}"
        print(
            f"{r['name']:<16}{r['original']:>7}{r['stored']:>8}{stored_pct:>8.0%} "
            f"{r['returned']:>5}{ctx_pct:>8.0%}{r['omitted']:>9}{facts:>8}{stale:>7}"
        )
        if r["missing"]:
            failures.append(f"{r['name']}: missing critical facts {r['missing']}")
        if r["stale"]:
            failures.append(f"{r['name']}: stale facts leaked {r['stale']}")
        if ctx_pct < 0.60:
            failures.append(f"{r['name']}: reduction only {ctx_pct:.0%} (<60%)")

    avg_ctx = sum(1 - r["returned"] / r["original"] for r in results) / len(results)
    avg_stored = sum(1 - r["stored"] / r["original"] for r in results) / len(results)
    total_facts = sum(len(s["critical"]) for s in SAMPLES)
    kept_facts = sum(len(s["critical"]) - len(r["missing"]) for r, s in zip(results, SAMPLES))
    total_write = sum(r["write_ms"] for r in results)
    print(
        f"\naverage reduction vs raw: stored {avg_stored:.0%}, returned-to-model {avg_ctx:.0%}"
        f"\ncritical fact retention at {BUDGET} tokens: {kept_facts}/{total_facts}"
        f"\ntotal ingest time (rules mode): {total_write:.0f}ms for {sum(r['original'] for r in results)} raw tokens"
    )

    print("\ntight-budget check (ctx at 150 tokens, remainder discoverable via omitted index):")
    for r in results:
        print(
            f"  {r['name']:<16} raw={r['original']:>5} -> {r['tight']:>4} tokens, "
            f"{r['tight_omitted']} units omitted"
        )

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1

    print("\nALL CHECKS PASSED: >=60% reduction, 100% critical facts retained, no stale facts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
