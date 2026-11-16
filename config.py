import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def _db_url():
    url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'trazabilidad.db'))
    # SQLAlchemy 2.x requiere postgresql+psycopg2:// para usar psycopg2
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    return url

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'trz-dev-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads'))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    SESSION_TIMEOUT_MINUTES = int(os.environ.get('SESSION_TIMEOUT_MINUTES', 30))
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15
