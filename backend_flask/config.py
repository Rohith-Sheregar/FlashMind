"""Configuration for the FlashMind backend.

All values are read from environment variables with sensible defaults
for local development.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# Allowed CORS origins (comma-separated Render URL in production).
# e.g. FRONTEND_URL=https://flashmind.onrender.com
FRONTEND_URL = os.environ.get('FRONTEND_URL', '')

# Uploads / generated paths
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', str(BASE_DIR / '..' / 'uploads'))
GENERATED_DIR = os.environ.get('GENERATED_DIR', str(BASE_DIR / '..' / 'generated'))
MAX_UPLOAD_SIZE_BYTES = int(os.environ.get('MAX_UPLOAD_SIZE_BYTES', 10 * 1024 * 1024))
MAX_PDF_UPLOAD_SIZE_BYTES = int(os.environ.get('MAX_PDF_UPLOAD_SIZE_BYTES', 10 * 1024 * 1024))
MAX_FILES_PER_DECK = int(os.environ.get('MAX_FILES_PER_DECK', 20))
MAX_TOTAL_CHARS = int(os.environ.get('MAX_TOTAL_CHARS', 5_000_000))

# Database
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'flashcard_db')
MONGO_COLLECTION = os.environ.get('MONGO_COLLECTION', 'flashcards')
MONGO_SERVER_SELECTION_TIMEOUT_MS = int(os.environ.get('MONGO_SERVER_SELECTION_TIMEOUT_MS', 10000))

# Server
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', 5000))
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('1', 'true', 'yes')

# Auth & Rate Limiting
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'default-dev-secret-key')
RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '200 per hour')
RATE_LIMIT_STORAGE = os.getenv('RATE_LIMIT_STORAGE', 'memory://')
DAILY_GENERATION_LIMIT = int(os.environ.get('DAILY_GENERATION_LIMIT', 5))

# AI
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_VISION_MODEL = os.environ.get('OPENROUTER_VISION_MODEL', 'openai/gpt-4o-mini')

# Email / SMTP
SMTP_EMAIL = os.environ.get('SMTP_EMAIL')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))

# EmailJS
EMAILJS_SERVICE_ID = os.environ.get('EMAILJS_SERVICE_ID')
EMAILJS_TEMPLATE_ID = os.environ.get('EMAILJS_TEMPLATE_ID')
EMAILJS_PUBLIC_KEY = os.environ.get('EMAILJS_PUBLIC_KEY')
EMAILJS_PRIVATE_KEY = os.environ.get('EMAILJS_PRIVATE_KEY')

# Misc
DEFAULT_PAGE_SIZE = int(os.environ.get('DEFAULT_PAGE_SIZE', 50))
ENABLE_FILE_DB = os.environ.get('ENABLE_FILE_DB', 'False').lower() in ('1', 'true', 'yes')
