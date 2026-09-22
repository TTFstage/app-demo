from codicefiscale import codicefiscale
from flask_security import RegisterFormV2
from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, HiddenField, PasswordField, SelectField, StringField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)


def validate_tax_id_code(form, field):
    cf = str(field.data or '').upper().strip()
    if not codicefiscale.is_valid(cf):
        raise ValidationError('Enter a valid Italian tax ID code.')

    required_details = (
        form.first_name.data,
        form.last_name.data,
        form.date_of_birth.data,
        form.gender.data,
        form.birth_city_country.data,
    )
    if not all(required_details):
        return

    try:
        expected = codicefiscale.encode(
            lastname=form.last_name.data.strip(),
            firstname=form.first_name.data.strip(),
            gender=form.gender.data,
            birthdate=form.date_of_birth.data.isoformat(),
            birthplace=form.birth_city_country.data.strip(),
        )
        accepted_codes = set(codicefiscale.decode(expected)['omocodes'])
    except (KeyError, TypeError, ValueError):
        raise ValidationError(
            'The place of birth could not be verified. Enter an Italian municipality or a foreign country.'
        )

    if cf not in accepted_codes:
        raise ValidationError('The tax ID code does not match the personal details entered.')


class ExtendedRegisterForm(RegisterFormV2):
    """Extended registration form with additional fields."""
    first_name = StringField(
        'First Name',
        validators=[DataRequired(message='First name is required.'), Length(min=2, max=100)],
        render_kw={'placeholder': 'Mario'}
    )
    last_name = StringField(
        'Last Name',
        validators=[DataRequired(message='Last name is required.'), Length(min=2, max=100)],
        render_kw={'placeholder': 'Rossi'}
    )
    full_name = HiddenField()
    tax_id_code = StringField(
        'Tax ID Code',
        validators=[
            DataRequired(message='The tax ID code is required.'),
            Length(min=16, max=16, message='The tax ID code must be 16 characters long.'),
            Regexp(r'^[A-Z0-9]{16}$', message='Invalid format.'),
            validate_tax_id_code
        ],
        render_kw={'placeholder': 'RSSMRA85T10A562S'},
        filters=[lambda x: x.upper() if x else x]
    )
    date_of_birth = DateField(
        'Date of Birth',
        validators=[DataRequired(message='Date of birth is required.')],
        render_kw={'placeholder': 'yyyy-mm-dd'},
        format='%Y-%m-%d'
    )
    gender = SelectField(
        'Gender',
        validators=[DataRequired(message='Please select a gender.')],
        choices=[('', 'Select...'), ('M', 'Male'), ('F', 'Female')],
        default=''
    )
    birth_city_country = StringField(
        'City or Country of Birth',
        validators=[DataRequired(message='City or country of birth is required.'), Length(min=2, max=200)],
        render_kw={'placeholder': 'Rome or France'}
    )
    phone_number = StringField(
        'Phone Number',
        validators=[
            Optional(),
            Length(
                max=20,
                message='The phone number cannot exceed %(max)d characters.'
            ),
            Regexp(
                r'^[\d\s\+\-\(\)]*$',
                message='The phone number contains invalid characters.'
            )
        ],
        render_kw={'placeholder': '+39 333 1234567'}
    )

    def validate(self, **kwargs):
        """Persist the split name fields using the existing full_name model column."""
        first_name = str(self.first_name.data or '').strip()
        last_name = str(self.last_name.data or '').strip()
        self.full_name.data = f'{first_name} {last_name}'.strip()
        return super().validate(**kwargs)

    # Override username validator for clearer messages
    @classmethod
    def get_username_validators(cls):
        return [
            Length(
                min=3,
                max=50,
                message='Username must be between %(min)d and %(max)d characters.'
            )
        ]

    # Override email validator for clearer messages
    @classmethod
    def get_email_validators(cls):
        return [
            Length(
                min=5,
                max=120,
                message='Email must be between %(min)d and %(max)d characters.'
            )
        ]

    # Override password validator for clearer messages
    @classmethod
    def get_password_validators(cls, field):
        return []


class SOSContactForm(FlaskForm):
    """Form to add/edit an SOS contact."""
    name = StringField(
        'Full Name',
        validators=[
            DataRequired(message='Name is required.'),
            Length(min=2, max=100, message='Name must be between %(min)d and %(max)d characters.')
        ],
        render_kw={'placeholder': 'e.g. Maria Rossi', 'autofocus': True}
    )
    phone = StringField(
        'Phone Number',
        validators=[
            DataRequired(message='Phone number is required.'),
            Length(min=5, max=20, message='Number must be between %(min)d and %(max)d characters.'),
            Regexp(
                r'^[\d\s\+\-\(\)]+$',
                message='Invalid phone number. Use only digits, spaces and the characters + - ( ).'
            )
        ],
        render_kw={'placeholder': 'e.g. +39 333 1234567'}
    )
    relationship = SelectField(
        'Relationship',
        validators=[Optional()],
        choices=[
            ('', 'Select...'),
            ('Spouse/Partner', 'Spouse/Partner'),
            ('Parent', 'Parent'),
            ('Sibling', 'Sibling'),
            ('Child', 'Child'),
            ('Friend', 'Friend'),
            ('Colleague', 'Colleague'),
            ('Other', 'Other')
        ],
        default=''
    )
    priority = SelectField(
        'Priority',
        validators=[Optional()],
        choices=[
            ('0', 'Low'),
            ('1', 'Medium'),
            ('2', 'High')
        ],
        default='1',
        coerce=int
    )


class ProfileForm(FlaskForm):
    username = StringField(
        'Username',
        validators=[DataRequired(), Length(min=3, max=50)],
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    phone_number = StringField(
        'Phone number',
        validators=[
            Optional(),
            Length(max=20),
            Regexp(r'^[\d\s\+\-\(\)]*$', message='Use only digits, spaces and + - ( ).'),
        ],
    )
    full_name = StringField('Full name', validators=[DataRequired(), Length(min=2, max=200)])
    date_of_birth = DateField('Date of birth', validators=[DataRequired()], format='%Y-%m-%d')
    gender = SelectField(
        'Gender',
        validators=[DataRequired()],
        choices=[('M', 'Male'), ('F', 'Female')],
    )
    birth_city_country = StringField(
        'City or country of birth',
        validators=[DataRequired(), Length(min=2, max=200)],
    )


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current password', validators=[DataRequired()])
    new_password = PasswordField(
        'New password',
        validators=[DataRequired(), Length(min=8, max=128)],
    )
    confirm_password = PasswordField(
        'Confirm password',
        validators=[DataRequired(), EqualTo('new_password', message='Passwords must match.')],
    )


class PreferencesForm(FlaskForm):
    telemetry_enabled = BooleanField('Share ride telemetry')
    fall_detection_enabled = BooleanField('Enable fall detection')
    sos_notifications_enabled = BooleanField('Notify SOS webhook')
    browser_notifications_enabled = BooleanField('Browser notifications')
    high_accuracy_gps = BooleanField('High accuracy GPS')
    map_default_overlays = SelectField(
        'Default map detail',
        choices=[
            ('stations,bicycle_repair', 'Fountains and repair points'),
            ('stations,bicycle_repair,toilets,bicycleParkings', 'All rider stops'),
            ('stations', 'Fountains only'),
            ('', 'No points of interest'),
        ],
    )
    appearance = SelectField(
        'Appearance',
        choices=[
            ('system', 'Use device setting'),
            ('light', 'Light'),
            ('dark', 'Dark'),
        ],
    )


class OnboardingForm(FlaskForm):
    telemetry_enabled = BooleanField('Enable ride telemetry', default=True)
    fall_detection_enabled = BooleanField('Enable fall detection', default=True)
    high_accuracy_gps = BooleanField('Use high accuracy GPS', default=True)
