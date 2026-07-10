import asyncio
import os

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-suite-secret-not-for-production")

from app.services.state_store import state_store  # noqa: E402  (must follow env defaults above)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    asyncio.run(state_store.initialize_tables())
