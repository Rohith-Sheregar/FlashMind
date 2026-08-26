import re
import datetime
import logging
from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

try:
    from backend_flask.services.db_service import get_mongo_client, MONGO_DB_NAME, get_user_generation_count
    from backend_flask.services.email_service import generate_otp, send_otp_email
    from backend_flask.config import DAILY_GENERATION_LIMIT
except ModuleNotFoundError:
    from services.db_service import get_mongo_client, MONGO_DB_NAME, get_user_generation_count
    from services.email_service import generate_otp, send_otp_email
    from config import DAILY_GENERATION_LIMIT

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
OTP_EXPIRY_MINUTES = 5


def get_db():
    client = get_mongo_client()
    return client.get_database(MONGO_DB_NAME)


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not username or not email or not password:
        return jsonify({'error': 'Username, email, and password are required'}), 400
    if len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if not EMAIL_REGEX.match(email):
        return jsonify({'error': 'Please enter a valid email address'}), 400

    db = get_db()
    if db is None:
        return jsonify({'error': 'Database not connected'}), 500

    users = db['users']
    if users.find_one({'username': username}):
        return jsonify({'error': 'Username already exists'}), 400
    if users.find_one({'email': email}):
        return jsonify({'error': 'This email is already registered'}), 400

    otp = generate_otp()
    pending = db['pending_otps']
    pending.delete_many({'email': email})
    pending.insert_one({
        'username': username,
        'email': email,
        'password': bcrypt.generate_password_hash(password).decode('utf-8'),
        'otp': otp,
        'created_at': datetime.datetime.utcnow(),
        'expires_at': datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_EXPIRY_MINUTES)
    })
    pending.create_index('expires_at', expireAfterSeconds=0)

    if not send_otp_email(email, otp):
        logger.warning(f"SMTP failed for {email}. OTP: {otp}")
        return jsonify({'message': 'OTP generated. Check server logs for the code.'}), 200

    return jsonify({'message': 'OTP sent to your email. Please verify to complete registration.'}), 200


@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()
    otp = (data.get('otp') or '').strip()

    if not email or not otp:
        return jsonify({'error': 'Email and OTP are required'}), 400

    db = get_db()
    if db is None:
        return jsonify({'error': 'Database not connected'}), 500

    pending = db['pending_otps']
    record = pending.find_one({'email': email})

    if not record:
        return jsonify({'error': 'No pending verification found. Please register again.'}), 400
    if datetime.datetime.utcnow() > record['expires_at']:
        pending.delete_many({'email': email})
        return jsonify({'error': 'OTP has expired. Please register again.'}), 400
    if record['otp'] != otp:
        return jsonify({'error': 'Invalid OTP. Please try again.'}), 400

    users = db['users']
    if users.find_one({'username': record['username']}):
        pending.delete_many({'email': email})
        return jsonify({'error': 'Username was taken while verifying. Please register again.'}), 400
    if users.find_one({'email': email}):
        pending.delete_many({'email': email})
        return jsonify({'error': 'Email was registered while verifying. Please try logging in.'}), 400

    users.insert_one({
        'username': record['username'],
        'email': email,
        'password': record['password'],
        'created_at': datetime.datetime.utcnow(),
        'email_verified': True
    })
    pending.delete_many({'email': email})

    return jsonify({'message': 'Email verified! Your account has been created successfully.'}), 201


@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    db = get_db()
    if db is None:
        return jsonify({'error': 'Database not connected'}), 500

    pending = db['pending_otps']
    if not pending.find_one({'email': email}):
        return jsonify({'error': 'No pending registration found. Please register first.'}), 400

    new_otp = generate_otp()
    pending.update_one(
        {'email': email},
        {'$set': {
            'otp': new_otp,
            'created_at': datetime.datetime.utcnow(),
            'expires_at': datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_EXPIRY_MINUTES)
        }}
    )

    if not send_otp_email(email, new_otp):
        logger.warning(f"SMTP failed for {email}. OTP: {new_otp}")
        return jsonify({'message': 'OTP generated. Check server logs for the code.'}), 200

    return jsonify({'message': 'A new OTP has been sent to your email.'}), 200


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    db = get_db()
    if db is None:
        return jsonify({'error': 'Database not connected'}), 500

    user = db['users'].find_one({'username': username})
    if user and bcrypt.check_password_hash(user['password'], password):
        token = create_access_token(identity=username)
        return jsonify({'access_token': token, 'username': username}), 200

    return jsonify({'error': 'Invalid credentials'}), 401


@auth_bp.route('/status', methods=['GET'])
@jwt_required()
def user_status():
    current_user = get_jwt_identity()
    count = get_user_generation_count(current_user)
    return jsonify({'generations_used': count, 'limit': DAILY_GENERATION_LIMIT}), 200
