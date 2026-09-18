import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, jsonify, request
from flask_security import auth_required, current_user

from app.telemetry.models import Activity
from extensions import db

logger = logging.getLogger(__name__)

telemetry_bp = Blueprint("telemetry", __name__)


def _parse_activity(data: dict) -> Activity:
    """Validate an activity and bind it to the authenticated user."""
    required = ("start_datetime", "duration_sec", "distance_km")
    for field in required:
        if field not in data:
            abort(400, description=f"Missing field: {field}")

    try:
        start_dt = datetime.fromisoformat(str(data["start_datetime"]).replace("Z", "+00:00"))
        duration_sec = int(data["duration_sec"])
        distance_km = float(data["distance_km"])
        active_time_sec = int(data.get("active_time_sec", duration_sec))
    except (TypeError, ValueError):
        abort(400, description="Invalid activity values")

    if duration_sec <= 0 or distance_km < 0 or not 0 <= active_time_sec <= duration_sec:
        abort(400, description="Invalid values for duration, distance, or active_time")

    avg_speed_kmh = distance_km / (duration_sec / 3600)
    return Activity(
        start_datetime=start_dt,
        duration_sec=duration_sec,
        distance_km=distance_km,
        avg_speed_kmh=round(avg_speed_kmh, 2),
        active_time_sec=active_time_sec,
        user_id=current_user.id,
    )


def _activities_between(start: datetime, end: datetime) -> list[Activity]:
    return (
        Activity.query.filter(
            Activity.user_id == current_user.id,
            Activity.start_datetime >= start,
            Activity.start_datetime < end,
        )
        .order_by(Activity.start_datetime)
        .all()
    )


def _summary(activities: list[Activity]) -> dict:
    total_distance = sum(float(activity.distance_km) for activity in activities)
    total_duration = sum(activity.duration_sec for activity in activities)
    active_seconds = sum(activity.active_time_sec for activity in activities)
    avg_speed = total_distance / (total_duration / 3600) if total_duration else 0.0
    return {
        "total_distance_km": round(total_distance, 3),
        "duration_sec": total_duration,
        "avg_speed_kmh": round(avg_speed, 2),
        "active_hours": round(active_seconds / 3600, 2),
    }


def _hourly(activities: list[Activity]) -> list[dict]:
    by_hour: dict[int, list[Activity]] = defaultdict(list)
    for activity in activities:
        by_hour[activity.start_datetime.hour].append(activity)

    result = []
    for hour in sorted(by_hour):
        values = _summary(by_hour[hour])
        result.append(
            {
                "hour": hour,
                "avg_speed_kmh": values["avg_speed_kmh"],
                "distance_km": values["total_distance_km"],
                "duration_sec": values["duration_sec"],
            }
        )
    return result


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min)
    return start, start + timedelta(days=1)


def _activity_dict(activity: Activity) -> dict:
    return {
        "id": activity.id,
        "start_datetime": activity.start_datetime.isoformat(),
        "duration_sec": activity.duration_sec,
        "distance_km": float(activity.distance_km),
        "avg_speed_kmh": float(activity.avg_speed_kmh),
        "active_time_sec": activity.active_time_sec,
    }


@telemetry_bp.post("/activity")
@auth_required()
def create_activity():
    if not request.is_json:
        abort(400, description="Request must be JSON")

    activity = _parse_activity(request.get_json(silent=False))
    try:
        db.session.add(activity)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error creating activity for user=%s", current_user.id)
        abort(500, description="Internal server error")

    return jsonify({"status": "ok", "activity_id": activity.id}), 201


@telemetry_bp.get("/data/day")
@auth_required()
def get_day():
    date_str = request.args.get("date")
    if not date_str:
        abort(400, description="Missing 'date' parameter (YYYY-MM-DD)")
    try:
        selected_date = date.fromisoformat(date_str)
    except ValueError:
        abort(400, description="Invalid date format; expected YYYY-MM-DD")

    start, end = _day_bounds(selected_date)
    activities = _activities_between(start, end)
    if not activities:
        abort(404, description="No data for this date")

    return jsonify(
        {
            "date": selected_date.isoformat(),
            "daily": _summary(activities),
            "hourly": _hourly(activities),
            "activities": [_activity_dict(activity) for activity in activities],
        }
    )


@telemetry_bp.get("/data/day-hour")
@auth_required()
def get_day_hour():
    date_str = request.args.get("date")
    if not date_str:
        abort(400, description="Missing 'date' parameter")
    try:
        selected_date = date.fromisoformat(date_str)
    except ValueError:
        abort(400, description="Invalid date format")

    start, end = _day_bounds(selected_date)
    hourly = _hourly(_activities_between(start, end))
    if not hourly:
        abort(404, description="No hourly data for this date")
    return jsonify({"date": selected_date.isoformat(), "hourly": hourly})


@telemetry_bp.get("/data/week-hour")
@auth_required()
def get_week_hourly():
    start_str = request.args.get("start")
    if not start_str:
        abort(400, description="Missing 'start' parameter (start date YYYY-MM-DD)")
    try:
        start_date = date.fromisoformat(start_str)
    except ValueError:
        abort(400, description="Invalid date format")

    days = []
    for offset in range(7):
        selected_date = start_date + timedelta(days=offset)
        day_start, day_end = _day_bounds(selected_date)
        activities = _activities_between(day_start, day_end)
        days.append(
            {
                "date": selected_date.isoformat(),
                "daily": _summary(activities),
                "hourly": _hourly(activities),
            }
        )

    total_distance = sum(item["daily"]["total_distance_km"] for item in days)
    total_duration = sum(item["daily"]["duration_sec"] for item in days)
    return jsonify(
        {
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=6)).isoformat(),
            "weekly_summary": {
                "total_distance_km": round(total_distance, 3),
                "total_duration_sec": total_duration,
                "avg_speed_kmh": round(total_distance / (total_duration / 3600), 2)
                if total_duration
                else 0.0,
                "total_active_hours": round(
                    sum(item["daily"]["active_hours"] for item in days), 2
                ),
            },
            "days": days,
        }
    )


@telemetry_bp.get("/data/month")
@auth_required()
def get_month():
    try:
        year = int(request.args["year"])
        month = int(request.args["month"])
        start_date = date(year, month, 1)
    except (KeyError, TypeError, ValueError):
        abort(400, description="Valid 'year' and 'month' parameters are required")

    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    activities = _activities_between(
        datetime.combine(start_date, time.min), datetime.combine(next_month, time.min)
    )
    if not activities:
        abort(404, description="No monthly data for this year/month")

    daily_series = []
    current = start_date
    while current < next_month:
        day_start, day_end = _day_bounds(current)
        day_activities = [
            activity for activity in activities if day_start <= activity.start_datetime < day_end
        ]
        if day_activities:
            daily_series.append({"date": current.isoformat(), **_summary(day_activities)})
        current += timedelta(days=1)

    monthly = _summary(activities)
    monthly["daily_avg_speed"] = monthly.pop("avg_speed_kmh")
    monthly["total_duration"] = monthly.pop("duration_sec")
    return jsonify(
        {"year": year, "month": month, "monthly": monthly, "daily_series": daily_series}
    )


@telemetry_bp.get("/data/year")
@auth_required()
def get_year():
    try:
        year = int(request.args["year"])
        start_date = date(year, 1, 1)
        next_year = date(year + 1, 1, 1)
    except (KeyError, TypeError, ValueError):
        abort(400, description="A valid 'year' parameter is required")

    activities = _activities_between(
        datetime.combine(start_date, time.min), datetime.combine(next_year, time.min)
    )
    if not activities:
        abort(404, description="No yearly data for this year")

    monthly_series = []
    for month in range(1, 13):
        month_start = datetime.combine(date(year, month, 1), time.min)
        month_end = datetime.combine(
            date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1),
            time.min,
        )
        month_activities = [
            activity for activity in activities if month_start <= activity.start_datetime < month_end
        ]
        if month_activities:
            values = _summary(month_activities)
            monthly_series.append(
                {
                    "month": month,
                    "daily_avg_speed": values["avg_speed_kmh"],
                    "total_distance_km": values["total_distance_km"],
                    "total_duration": values["duration_sec"],
                    "active_hours": values["active_hours"],
                }
            )

    yearly = _summary(activities)
    return jsonify(
        {
            "year": year,
            "yearly": {
                "monthly_avg_speed": yearly["avg_speed_kmh"],
                "total_distance_km": yearly["total_distance_km"],
                "total_duration": yearly["duration_sec"],
            },
            "monthly_series": monthly_series,
        }
    )
