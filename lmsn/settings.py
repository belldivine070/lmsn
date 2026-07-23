import os
from pathlib import Path
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG')

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'import_export',    
    'widget_tweaks',
    'django_paystack',
    'django_bootstrap5',
    'django_summernote',
    'accounts.apps.AccountsConfig', 
    'payment.apps.PaymentConfig',
    'product.apps.ProductConfig',
    'order.apps.OrderConfig',
    'shopify.apps.ShopifyConfig',
    'cart.apps.CartConfig',
    'core.apps.CoreConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'accounts.middleware.UserActivityMiddleware',
    'core.middleware.SessionCartMiddleware',  
]

ROOT_URLCONF = 'lmsn.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.app_settings_processor', 
                'core.context_processors.extras',
                'core.context_processors.cart_context',
                'core.context_processors.wish_list',
            ],
        },
    },
]

WSGI_APPLICATION = 'lmsn.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': os.getenv('DB_NAME'),
#         'USER': os.getenv('DB_USER'),
#         'PASSWORD': os.getenv('DB_PASSWORD'),
#         'HOST': os.getenv('DB_HOST', '127.0.0.1'),
#         'PORT': os.getenv('DB_PORT', '3306'),
#         'OPTIONS': {
#             'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
#         },
#     }
# }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTHENTICATION_BACKENDS = [
    'accounts.backends.MultiFieldModelBackend', 
    'django.contrib.auth.backends.ModelBackend',
]

# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

# --- STATIC & MEDIA FILES ---
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'), 
]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# # This is the key for app-specific static files
# STATICFILES_FINDERS = [
#     'django.contrib.staticfiles.finders.FileSystemFinder',
#     'django.contrib.staticfiles.finders.AppDirectoriesFinder', # <--- Make sure this is here!
# ]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media/'

# --- FILE UPLOAD SETTINGS ---
# Increase the limit for multi-file uploads (e.g., to 1000)
DATA_UPLOAD_MAX_NUMBER_FILES = 1000

# Optional: You might also want to increase the max payload size 
# if these files are large (e.g., 50MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800


# --- AUTHENTICATION ---
AUTH_USER_MODEL = 'accounts.CustomUser'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:index'
LOGOUT_REDIRECT_URL = 'accounts:login'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- PAYSTACK INTEGRATION ---
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY')
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')

PAYSTACK_SETTINGS = {
    'BUTTON_ID': 'paystack-button',
    'UPLOAD_URL': 'media/paystack',
    'CURRENCY': 'NGN',
    'BUTTON_CLASS': 'btn btn-primary',
}

#Block unwanted bots and crawlers
# CRAWLER_USER_AGENTS = [
#     'Googlebot',
#     'Slurp',
#     'DuckDuckGo',
# ]
AXES_FAILURE_LIMIT = 5  # Lock out after 5 tries
AXES_COOLOFF_TIME = 1   # Lock out for 1 hour
AXES_LOCKOUT_TEMPLATE = 'lockout.html' # Show a custom "You are blocked" page
AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True



# # --- DEPLOYMENT SECURITY ---
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

# GEOIP_PATH = os.path.join(BASE_DIR, 'geoip')

# --- SESIONS ---
# Force session to expire when browser closes (Security best practice)
# SESSION_EXPIRE_AT_BROWSER_CLOSE = True
# Set global session cookie age to 30 minutes
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True

# --- CELERY CONFIGURATION ---
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True
CELERY_BEAT_SCHEDULE = {
    'check-scheduled-broadcasts-every-minute': {
        'task': 'users.tasks.check_scheduled_broadcasts',
        'schedule': crontab(minute='*'),
    },
}

# --- EMAIL SETTINGS ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True #587
EMAIL_USE_SSL = False #467
EMAIL_HOST_USER = os.environ.get('OFFICIAL_EMAIL')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD')


# --- SUMMERNOTE CONFIG ---
SUMMERNOTE_THEME = 'bs5'
SUMMERNOTE_CONFIG = {
    'iframe': {'height': '100%', 'width': '100%'},
    'summernote': {'width': '100%', 'styleWithSpan': False},
    'codemirror': {'lineWrapping': True},
}
