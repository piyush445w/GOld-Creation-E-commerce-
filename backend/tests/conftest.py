import os
import sys
import pytest

# Make the backend/ directory importable so `from app import ...` works when pytest runs from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# Use a deterministic secret key so session/CSRF behavior is stable across test runs.
os.environ['SECRET_KEY'] = 'test-secret-key'

# Run all tests against an in-memory SQLite DB: fast, isolated, and no setup/teardown needed.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app, db  # noqa: E402


# Fixture (function scope): provides a fresh Flask app in 'testing' mode with created tables.
# Creates schema before yield, tears down (session.remove + drop_all) after.
# Required by: all tests needing an app context (currency, routes, models).
@pytest.fixture
def app():
    # Build a fresh app in 'testing' mode (disables CSRF, debug, etc.) and create its tables.
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        # Clean up the session and drop tables so each test starts from an empty schema.
        db.session.remove()
        db.drop_all()


# Fixture (function scope): provides a Flask test client bound to the app fixture.
# Used for making HTTP requests in route tests (storefront, admin, auth).
@pytest.fixture
def client(app):
    # Provide a Flask test client bound to the app fixture for making HTTP requests in tests.
    return app.test_client()


# Fixture (function scope): provides the SQLAlchemy session for direct model manipulation.
# Rolls back after each test to keep DB clean. Used by model and route tests needing DB writes.
@pytest.fixture
def db_session(app):
    # Provide the SQLAlchemy session so tests can add/query models directly.
    with app.app_context():
        yield db.session
        # Roll back any changes so the database stays clean between tests.
        db.session.rollback()
