from datetime import datetime, timezone

from app.auth.models import RiderShift
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

    analytics = client.get('/analytics/')
    assert analytics.status_code == 200
    assert b'ride-history-card' in analytics.data
    assert b'data-shift-id=' in analytics.data
