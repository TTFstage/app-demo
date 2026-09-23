from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_security import auth_required, current_user, logout_user
from flask_security.utils import hash_password, verify_password
from sqlalchemy import func

from app.auth.forms import (
    ChangePasswordForm,
    OnboardingForm,
    PreferencesForm,
    ProfileForm,
    SOSContactForm,
)
from app.auth.models import SOSContact, User, UserPreference, linked_bike_if_available
from app.i18n import translate
from extensions import db, redis_client, security

auth_bp = Blueprint('auth', __name__)


def get_or_create_preferences(user):
    """Return a persisted preference row for a user."""
    preferences = UserPreference.query.filter_by(user_id=user.id).first()
    if preferences is None:
        preferences = UserPreference(user_id=user.id)
        db.session.add(preferences)
        db.session.commit()
    return preferences


@auth_bp.get("/check_session")
@auth_required()
def check_session():
    """Returns the current user id if the session cookie is valid."""
    from flask import jsonify
    return jsonify({"user_id": current_user.id, "authenticated": True})


@auth_bp.get("/me")
@auth_required()
def me():
    """User profile page: data, logout and account deletion."""
    preferences = get_or_create_preferences(current_user)
    return render_template(
        "auth/private_page.html",
        username=current_user.username,
        phone_number=current_user.phone_number,
        email=current_user.email,
        tax_id_code=current_user.tax_id_code,
        full_name=current_user.full_name,
        date_of_birth=current_user.date_of_birth,
        gender=current_user.gender,
        birth_city_country=current_user.birth_city_country,
        tax_id_masked=(current_user.tax_id_code[:3] + '••••••••••' + current_user.tax_id_code[-3:]) if current_user.tax_id_code else '',
        bike=linked_bike_if_available(current_user),
        sos_contacts_count=SOSContact.query.filter_by(user_id=current_user.id).count(),
        onboarding_completed=preferences.onboarding_completed,
    )


@auth_bp.route("/profile/edit", methods=["GET", "POST"])
@auth_required()
def edit_profile():
    """Update the editable portion of the signed-in user's profile."""
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        username = form.username.data.strip()
        phone_number = (form.phone_number.data or '').strip() or None

        email_owner = User.query.filter(
            func.lower(User.email) == email,
            User.id != current_user.id,
        ).first()
        username_owner = User.query.filter(
            func.lower(User.username) == username.lower(),
            User.id != current_user.id,
        ).first()
        phone_owner = None
        if phone_number:
            phone_owner = User.query.filter(
                User.phone_number == phone_number,
                User.id != current_user.id,
            ).first()

        if email_owner:
            form.email.errors.append('This email is already in use.')
        if username_owner:
            form.username.errors.append('This username is already in use.')
        if phone_owner:
            form.phone_number.errors.append('This phone number is already in use.')

        if not (email_owner or username_owner or phone_owner):
            current_user.email = email
            current_user.username = username
            current_user.phone_number = phone_number
            current_user.full_name = form.full_name.data.strip()
            current_user.date_of_birth = form.date_of_birth.data
            current_user.gender = form.gender.data
            current_user.birth_city_country = form.birth_city_country.data.strip()
            db.session.commit()
            flash('Profile updated.', 'success')
            return redirect(url_for('auth.me'))

    return render_template('auth/edit_profile.html', form=form)


@auth_bp.route("/password/change", methods=["GET", "POST"])
@auth_required()
def change_password():
    """Change the password after confirming the current password."""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not verify_password(form.current_password.data, current_user.password):
            form.current_password.errors.append('The current password is incorrect.')
        else:
            current_user.password = hash_password(form.new_password.data)
            db.session.commit()
            flash('Password changed successfully.', 'success')
            return redirect(url_for('auth.me'))
    return render_template('auth/change_password.html', form=form)


@auth_bp.route("/settings", methods=["GET", "POST"])
@auth_required()
def settings():
    """Manage persisted safety, privacy and map preferences."""
    preferences = get_or_create_preferences(current_user)
    form = PreferencesForm(obj=preferences)
    form.map_default_overlays.choices = [
        ('stations,bicycle_repair', translate('settings.map_fountains_repair')),
        ('stations,bicycle_repair,toilets,bicycleParkings', translate('settings.map_all')),
        ('stations', translate('settings.map_fountains')),
        ('', translate('settings.map_none')),
    ]
    form.appearance.choices = [
        ('system', translate('settings.theme_system')),
        ('light', translate('settings.theme_light')),
        ('dark', translate('settings.theme_dark')),
    ]
    if request.method == 'POST' and 'language' not in request.form:
        form.language.data = preferences.language
    if form.validate_on_submit():
        form.populate_obj(preferences)
        db.session.commit()
        flash(translate('flash.settings_saved'), 'success')
        return redirect(url_for('auth.settings'))
    return render_template(
        'auth/settings.html',
        form=form,
        preferences=preferences,
        webhook_configured=bool(current_app.config.get('SOS_WEBHOOK_URL')),
    )


@auth_bp.route("/onboarding", methods=["GET", "POST"])
@auth_required()
def onboarding():
    """First-run safety and device setup."""
    preferences = get_or_create_preferences(current_user)
    form = OnboardingForm(obj=preferences)
    if form.validate_on_submit():
        preferences.telemetry_enabled = form.telemetry_enabled.data
        preferences.fall_detection_enabled = form.fall_detection_enabled.data
        preferences.high_accuracy_gps = form.high_accuracy_gps.data
        preferences.onboarding_completed = True
        db.session.commit()
        flash('Setup complete. You are ready to ride.', 'success')
        return redirect(url_for('core.index'))
    return render_template('auth/onboarding.html', form=form)


@auth_bp.post("/delete_account")
@auth_required()
def delete_account():
    """Deletes the current user's account."""
    user_to_delete = current_user._get_current_object()
    user_id = user_to_delete.id
    gpx_paths = [Path(shift.gpx_path) for shift in user_to_delete.rider_shifts]
    try:
        logout_user()
        security.datastore.delete_user(user_to_delete)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Account deletion failed for user=%s", user_id)
        flash("Unable to delete the account. Please try again later.", "error")
        return redirect(url_for("core.index"))

    try:
        redis_client.delete(f"position:{user_id}")
    except Exception:
        current_app.logger.exception("Unable to remove live position for deleted user=%s", user_id)

    storage_root = Path(current_app.config["GPX_STORAGE_DIR"]).resolve()
    for gpx_path in gpx_paths:
        try:
            resolved_path = gpx_path.resolve()
            if storage_root == resolved_path.parent or storage_root in resolved_path.parents:
                resolved_path.unlink(missing_ok=True)
            else:
                current_app.logger.error(
                    "Refusing to delete GPX outside storage root: %s", resolved_path
                )
        except OSError:
            current_app.logger.exception("Unable to remove GPX for deleted user=%s", user_id)

    flash("Account deleted successfully.", "info")
    return redirect(url_for("core.index"))


# ==================== SOS CONTACTS CRUD ====================

@auth_bp.route("/sos/contacts", methods=["GET"])
@auth_required()
def list_sos_contacts():
    """Lists all SOS contacts for the current user."""
    contacts = (
        SOSContact.query.filter_by(user_id=current_user.id)
        .order_by(SOSContact.priority.desc(), SOSContact.created_at.asc())
        .all()
    )
    return render_template("auth/sos_contacts_list.html", contacts=contacts)


@auth_bp.route("/sos/contacts/add", methods=["GET", "POST"])
@auth_required()
def add_sos_contact():
    """Adds a new SOS contact."""
    form = SOSContactForm()
    
    if form.validate_on_submit():
        # Check maximum contact limit (max 5)
        existing_count = SOSContact.query.filter_by(user_id=current_user.id).count()
        if existing_count >= 5:
            flash("You have reached the maximum number of SOS contacts (5). Remove an existing one to add a new one.", "error")
            return redirect(url_for("auth.list_sos_contacts"))
        
        contact = SOSContact(
            user_id=current_user.id,
            name=form.name.data.strip(),
            phone=form.phone.data.strip(),
            relationship=form.relationship.data if form.relationship.data else None,
            priority=int(form.priority.data)
        )
        db.session.add(contact)
        db.session.commit()
        
        flash(f"Contact '{contact.name}' added successfully!", "success")
        return redirect(url_for("auth.list_sos_contacts"))
    
    return render_template("auth/sos_contact_form.html", form=form, contact=None)


@auth_bp.route("/sos/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
@auth_required()
def edit_sos_contact(contact_id):
    """Edits an existing SOS contact."""
    contact = SOSContact.query.filter_by(id=contact_id, user_id=current_user.id).first_or_404()
    
    form = SOSContactForm(obj=contact)
    
    if form.validate_on_submit():
        contact.name = form.name.data.strip()
        contact.phone = form.phone.data.strip()
        contact.relationship = form.relationship.data if form.relationship.data else None
        contact.priority = int(form.priority.data)
        db.session.commit()
        
        flash(f"Contact '{contact.name}' updated successfully!", "success")
        return redirect(url_for("auth.list_sos_contacts"))
    
    return render_template("auth/sos_contact_form.html", form=form, contact=contact)


@auth_bp.route("/sos/contacts/<int:contact_id>/delete", methods=["POST"])
@auth_required()
def delete_sos_contact(contact_id):
    """Deletes an SOS contact."""
    contact = SOSContact.query.filter_by(id=contact_id, user_id=current_user.id).first_or_404()
    
    contact_name = contact.name
    db.session.delete(contact)
    db.session.commit()
    
    flash(f"Contact '{contact_name}' deleted.", "info")
    return redirect(url_for("auth.list_sos_contacts"))


@auth_bp.route("/sos/contacts/reorder", methods=["POST"])
@auth_required()
def reorder_sos_contacts():
    """
    Reorders SOS contacts by updating priority.
    Expected JSON: {"contacts": [{"id": 1, "priority": 2}, ...]}
    """
    from flask import jsonify
    
    data = request.get_json()
    if not data or 'contacts' not in data:
        return jsonify({"error": "Invalid data"}), 400
    
    try:
        for item in data['contacts']:
            contact = SOSContact.query.filter_by(
                id=item['id'], 
                user_id=current_user.id
            ).first()
            if contact:
                contact.priority = int(item['priority'])
        
        db.session.commit()
        return jsonify({"status": "ok"}), 200
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
