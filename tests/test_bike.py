from app.auth.models import Bike, BikeTracking
from extensions import db


def _login(client, email):
    response = client.post(
        '/login',
        data={'email': email, 'password': 'password'},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_bike_link_replaces_the_riders_previous_bike(client, app, user_factory):
    with app.app_context():
        rider = user_factory('bike-rider@example.com', 'bike_rider')
        first_bike = Bike(bike_id='FIRSTBIKEID')
        second_bike = Bike(bike_id='SECONDBIKEID')
        db.session.add_all([first_bike, second_bike])
        db.session.commit()
        rider_id = rider.id
        first_bike_id = first_bike.id
        second_bike_id = second_bike.id

    anonymous_response = client.get('/bike/FIRSTBIKEID', follow_redirects=False)
    assert anonymous_response.status_code == 302
    assert '/login' in anonymous_response.headers['Location']

    _login(client, 'bike-rider@example.com')
    response = client.get('/bike/FIRSTBIKEID', follow_redirects=False)
    assert response.status_code == 302

    response = client.get('/bike/SECONDBIKEID', follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        rider = db.session.get(type(rider), rider_id)
        first_bike = db.session.get(Bike, first_bike_id)
        second_bike = db.session.get(Bike, second_bike_id)
        assert rider.bike.id == second_bike_id
        assert first_bike.user_id is None
        assert second_bike.user_id == rider_id


def test_bike_models_generate_ids_and_track_sessions(app):
    with app.app_context():
        bike = Bike()
        tracking = BikeTracking(bike=bike, total_km=8.5, gpx_path='rides/8.gpx')
        db.session.add(tracking)
        db.session.commit()

        assert len(bike.bike_id) == 12
        assert bike.bike_id.isalpha()
        assert bike.total_km == 0.0
        assert tracking.bike_id == bike.id
        assert tracking.date is not None


def test_bike_can_be_linked_from_home_form(client, app, user_factory):
    with app.app_context():
        rider = user_factory('bike-form@example.com', 'bike_form')
        db.session.add(Bike(bike_id='FORMBIKE123'))
        db.session.commit()
        rider_id = rider.id

    _login(client, 'bike-form@example.com')
    response = client.post('/bikes/connect', data={'bike_id': 'FORMBIKE123'})
    assert response.status_code == 302
    assert response.headers['Location'] == '/'

    with app.app_context():
        assert db.session.get(type(rider), rider_id).bike.bike_id == 'FORMBIKE123'


def test_bike_form_reports_unknown_code(client, app, user_factory):
    with app.app_context():
        user_factory('bike-missing@example.com', 'bike_missing')
        db.session.commit()

    _login(client, 'bike-missing@example.com')
    response = client.post('/bikes/connect', data={'bike_id': 'NOTFOUND123'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'No bike was found with that code.' in response.data
