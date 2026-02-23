"""Pytest fixtures. Set dummy MONGODB_URL so app lifespan can run in tests."""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def env_for_app():
    os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
    yield
    # optional: delete if we set it only for tests
