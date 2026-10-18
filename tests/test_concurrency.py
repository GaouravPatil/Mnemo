from concurrent.futures import ThreadPoolExecutor

from mnemo.config import Config
from mnemo.service import MemoryService


def test_concurrent_writers_from_multiple_services(cfg):
    workers = 8
    per_worker = 5
    services = [
        MemoryService(Config.from_env(db_path=cfg.db_path, api_key=cfg.api_key)) for _ in range(workers)
    ]

    def work(i):
        svc = services[i]
        for j in range(per_worker):
            svc.write(
                "shared",
                f"alias endpoint-{i}-{j} registered by worker",
                source_model=f"model-{i}",
            )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, range(workers)))

    out = services[0].read("shared", max_tokens=100000)
    for i in range(workers):
        for j in range(per_worker):
            assert f"endpoint-{i}-{j}" in out["context"], (i, j)
    assert out["stats"]["units_total"] == workers * per_worker


def test_concurrent_contradicting_writes_leave_one_winner(cfg):
    services = [
        MemoryService(Config.from_env(db_path=cfg.db_path, api_key=cfg.api_key)) for _ in range(6)
    ]

    def work(i):
        services[i].write("race", f"timeout updated to {100 + i}s", source_model=f"model-{i}")

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(work, range(6)))

    out = services[0].read("race", max_tokens=1000)
    lines = [ln for ln in out["context"].splitlines() if not ln.startswith("#")]
    assert len(lines) == 1
    assert out["stats"]["superseded_excluded"] == 5
