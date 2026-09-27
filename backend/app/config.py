import os
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


def _normalize_database_url(url):
    """Auto-configure SSL for known database providers."""
    if not url or not url.startswith('mysql+pymysql://'):
        return url

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    # Remove SSL params from the query string. PyMySQL does not accept them
    # as top-level connection kwargs; they are provided via connect_args below.
    for key in ['ssl_mode', 'ssl_ca', 'ssl_cert', 'ssl_key', 'ssl_verify_cert', 'ssl_verify_identity']:
        query.pop(key, None)

    new_query = urlencode(query, doseq=True)
    parsed = parsed._replace(query=new_query)

    return urlunparse(parsed)


def _get_engine_options(database_url: str | None) -> dict:
    """Return database-specific engine options."""
    if not database_url:
        return {}

    connect_args = {}

    if database_url.startswith('mysql'):
        connect_args['init_command'] = "SET GLOBAL max_allowed_packet=104857600"

        parsed = urlparse(database_url)
        host = (parsed.hostname or '').lower()

        if 'railway.internal' in host or 'railway.app' in host:
            connect_args['ssl'] = {'ssl_mode': 'REQUIRED'}
        elif 'aivencloud.com' in host:
            connect_args['ssl'] = {
                'ca': '/etc/ssl/certs/aiven-ca.pem',
                'ssl_mode': 'VERIFY_CA'
            }

        return {'connect_args': connect_args}

    return {}


class Config:
    # SECRET_KEY and DATABASE_URL are required in production/testing.
    # No fallbacks are provided to prevent insecure defaults.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(os.environ.get('DATABASE_URL'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database-specific engine options
    SQLALCHEMY_ENGINE_OPTIONS = _get_engine_options(SQLALCHEMY_DATABASE_URI)

    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')

    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

    PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID')
    PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET')
    PAYPAL_MODE = os.environ.get('PAYPAL_MODE', 'sandbox')

    RATELIMIT_DEFAULT = '200 per day; 50 per hour'
    RATELIMIT_STORAGE_URI = 'memory://'
    SECURITY_HEADERS = {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block'
    }

    MAX_IMAGE_SIZE = 50 * 1024 * 1024
    MAX_VIDEO_SIZE = 250 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'avif', 'mp4', 'webm'}

    @classmethod
    def init_app(cls, app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    # WARNING: Insecure fallbacks are only for local development.
    # Never use these in production or testing.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    # Default to MySQL for local dev, but allow override via DATABASE_URL
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(os.environ.get('DATABASE_URL')) or 'mysql+pymysql://root:@localhost/gold_creation'
    SQLALCHEMY_ENGINE_OPTIONS = _get_engine_options(SQLALCHEMY_DATABASE_URI)


class ProductionConfig(Config):
    DEBUG = False

    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        if not os.environ.get('SECRET_KEY'):
            raise RuntimeError("SECRET_KEY must be set via environment variable in production.")
        if not os.environ.get('DATABASE_URL'):
            raise RuntimeError("DATABASE_URL must be set via environment variable in production.")


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False

    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        if not os.environ.get('SECRET_KEY'):
            raise RuntimeError("SECRET_KEY must be set via environment variable in testing.")
        if not os.environ.get('DATABASE_URL'):
            raise RuntimeError("DATABASE_URL must be set via environment variable in testing.")


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
