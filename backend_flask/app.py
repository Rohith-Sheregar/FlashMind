from flask import Flask
import os
import logging

# Allow running the module two ways:
# 1) as a package: `python -m backend_flask.app` (preferred)
# 2) as a script from inside the package folder: `python app.py`
#
# Relative imports (leading dot) require package context. When the file is
# executed directly as a script, __package__ may be None and relative imports
# raise ImportError. Try the package-relative imports first and fall back to
# local imports when running as a script.
try:
    from .routes.upload_routes import upload_bp
    from .routes.flashcard_routes import flashcard_bp
    from .routes.auth_routes import auth_bp
    from .routes.ai_routes import ai_bp
    from .config import UPLOAD_DIR, GENERATED_DIR, HOST, PORT, DEBUG, JWT_SECRET_KEY, RATE_LIMIT_DEFAULT, RATE_LIMIT_STORAGE
except (ImportError, ModuleNotFoundError):
    # Running as a script (no package). Import from local module paths.
    from routes.upload_routes import upload_bp
    from routes.flashcard_routes import flashcard_bp
    from routes.auth_routes import auth_bp
    from routes.ai_routes import ai_bp
    from config import UPLOAD_DIR, GENERATED_DIR, HOST, PORT, DEBUG, JWT_SECRET_KEY, RATE_LIMIT_DEFAULT, RATE_LIMIT_STORAGE

from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS


logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Disable static file caching for development
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
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

# ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/health')
@limiter.exempt
def health():
    """Lightweight health-check endpoint for Render / UptimeRobot keep-alive pings."""
    return 'OK', 200


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
    logger.info(f"Starting backend on {HOST}:{PORT}, uploads={UPLOAD_DIR}, generated={GENERATED_DIR}")
    app.run(host=HOST, port=PORT, debug=DEBUG)
