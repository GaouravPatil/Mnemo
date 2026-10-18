import pytest
from fastapi.testclient import TestClient

from mnemo.api import create_app
from mnemo.config import Config
from mnemo.service import MemoryService


@pytest.fixture()
def cfg(tmp_path):
    return Config.from_env(db_path=str(tmp_path / "mnemo.db"), api_key="test-key")


@pytest.fixture()
def svc(cfg):
    return MemoryService(cfg)


@pytest.fixture()
def client(cfg):
    return TestClient(create_app(cfg))
