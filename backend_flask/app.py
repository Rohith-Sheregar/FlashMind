import os
import logging
import datetime
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

try:
    from .routes.upload_routes import upload_bp
    from .routes.flashcard_routes import flashcard_bp
    from .routes.auth_routes import auth_bp
    from .routes.ai_routes import ai_bp
    from .config import (
        UPLOAD_DIR, GENERATED_DIR, HOST, PORT, DEBUG,
        JWT_SECRET_KEY, RATE_LIMIT_DEFAULT, RATE_LIMIT_STORAGE,
        FRONTEND_URL,
    )
except (ImportError, ModuleNotFoundError):
    from routes.upload_routes import upload_bp
    from routes.flashcard_routes import flashcard_bp
    from routes.auth_routes import auth_bp
    from routes.ai_routes import ai_bp
    from config import (
        UPLOAD_DIR, GENERATED_DIR, HOST, PORT, DEBUG,
        JWT_SECRET_KEY, RATE_LIMIT_DEFAULT, RATE_LIMIT_STORAGE,
        FRONTEND_URL,
    )

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

_cors_origins = [o.strip() for o in FRONTEND_URL.split(',') if o.strip()] if FRONTEND_URL else []
if not _cors_origins:
    _cors_origins = ['http://localhost:5000', 'http://127.0.0.1:5000']
CORS(app, origins=_cors_origins, supports_credentials=True)

app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(days=7)
jwt = JWTManager(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[RATE_LIMIT_DEFAULT],
    storage_uri=RATE_LIMIT_STORAGE
)

app.register_blueprint(upload_bp, url_prefix='/api')
app.register_blueprint(flashcard_bp, url_prefix='/api')
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(ai_bp, url_prefix='/api')

limiter.limit("10 per minute; 30 per hour")(app.view_functions['auth.register'])
limiter.limit("15 per minute")(app.view_functions['auth.verify_otp'])
limiter.limit("5 per minute; 10 per hour")(app.view_functions['auth.resend_otp'])
limiter.limit("10 per minute; 50 per hour")(app.view_functions['auth.login'])
limiter.limit("20 per hour")(app.view_functions['upload_bp.upload'])
limiter.limit("30 per hour")(app.view_functions['ai_bp.generate_quiz_route'])
limiter.limit("30 per hour")(app.view_functions['ai_bp.generate_mindmap_route'])
limiter.limit("30 per hour")(app.view_functions['ai_bp.extract_topics_route'])
limiter.limit("30 per hour")(app.view_functions['ai_bp.generate_flashcards_route'])

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify(error='Too many requests. Please slow down and try again later.'), 429


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/health')
@limiter.exempt
def health():
    return 'OK', 200


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
    app.run(host=HOST, port=PORT, debug=DEBUG)
