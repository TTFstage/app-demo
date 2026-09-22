from app.map.models import BicycleParking, BicycleRepair, Station, Toilet
from extensions import db
from scripts.import_map_data import (
    encode_geohash,
    parking_mapping,
    repair_mapping,
    station_mapping,
    toilet_mapping,
)


def test_map_api_returns_each_point_type(client, app):
    gh5 = encode_geohash(45.4642, 9.19)
    with app.app_context():
        db.session.add_all(
            [
                Station(id=1, lat=45.4642, lng=9.19, name="Fontanella", type="fountain", gh5=gh5),
                BicycleRepair(id=2, lat=45.4643, lng=9.1901, name="Ciclofficina", gh5=gh5),
                Toilet(id=3, lat=45.4644, lng=9.1902, fee=False, gh5=gh5),
                BicycleParking(id=4, lat=45.4645, lng=9.1903, covered=True, gh5=gh5),
            ]
        )
        db.session.commit()

    endpoints = (
        "/api/v1/fountains",
        "/api/v1/bicycle_repair",
        "/api/v1/toilets",
        "/api/v1/bicycle-parkings",
    )
    for endpoint in endpoints:
        response = client.get(f"{endpoint}?gh5={gh5}")
        assert response.status_code == 200
        assert len(response.get_json()) == 1


def test_osm_csv_fields_are_mapped_to_api_models():
    source = {
        "@id": "42",
        "@lat": "45.4642",
        "@lon": "9.19",
        "name": "Test point",
    }

    station = station_mapping(source)
    repair = repair_mapping({**source, "opening_hours": "24/7", "phone": "+39 02 123"})
    toilet = toilet_mapping({**source, "fee": "no", "changing_table": "yes"})
    parking = parking_mapping(
        {**source, "covered": "yes", "bicycle_parking": "stands", "capacity": "12"}
    )

    assert station["type"] == "fountain"
    assert station["gh5"] == encode_geohash(45.4642, 9.19)
    assert len(station["gh5"]) == 5
    assert repair["opening_hours"] == "24/7"
    assert toilet["fee"] is False
    assert toilet["changingTable"] is True
    assert parking["covered"] is True
    assert parking["bicycleParking"] == "stands"
    assert parking["capacity"] == 12
