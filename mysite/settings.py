from pathlib import Path
import os
import logging

# Try to load .env file, but don't fail if it's not available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)

# Log environment variables (safely)
logger.info("Checking environment variables:")
logger.info(f"OPENAI_API_KEY set: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")
logger.info(f"SECRET_KEY set: {'Yes' if os.getenv('SECRET_KEY') else 'No'}")
logger.info(f"DEBUG set: {os.getenv('DEBUG')}")

SECRET_KEY = os.getenv('SECRET_KEY', '0gza9xs+2133ghyx7vhatayhrec@hc=(=*#cjx30+1fzs860+9')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = [
    '*',
    'ask-arthor-production.up.railway.app',
    'stellar-gingersnap-137a05.netlify.app',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'myapp',
    'channels',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mysite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mysite.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Add this to the bottom of settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'myapp': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Add near the bottom with other settings
API_BASE_URL = os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')  # Default to local for development

# Channels configuration
ASGI_APPLICATION = 'mysite.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    } if DEBUG else {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.environ.get('REDIS_URL', 'redis://localhost:6379')],
        },
    }
}

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True  # For development

CORS_ALLOWED_ORIGINS = [
    "https://stellar-gingersnap-137a05.netlify.app",
    "http://localhost:3000",
    "https://ask-arthor-production.up.railway.app",
]

# Add CORS_ORIGIN_WHITELIST as a fallback
CORS_ORIGIN_WHITELIST = [
    "https://stellar-gingersnap-137a05.netlify.app",
    "http://localhost:3000",
    "https://ask-arthor-production.up.railway.app",
]

# Allow all headers and methods temporarily for debugging
CORS_ALLOW_ALL_METHODS = True
CORS_ALLOW_HEADERS = ['*']
CORS_EXPOSE_HEADERS = ['*']
CORS_ALLOW_CREDENTIALS = True

# Allow WebSocket connections
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://\w+\.up\.railway\.app$",
    r"^http://localhost:\d+$",
]

CORS_URLS_REGEX = r'^.*$'
CORS_ORIGIN_ALLOW_ALL = True  # Most permissive setting for debugging