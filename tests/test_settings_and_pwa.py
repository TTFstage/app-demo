import hashlib
import hmac

from flask_security.utils import verify_password

from app.auth.models import SOSAlert, SOSContact, User, UserPreference
from extensions import db


def _login(client, email, password="password"):
    response = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def test_settings_are_persisted_and_used_by_map(client, user_factory):
    with client.application.app_context():
        user_factory("settings@example.com", "settings_user")
        db.session.commit()

    _login(client, "settings@example.com")
    assert client.get("/auth/settings").status_code == 200
    response = client.post(
        "/auth/settings",
        data={
            "fall_detection_enabled": "y",
            "sos_notifications_enabled": "y",
            "browser_notifications_enabled": "y",
            "map_default_overlays": "stations",
            "appearance": "dark",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Settings saved" in response.data

    with client.application.app_context():
        preferences = UserPreference.query.one()
        assert preferences.telemetry_enabled is False
        assert preferences.fall_detection_enabled is True
        assert preferences.high_accuracy_gps is False
        assert preferences.map_default_overlays == "stations"
        assert preferences.appearance == "dark"

    map_response = client.get("/map/")
    assert b'data-overlay="stations" checked' in map_response.data
    assert b'data-overlay="bicycle_repair" checked' not in map_response.data


def test_profile_and_password_can_be_updated(client, user_factory):
    with client.application.app_context():
        user_factory("profile@example.com", "profile_user")
        db.session.commit()

    _login(client, "profile@example.com")
    response = client.post(
        "/auth/profile/edit",
        data={
            "username": "updated_user",
            "email": "updated@example.com",
            "phone_number": "+39 333 100 2000",
            "full_name": "Updated Rider",
            "date_of_birth": "1991-04-12",
            "gender": "F",
            "birth_city_country": "Milan",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Profile updated" in response.data

    response = client.post(
        "/auth/password/change",
        data={
            "current_password": "password",
            "new_password": "new-password-123",
            "confirm_password": "new-password-123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Password changed successfully" in response.data

    with client.application.app_context():
        user = User.query.filter_by(email="updated@example.com").one()
        assert user.username == "updated_user"
        assert user.phone_number == "+39 333 100 2000"
        assert verify_password("new-password-123", user.password)


def test_onboarding_marks_setup_complete(client, user_factory):
    with client.application.app_context():
        user_factory("onboarding@example.com", "onboarding_user")
        db.session.commit()

    _login(client, "onboarding@example.com")
    response = client.post(
        "/auth/onboarding",
        data={
            "telemetry_enabled": "y",
            "fall_detection_enabled": "y",
            "high_accuracy_gps": "y",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert response.headers["Location"] == "/"

    with client.application.app_context():
        assert UserPreference.query.one().onboarding_completed is True


def test_sos_webhook_is_signed_and_audited(client, user_factory, monkeypatch):
    with client.application.app_context():
        user = user_factory("alert@example.com", "alert_user")
        db.session.flush()
        db.session.add(
            SOSContact(
                user_id=user.id,
                name="Trusted Person",
                phone="+39 333 000 0000",
                priority=2,
            )
        )
        db.session.commit()

    client.application.config.update(
        SOS_WEBHOOK_URL="https://sos-provider.example/events",
        SOS_WEBHOOK_SECRET="test-secret",
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(url, data, headers, timeout):
        captured.update(url=url, data=data, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr("app.core.routes.requests.post", fake_post)
    _login(client, "alert@example.com")
    response = client.post(
        "/trigger_sos",
        json={
            "session_id": "8fd8ab5f-8734-46c4-baad-197a22d4ca7e",
            "coordinates": {"latitude": 41.9028, "longitude": 12.4964},
        },
    )
    assert response.status_code == 200
    assert response.get_json()["notification_sent"] is True
    expected_signature = hmac.new(
        b"test-secret", captured["data"], hashlib.sha256
    ).hexdigest()
    assert captured["headers"]["X-RoR-Signature"] == f"sha256={expected_signature}"

    with client.application.app_context():
        alert = SOSAlert.query.one()
        assert alert.delivery_status == "sent"
        assert alert.latitude == 41.9028


def test_pwa_assets_are_available(client):
    manifest = client.get("/static/manifest.webmanifest")
    worker = client.get("/service-worker.js")
    offline = client.get("/offline")
    assert manifest.status_code == 200
    assert manifest.get_json()["display"] == "standalone"
    assert worker.status_code == 200
    assert worker.headers["Service-Worker-Allowed"] == "/"
    assert offline.status_code == 200
