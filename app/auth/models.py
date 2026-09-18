import re
import secrets
import string
import uuid
from datetime import datetime, timezone

from flask_security import RoleMixin, SQLAlchemyUserDatastore, UserMixin
from sqlalchemy.orm import validates

from extensions import db

roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id', ondelete='CASCADE')),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id', ondelete='CASCADE'))
)

class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), unique=True, nullable=True)
    tax_id_code = db.Column(db.String(16), unique=True, nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    date_of_birth = db.Column(db.Date(), nullable=False)
    gender = db.Column(db.String(1), nullable=False)
    birth_city_country = db.Column(db.String(200), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean(), default=True)
    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=False, default=lambda: uuid.uuid4().hex)
    roles = db.relationship('Role', secondary=roles_users, backref=db.backref('users', lazy='selectin'))
    group_memberships = db.relationship('GroupMembership', back_populates='user', cascade='all, delete-orphan')
    rider_shifts = db.relationship('RiderShift', back_populates='user', cascade='all, delete-orphan')
    fall_events = db.relationship('FallEvent', back_populates='user', cascade='all, delete-orphan')
    sos_contacts = db.relationship('SOSContact', back_populates='user', cascade='all, delete-orphan')
    activities = db.relationship('Activity', back_populates='user', cascade='all, delete-orphan')
    preference = db.relationship(
        'UserPreference',
        back_populates='user',
        cascade='all, delete-orphan',
        uselist=False,
    )
    sos_alerts = db.relationship('SOSAlert', back_populates='user', cascade='all, delete-orphan')

    # Validation to ensure that empty phone numbers are stored as NULL in the database
    @validates("phone_number")
    def validate_phone_number(self, key, value):
        if value is not None and not str(value).strip():
            return None  # Store NULL instead of empty string
        return value

class GroupMembership(db.Model):
    __tablename__ = 'group_memberships'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True)
    
    role = db.Column(db.String(20), default='member', nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship('User', back_populates='group_memberships')
    group = db.relationship('Group', back_populates='members')

class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    code = db.Column(db.String(12), unique=True, nullable=False, index=True)
    security_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    members = db.relationship('GroupMembership', back_populates='group', cascade='all, delete-orphan')

    @staticmethod
    def generate_group_code():
        """Generates a unique code for the group (e.g. 'abc-defg-hij')."""
        part1 = ''.join(secrets.choice(string.ascii_lowercase) for _ in range(3))
        part2 = ''.join(secrets.choice(string.ascii_lowercase) for _ in range(4))
        part3 = ''.join(secrets.choice(string.ascii_lowercase) for _ in range(3))
        return f"{part1}-{part2}-{part3}"

    @staticmethod
    def normalize_code(raw_code: str) -> str:
        """
        Normalizes the code to the standard format 'xxx-yyyy-zzz'.
        Supports input with or without dashes and is case-insensitive.
        """
        if not raw_code:
            return ""
        cleaned = re.sub(r'[^a-zA-Z]', '', raw_code).lower()
        if len(cleaned) == 10:
            return f"{cleaned[:3]}-{cleaned[3:7]}-{cleaned[7:]}"
        return raw_code.strip().lower()

    def generate_security_token(self):
        """Generates a new random url-safe security token."""
        self.security_token = secrets.token_urlsafe(32)
        return self.security_token

    def revoke_security_token(self):
        """Revokes the current security token, invalidating old invite links."""
        self.security_token = None

class RiderShift(db.Model):
    __tablename__ = 'rider_shifts'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    gpx_path = db.Column(db.String(512), nullable=False)
    total_distance_km = db.Column(db.Float, nullable=True)
    duration_min = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship('User', back_populates='rider_shifts')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'session_id', name='uq_rider_shifts_user_session'),
    )

class FallEvent(db.Model):
    __tablename__ = 'fall_events'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    user = db.relationship('User', back_populates='fall_events')

    __table_args__ = (
        db.UniqueConstraint(
            'user_id', 'session_id', 'timestamp', name='uq_fall_events_user_session_timestamp'
        ),
    )


class SOSContact(db.Model):
    """Emergency contacts for SOS notifications."""
    __tablename__ = 'sos_contacts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    relationship = db.Column(db.String(50), nullable=True)  # e.g.: "Spouse", "Sibling", "Friend"
    priority = db.Column(db.Integer, default=0, nullable=False)  # Priority order
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    user = db.relationship('User', back_populates='sos_contacts')

    @validates('name')
    def validate_name(self, key, value):
        if value:
            return value.strip()
        return value

    @validates('phone')
    def validate_phone(self, key, value):
        if value:
            return re.sub(r'[^\d+\-\s\(\)]', '', value)  # Keep only digits and valid phone characters
        return value


class UserPreference(db.Model):
    """Persistent, user-controlled app and privacy preferences."""

    __tablename__ = 'user_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    telemetry_enabled = db.Column(db.Boolean, nullable=False, default=True)
    fall_detection_enabled = db.Column(db.Boolean, nullable=False, default=True)
    sos_notifications_enabled = db.Column(db.Boolean, nullable=False, default=True)
    browser_notifications_enabled = db.Column(db.Boolean, nullable=False, default=False)
    high_accuracy_gps = db.Column(db.Boolean, nullable=False, default=True)
    map_default_overlays = db.Column(db.String(120), nullable=False, default='stations,bicycle_repair')
    appearance = db.Column(db.String(16), nullable=False, default='system')
    onboarding_completed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship('User', back_populates='preference')


class SOSAlert(db.Model):
    """Auditable result of an SOS request and its external delivery attempt."""

    __tablename__ = 'sos_alerts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    session_id = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    delivery_status = db.Column(db.String(32), nullable=False, default='not_configured')
    delivery_detail = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', back_populates='sos_alerts')

# We initialize the user_datastore here, but we will pass it to security.init_app in the factory
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
