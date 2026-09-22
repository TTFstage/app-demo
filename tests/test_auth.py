import logging

from app.auth.models import user_datastore
from extensions import db

logger = logging.getLogger(__name__)

def test_user_creation(app, user_factory):
    """Test that a user can be created via the datastore."""
    logger.info("Testing user creation")
    with app.app_context():
        user_factory(email="test@example.com", username="testuser")
        db.session.commit()
        
        fetched_user = user_datastore.find_user(email="test@example.com")
        assert fetched_user is not None
        assert fetched_user.username == "testuser"

def test_login_page_loads(client):
    """Test that the login page loads."""
    logger.info("Testing login page load")
    response = client.get("/login") # Flask-Security defaults
    assert response.status_code == 200


def _valid_registration(**overrides):
    data = {
        "email": "fabio.caccamo@gmail.com",
        "username": "fcaccamo",
        "password": "Password1!",
        "password_confirm": "Password1!",
        "first_name": "Fabio",
        "last_name": "Caccamo",
        "date_of_birth": "1985-04-03",
        "gender": "M",
        "tax_id_code": "CCCFBA85D03L219P",
        "birth_city_country": "Torino",
        "phone_number": "+39 333 1234567",
    }
    data.update(overrides)
    return data


def test_registration_joins_first_and_last_name(client, app):
    response = client.post("/register", data=_valid_registration(), follow_redirects=False)

    assert response.status_code == 302
    with app.app_context():
        user = user_datastore.find_user(email="fabio.caccamo@gmail.com")
        assert user is not None
        assert user.full_name == "Fabio Caccamo"


def test_registration_rejects_tax_id_for_different_person(client, app):
    response = client.post(
        "/register",
        data=_valid_registration(tax_id_code="RSSMRA80E20F205I"),
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"does not match the personal details" in response.data
    with app.app_context():
        assert user_datastore.find_user(email="fabio.caccamo@gmail.com") is None


def test_registration_accepts_valid_omocode(client, app):
    response = client.post(
        "/register",
        data=_valid_registration(tax_id_code="CCCFBA85D03L21VE"),
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        assert user_datastore.find_user(email="fabio.caccamo@gmail.com") is not None
