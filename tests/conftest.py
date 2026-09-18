import logging
from datetime import date

import pytest
from sqlalchemy.pool import StaticPool

from app import create_app
from app.auth.models import user_datastore
from config import Config
from extensions import db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory SQLite for testing
    SQLALCHEMY_ENGINE_OPTIONS = {  # noqa: RUF012
        'poolclass': StaticPool,
        'connect_args': {'check_same_thread': False}
    }
    WTF_CSRF_ENABLED = False
    SECURITY_PASSWORD_HASH = 'plaintext'
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

@pytest.fixture
def app():
    """Create an isolated application and database for each test."""
    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        if not user_datastore.find_role('admin'):
            user_datastore.create_role(name='admin', description='Admin Role')
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """A test runner for the app's cli commands."""
    return app.test_cli_runner()


@pytest.fixture
def user_factory():
    """Create valid users with all mandatory profile fields."""
    def create_user(email, username, **overrides):
        defaults = {
            'email': email,
            'username': username,
            'password': 'password',
            'tax_id_code': f'{username.upper():0<16}'[:16],
            'full_name': username.replace('_', ' ').title(),
            'date_of_birth': date(1990, 1, 1),
            'gender': 'M',
            'birth_city_country': 'Rome',
        }
        defaults.update(overrides)
        return user_datastore.create_user(**defaults)

    return create_user

@pytest.fixture(autouse=True)
def setup_logging(request):
    """Fixture to ensure logging happens for each test."""
    logger = logging.getLogger(request.node.name)
    
    # Recupera la descrizione iniziale del test (il suo docstring)
    description = request.node.function.__doc__
    if description:
        logger.info(f"Starting test: {request.node.name} - Descrizione: {description.strip()}")
    else:
        logger.info(f"Starting test: {request.node.name}")
        
    yield
    logger.info(f"Finished test: {request.node.name}")
