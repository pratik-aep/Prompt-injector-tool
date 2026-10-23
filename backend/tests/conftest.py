import pytest

from backend.core.security import secrets_registry
from backend.experiments import runner
from backend.services.bootstrap import bootstrap


@pytest.fixture(autouse=True)
def fresh_db():
    secrets_registry.clear()
    runner._locks.clear()
    bootstrap(":memory:")
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    with TestClient(create_app(":memory:", serve_frontend=False)) as c:
        yield c
