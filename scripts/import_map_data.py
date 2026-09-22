"""Import the bundled OpenStreetMap extracts into the map tables.

The source CSVs use Overpass field names (``@lat``, ``@lon`` and snake_case),
while the SQLAlchemy models use the names exposed by the API. Keep that
translation here so the files can be refreshed without editing them by hand.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app import create_app
from app.map.models import BicycleParking, BicycleRepair, Station, Toilet
from extensions import db


DATA_DIR = Path(__file__).resolve().parent / "data"
GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode_geohash(lat, lng, precision=5):
    """Return a standard geohash without requiring another runtime package."""
    lat_interval = [-90.0, 90.0]
    lng_interval = [-180.0, 180.0]
    bits = (16, 8, 4, 2, 1)
    output = []
    bit_index = 0
    char_value = 0
    use_lng = True

    while len(output) < precision:
        interval = lng_interval if use_lng else lat_interval
        value = lng if use_lng else lat
        midpoint = (interval[0] + interval[1]) / 2
        if value >= midpoint:
            char_value |= bits[bit_index]
            interval[0] = midpoint
        else:
            interval[1] = midpoint

        use_lng = not use_lng
        if bit_index < 4:
            bit_index += 1
        else:
            output.append(GEOHASH_ALPHABET[char_value])
            bit_index = 0
            char_value = 0

    return "".join(output)


def clean_value(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def as_bool(value):
    value = clean_value(value)
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"yes", "true", "1", "y"}:
        return True
    if normalized in {"no", "false", "0", "n"}:
        return False
    return None


def as_int(value):
    value = clean_value(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def base_mapping(row):
    record_id = as_int(row.get("@id", row.get("id")))
    lat_value = clean_value(row.get("@lat", row.get("lat")))
    lng_value = clean_value(row.get("@lon", row.get("lng")))
    if record_id is None or lat_value is None or lng_value is None:
        return None

    try:
        lat = float(lat_value)
        lng = float(lng_value)
    except (TypeError, ValueError):
        return None

    return {
        "id": record_id,
        "lat": lat,
        "lng": lng,
        "gh5": encode_geohash(lat, lng),
    }


def station_mapping(row):
    record = base_mapping(row)
    if not record:
        return None
    record.update(
        name=clean_value(row.get("name")),
        cap=as_int(row.get("capacity", row.get("cap"))),
        type="fountain",
    )
    return record


def repair_mapping(row):
    record = base_mapping(row)
    if not record:
        return None
    record.update(
        name=clean_value(row.get("name")),
        opening_hours=clean_value(row.get("opening_hours")),
        phone=clean_value(row.get("phone")),
    )
    return record


def toilet_mapping(row):
    record = base_mapping(row)
    if not record:
        return None
    record.update(
        fee=as_bool(row.get("fee")),
        openingHours=clean_value(row.get("opening_hours", row.get("openingHours"))),
        changingTable=as_bool(row.get("changing_table", row.get("changingTable"))),
    )
    return record


def parking_mapping(row):
    record = base_mapping(row)
    if not record:
        return None
    record.update(
        covered=as_bool(row.get("covered")),
        indoor=as_bool(row.get("indoor")),
        access=clean_value(row.get("access")),
        fee=as_bool(row.get("fee")),
        bicycleParking=clean_value(row.get("bicycle_parking", row.get("bicycleParking"))),
        surveillance=as_bool(row.get("surveillance")),
        capacity=as_int(row.get("capacity")),
    )
    return record


def import_csv_to_model(file_path, model_cls, mapper, batch_size=2000):
    """Insert new records from one CSV, leaving existing rows untouched."""
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"File non trovato: {file_path}")
        return 0

    existing_ids = {row[0] for row in db.session.query(model_cls.id).all()}
    pending = []
    inserted = 0

    for frame in pd.read_csv(file_path, chunksize=batch_size, low_memory=False):
        for source in frame.to_dict(orient="records"):
            record = mapper(source)
            if not record or record["id"] in existing_ids:
                continue
            pending.append(record)
            existing_ids.add(record["id"])

        if pending:
            db.session.bulk_insert_mappings(model_cls, pending)
            db.session.commit()
            inserted += len(pending)
            pending.clear()

    print(f"Importati {inserted} nuovi record per {model_cls.__name__}.")
    return inserted


def import_data():
    app = create_app()
    with app.app_context():
        db.create_all()
        datasets = (
            ("stations.csv", Station, station_mapping),
            ("toilets.csv", Toilet, toilet_mapping),
            ("bicycle_repair.csv", BicycleRepair, repair_mapping),
            # The original extract was published with this filename typo.
            ("bicycke_parkings.csv", BicycleParking, parking_mapping),
        )
        for filename, model_cls, mapper in datasets:
            import_csv_to_model(DATA_DIR / filename, model_cls, mapper)

        print("Import completato con successo.")


if __name__ == "__main__":
    import_data()
