from datetime import datetime, timezone

from app.auth.models import FallEvent, RiderShift, User
from app.telemetry.models import Activity
from extensions import db


def _login(client, email):
    response = client.post(
        "/login",
        data={"email": email, "password": "password"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert response.headers["Location"] == "/auth/me"
    assert client.get("/auth/check_session").status_code == 200


def test_telemetry_is_bound_to_authenticated_user(app, user_factory):
    with app.app_context():
        alice = user_factory("telemetry-alice@example.com", "telemetry_alice")
        bob = user_factory("telemetry-bob@example.com", "telemetry_bob")
        db.session.commit()
        alice_id = alice.id
        bob_id = bob.id

    alice_client = app.test_client()
    bob_client = app.test_client()
    _login(alice_client, "telemetry-alice@example.com")
    _login(bob_client, "telemetry-bob@example.com")
    assert alice_client.get("/auth/check_session").status_code == 200

    response = alice_client.post(
        "/telemetry/activity",
        json={
            "start_datetime": "2026-09-17T08:00:00",
            "duration_sec": 3600,
            "distance_km": 18,
            "active_time_sec": 3000,
            "user_id": bob_id,
        },
    )
    assert response.status_code == 201

    with app.app_context():
        activity = Activity.query.one()
        assert activity.user_id == alice_id

    assert bob_client.get("/telemetry/data/day?date=2026-09-17").status_code == 404
    alice_data = alice_client.get("/telemetry/data/day?date=2026-09-17")
    assert alice_data.status_code == 200
    assert alice_data.get_json()["daily"]["total_distance_km"] == 18.0


def test_telemetry_requires_authentication(client):
    response = client.post(
        "/telemetry/activity",
        json={
            "start_datetime": "2026-09-17T08:00:00",
            "duration_sec": 60,
            "distance_km": 1,
        },
    )
    assert response.status_code in (302, 401)


def test_account_deletion_cascades_private_data(
    app, user_factory, monkeypatch, tmp_path
):
    app.config["GPX_STORAGE_DIR"] = str(tmp_path)
    gpx_path = tmp_path / "deleted-user.gpx"
    gpx_path.write_text("<gpx/>", encoding="utf-8")

    with app.app_context():
        user = user_factory("delete-me@example.com", "delete_me")
        db.session.commit()
        user_id = user.id
        db.session.add_all(
            [
                RiderShift(session_id="delete-session", user_id=user_id, gpx_path=str(gpx_path)),
                FallEvent(
                    session_id="delete-session",
                    user_id=user_id,
                    latitude=41.9,
                    longitude=12.5,
                    timestamp=datetime.now(timezone.utc),
                ),
                Activity(
                    start_datetime=datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
                    duration_sec=60,
                    distance_km=1,
                    avg_speed_kmh=60,
                    active_time_sec=60,
                    user_id=user_id,
                ),
            ]
        )
        db.session.commit()

    monkeypatch.setattr("app.auth.routes.redis_client.delete", lambda _key: 1)
    client = app.test_client()
    _login(client, "delete-me@example.com")
    response = client.post("/auth/delete_account", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert db.session.get(User, user_id) is None
        assert RiderShift.query.filter_by(user_id=user_id).count() == 0
        assert FallEvent.query.filter_by(user_id=user_id).count() == 0
        assert Activity.query.filter_by(user_id=user_id).count() == 0
    assert not gpx_path.exists()


def test_sos_response_does_not_claim_delivery(client, user_factory):
    with client.application.app_context():
        user_factory("sos@example.com", "sos_user")
        db.session.commit()

    _login(client, "sos@example.com")
    response = client.post("/trigger_sos")
    assert response.status_code == 202
    assert response.get_json()["notification_sent"] is False
