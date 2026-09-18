import hashlib
import hmac
import json
import os

import requests
from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
)
from flask_security import current_user, login_required

from app.auth.models import FallEvent, RiderShift, SOSAlert, SOSContact, UserPreference
from extensions import db

core_bp = Blueprint('core', __name__)

@core_bp.route("/")
def index():
    shifts = []
    falls = []
    preferences = None
    if current_user.is_authenticated:
        shifts = RiderShift.query.filter_by(user_id=current_user.id).order_by(RiderShift.created_at.desc()).all()
        falls = FallEvent.query.filter_by(user_id=current_user.id).order_by(FallEvent.timestamp.desc()).all()
        preferences = UserPreference.query.filter_by(user_id=current_user.id).first()
    return render_template(
        "core/index.html",
        user=current_user,
        shifts=shifts,
        falls=falls,
        preferences=preferences,
    )

@core_bp.route("/download/gpx/<int:shift_id>")
@login_required
def download_gpx(shift_id):
    shift = RiderShift.query.get_or_404(shift_id)
    if shift.user_id != current_user.id:
        abort(403)
        
    gpx_path = shift.gpx_path
    if not os.path.exists(gpx_path):
        abort(404, description="The GPX file has not been generated yet or has been removed.")
        
    return send_file(gpx_path, as_attachment=True, download_name=f"session_{shift.session_id}.gpx")

@core_bp.route("/trigger_sos", methods=["POST"])
@login_required
def trigger_sos():
    """Persist an SOS and optionally relay it to a configured signed webhook."""
    data = request.get_json(silent=True) or {}
    coordinates = data.get('coordinates') or {}
    preferences = UserPreference.query.filter_by(user_id=current_user.id).first()
    alert = SOSAlert(
        user_id=current_user.id,
        session_id=str(data.get('session_id') or '')[:255] or None,
        latitude=_safe_float(coordinates.get('latitude')),
        longitude=_safe_float(coordinates.get('longitude')),
        delivery_status='recorded',
    )
    db.session.add(alert)
    db.session.commit()

    contacts = (
        SOSContact.query.filter_by(user_id=current_user.id)
        .order_by(SOSContact.priority.desc(), SOSContact.created_at.asc())
        .all()
    )
    webhook_url = current_app.config.get('SOS_WEBHOOK_URL')

    if preferences is not None and not preferences.sos_notifications_enabled:
        return _finish_sos(alert, 'disabled', 'SOS notifications are disabled in settings.')
    if not contacts:
        return _finish_sos(alert, 'no_contacts', 'No emergency contacts are configured.')
    if not webhook_url:
        return _finish_sos(
            alert,
            'not_configured',
            'Automatic SOS notifications are not configured.',
        )

    payload = {
        'event': 'sos.triggered',
        'alert_id': alert.id,
        'occurred_at': alert.created_at.isoformat(),
        'rider': {
            'id': current_user.id,
            'username': current_user.username,
            'full_name': current_user.full_name,
        },
        'session_id': alert.session_id,
        'coordinates': {
            'latitude': alert.latitude,
            'longitude': alert.longitude,
        },
        'contacts': [
            {
                'name': contact.name,
                'phone': contact.phone,
                'relationship': contact.relationship,
                'priority': contact.priority,
            }
            for contact in contacts
        ],
    }
    body = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    secret = current_app.config.get('SOS_WEBHOOK_SECRET')
    if secret:
        signature = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
        headers['X-RoR-Signature'] = f'sha256={signature}'

    try:
        response = requests.post(
            webhook_url,
            data=body,
            headers=headers,
            timeout=current_app.config.get('SOS_WEBHOOK_TIMEOUT_SECONDS', 5),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        current_app.logger.exception(
            'SOS webhook delivery failed for alert id=%s user id=%s',
            alert.id,
            current_user.id,
        )
        return _finish_sos(alert, 'failed', str(exc)[:500])

    current_app.logger.warning(
        'SOS delivered for alert id=%s user id=%s', alert.id, current_user.id
    )
    return _finish_sos(alert, 'sent', 'Emergency notification accepted by the provider.')


@core_bp.get('/offline')
def offline():
    """Offline fallback page used by the service worker."""
    return render_template('core/offline.html')


@core_bp.get('/service-worker.js')
def service_worker():
    """Serve the worker at root scope so the PWA can cover every page."""
    response = make_response(current_app.send_static_file('sw.js'))
    response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


def _safe_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _finish_sos(alert, status, detail):
    alert.delivery_status = status
    alert.delivery_detail = detail
    db.session.commit()
    sent = status == 'sent'
    return jsonify({
        'status': status,
        'notification_sent': sent,
        'alert_id': alert.id,
        'detail': detail,
    }), 200 if sent else 202
