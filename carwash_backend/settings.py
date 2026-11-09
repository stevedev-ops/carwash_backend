import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if available
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure--0o%pxh%-)!2aktfzzgvz*(7iy*$0e5!_4sjg2)ghn8)!s*s_o')

# DEBUG: False in production (Render) by default unless explicitly set to True
DEBUG = os.environ.get('DEBUG', 'True' if not os.environ.get('RENDER') else 'False').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '*').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # 3rd party
    'corsheaders',
    'rest_framework',
    
    # Local apps
    'core',
    'accounts',
    'services',
    'carwash',
    'payments',
    'reports',
]

# Check for whitenoise
try:
    import whitenoise
    HAS_WHITENOISE = True
except ImportError:
    HAS_WHITENOISE = False

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
]
if HAS_WHITENOISE:
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')

MIDDLEWARE.extend([
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
])

ROOT_URLCONF = 'carwash_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'] if (BASE_DIR / 'templates').exists() else [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'carwash_backend.wsgi.application'

# Database configuration: PostgreSQL via DATABASE_URL on Render, or SQLite locally
DATABASE_URL = os.environ.get('DATABASE_URL')
try:
    import dj_database_url
except ImportError:
    dj_database_url = None

if DATABASE_URL and dj_database_url:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Ensure reliable SQLite database operations even when running across Windows/WSL UNC shares
    db_override = os.environ.get('DATABASE_PATH')
    if db_override:
        DB_PATH = Path(db_override)
    elif str(BASE_DIR).startswith('\\\\') or 'wsl.localhost' in str(BASE_DIR):
        local_dir = Path(tempfile.gettempdir()) / 'shell_carwash'
        local_dir.mkdir(parents=True, exist_ok=True)
        DB_PATH = local_dir / 'db.sqlite3'
    else:
        DB_PATH = BASE_DIR / 'db.sqlite3'

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': DB_PATH,
        }
    }

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.authentication.CustomJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# Cross-Origin Resource Sharing (CORS) - Enables communication with Vercel frontend
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
    r"^https://.*\.onrender\.com$",
    r"^http://localhost:[0-9]+$",
    r"^http://127\.0\.0\.1:[0-9]+$",
]

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = [
    'https://carwashfrontend-eorp-kappa.vercel.app',
    'https://*.vercel.app',
    'https://carwash-backend-4kk7.onrender.com',
    'https://*.onrender.com',
    'http://localhost:5173',
    'http://localhost:3000',
    'http://127.0.0.1:8000',
]
extra_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS')
if extra_csrf:
    CSRF_TRUSTED_ORIGINS.extend([origin.strip() for origin in extra_csrf.split(',') if origin.strip()])

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

if HAS_WHITENOISE:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
