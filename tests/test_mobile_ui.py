from datetime import datetime, timezone

from app.auth.models import Bike, BikeTracking, RiderShift
from extensions import db


def test_mobile_ride_home_and_populated_analytics(client, user_factory, tmp_path):
    with client.application.app_context():
        user = user_factory(email='mobile-ui@example.com', username='mobile_ui')
        db.session.commit()
        gpx = tmp_path / 'sample.gpx'
        gpx.write_text('<gpx version="1.1"><trk><trkseg></trkseg></trk></gpx>', encoding='utf-8')
        shift = RiderShift(
            session_id='d5657f7e-dfc0-4c5e-a2ef-99f6955ca506',
            user_id=user.id,
            gpx_path=str(gpx),
            total_distance_km=12.4,
            duration_min=44,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(shift)
        db.session.commit()

    response = client.post('/login', data={'email': 'mobile-ui@example.com', 'password': 'password'})
    assert response.status_code in (200, 302)

    home = client.get('/')
    assert home.status_code == 200
    assert b'id="ride-screen"' in home.data
    assert b'mobile-tab-record' in home.data
    assert b'home-readiness' in home.data
    assert b'home-gps-status' in home.data
    assert b'home-desktop-start' in home.data
    assert b'home-weather-demo' in home.data
    assert b'quick-stack' not in home.data
    assert b'home-route-card' not in home.data

    analytics = client.get('/analytics/')
    assert analytics.status_code == 200
    assert b'ride-history-card' in analytics.data
    assert b'data-shift-id=' in analytics.data


def test_home_and_profile_show_real_bike_and_hide_full_tax_id(client, user_factory):
    with client.application.app_context():
        user = user_factory(email='bike-ui@example.com', username='bike_ui', tax_id_code='ABC1234567890XYZ')
        db.session.flush()
        db.session.add(Bike(bike_id='MyBikeCode12', user_id=user.id, total_km=24.5))
        db.session.commit()

    client.post('/login', data={'email': 'bike-ui@example.com', 'password': 'password'})

    home = client.get('/')
    assert home.status_code == 200
    assert b'home-page' in home.data
    assert b'MyBikeCode12' in home.data
    assert b'home-bike-connect' not in home.data

    profile = client.get('/auth/me')
    assert profile.status_code == 200
    assert b'profile-page' in profile.data
    assert b'MyBikeCode12' in profile.data
    assert b'ABC1234567890XYZ' not in profile.data
    assert b'delete-account' in client.get('/auth/settings').data


def test_mobile_pages_work_before_bike_schema_migration(client, user_factory):
    with client.application.app_context():
        user_factory(email='pre-migration@example.com', username='pre_migration')
        db.session.commit()
        BikeTracking.__table__.drop(db.engine)
        Bike.__table__.drop(db.engine)

    client.post('/login', data={'email': 'pre-migration@example.com', 'password': 'password'})

    assert client.get('/').status_code == 200
    assert b'home-bike-connect' in client.get('/').data
    assert b'Bike linking will be available' in client.get('/').data
    profile = client.get('/auth/me')
    assert profile.status_code == 200
    assert b'No bike linked' in profile.data
