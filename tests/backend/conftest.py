"""
Pytest configuration for backend tests
"""

import os
import sys
from pathlib import Path

import pytest

# Add the backend directory to Python path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Set test environment before importing app modules
os.environ["ENVIRONMENT"] = "test"
# Use different database URLs for CI vs local development
if "GITHUB_ACTIONS" in os.environ:
    # GitHub Actions CI environment
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/test_db"
    TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/test_db"
else:
    # Local development environment
    os.environ["DATABASE_URL"] = (
        "postgresql://user:password@localhost:5432/civicspark_db"
    )
    TEST_DATABASE_URL = "postgresql://user:password@localhost:5432/civicspark_db"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base

# Test database configuration
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def db_engine():
    """Create database engine for testing"""
    # Create test database tables
    Base.metadata.create_all(bind=engine)
    yield engine
    # Clean up test database tables
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    """Create a new database session for a test"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
