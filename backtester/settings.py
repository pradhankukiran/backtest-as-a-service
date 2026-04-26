"""Django settings for backtest-as-a-service."""

from pathlib import Path

import environ
from celery.schedules import crontab
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "dev-insecure-change-me"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    REDIS_URL=(str, "redis://localhost:6379/0"),
)

env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "bars",
    "runs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "backtester.auto_login.AutoLoginAsSuperuserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backtester.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backtester.wsgi.application"

DATABASES = {"default": env.db_url("DATABASE_URL")}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAdminUser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Backtest-as-a-Service API",
    "DESCRIPTION": "Run, inspect, and replay trading-strategy backtests.",
    "VERSION": "0.1.0",
}

REDIS_URL = env("REDIS_URL")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # children outlive multi-hour sweeps
CELERY_TASK_TIME_LIMIT = 60
CELERY_TASK_SOFT_TIME_LIMIT = 50
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    # User-supplied strategy code runs here. The default Celery worker does
    # NOT consume this queue; a dedicated worker-untrusted container does,
    # so the blast radius of a runaway strategy stays contained.
    "runs.run_backtest": {"queue": "untrusted"},
}
CELERY_BEAT_SCHEDULE = {
    "ingest-active-bars-nightly": {
        "task": "bars.ingest_all_active_bars",
        "schedule": crontab(hour="2", minute="0"),
        "kwargs": {"days_back": 5},
    },
    "cleanup-stale-runs-weekly": {
        "task": "runs.cleanup_stale_runs",
        "schedule": crontab(hour="3", minute="0", day_of_week="sunday"),
        "kwargs": {"older_than_days": 90},
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

UNFOLD = {
    "SITE_TITLE": "Backtester",
    "SITE_HEADER": "Backtester",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SITE_ICON": lambda request: static("runs/favicon.svg"),
    "THEME": "light",
    "DASHBOARD_CALLBACK": "backtester.admin_dashboard.dashboard_callback",
    "STYLES": [
        lambda request: static("runs/admin-overrides.css"),
    ],
    "COLORS": {
        "primary": {
            "50": "236 253 245",
            "100": "209 250 229",
            "200": "167 243 208",
            "300": "110 231 183",
            "400": "52 211 153",
            "500": "16 185 129",
            "600": "5 150 105",
            "700": "4 120 87",
            "800": "6 95 70",
            "900": "6 78 59",
            "950": "2 44 34",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Operations",
                "separator": True,
                "items": [
                    {
                        "title": "Backtest runs",
                        "icon": "show_chart",
                        "link": reverse_lazy("admin:runs_backtestrun_changelist"),
                    },
                    {
                        "title": "Parameter sweeps",
                        "icon": "tune",
                        "link": reverse_lazy("admin:runs_parametersweep_changelist"),
                    },
                    {
                        "title": "Trades",
                        "icon": "swap_horiz",
                        "link": reverse_lazy("admin:runs_trade_changelist"),
                    },
                    {
                        "title": "Equity points",
                        "icon": "ssid_chart",
                        "link": reverse_lazy("admin:runs_equitypoint_changelist"),
                    },
                    {
                        "title": "Run metrics",
                        "icon": "monitoring",
                        "link": reverse_lazy("admin:runs_runmetrics_changelist"),
                    },
                ],
            },
            {
                "title": "Configuration",
                "separator": True,
                "items": [
                    {
                        "title": "Strategies",
                        "icon": "psychology",
                        "link": reverse_lazy("admin:runs_strategy_changelist"),
                    },
                    {
                        "title": "Symbols",
                        "icon": "candlestick_chart",
                        "link": reverse_lazy("admin:bars_symbol_changelist"),
                    },
                    {
                        "title": "Bars",
                        "icon": "bar_chart",
                        "link": reverse_lazy("admin:bars_bar_changelist"),
                    },
                ],
            },
            {
                "title": "Access",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": "Groups",
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
}
