import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from app.database.connection import Database
from app.database.repository import BugReportRepository


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a fresh in-memory-like temp database for each test."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    await database.connect()
    yield database
    await database.disconnect()


@pytest_asyncio.fixture
async def repo(db):
    """Repository backed by temp database."""
    return BugReportRepository(db)
