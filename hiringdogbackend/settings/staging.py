from .base import *

SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS").split(",")

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE"),
        "HOST": os.environ.get("MYSQL_DATABASE_HOST"),
        "USER": os.environ.get("MYSQL_DATABASE_USER_NAME"),
        "PASSWORD": os.environ.get("MYSQL_ROOT_PASSWORD"),  # "Sumit@Dey",
        "PORT": "3306",
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "charset": "utf8mb4",
        },
    }
}

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "https://app.hdiplatform.in",
    "http://localhost:5173",
]

CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
]

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-cashfree-signature",
    "x-cashfree-timestamp",
    "x-webhook-signature",
    "x-webhook-timestamp",
]

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.environ.get("AWS_ACCESS_KEY"),
            "secret_key": os.environ.get("AWS_SECRET_KEY"),
            "bucket_name": os.environ.get("AWS_BUCKET_NAME"),
            "location": "media",
            "region_name": os.environ.get("AWS_REGION_NAME"),
            "addressing_style": "virtual",
            "signature_version": "s3v4",  # if you use cloudfront then remove this one
            # "custom_domain": os.environ.get("AWS_CUSTOM_DOMAIN"),
        },
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.environ.get("AWS_ACCESS_KEY"),
            "secret_key": os.environ.get("AWS_SECRET_KEY"),
            "bucket_name": os.environ.get("AWS_BUCKET_NAME"),
            "location": "static",
            "region_name": os.environ.get("AWS_REGION_NAME"),
            "addressing_style": "virtual",
            "signature_version": "s3v4",
        },
    },
}

LOG_DIR = os.path.join("/var/log", "hiringdog")
SERVER_EMAIL = "hdipstaging-alerts@hdiplatform.in"
EMAIL_SUBJECT_PREFIX = "[HDIP STAGING ERROR] "
ADMINS = [("Sumit", "sumit.dey@hiringdog.com")]

LOGGING["handlers"]["error_file"]["filename"] = os.path.join(LOG_DIR, "errors.log")
LOGGING["handlers"]["file"]["filename"] = os.path.join(LOG_DIR, "app.log")
LOGGING["loggers"]["django.request"]["handlers"].append("mail_admins")

"""
    AWS_S3_CUSTOM_DOMAIN = (
        os.environ.get("AWS_CUSTOM_DOMAIN")
        or f"{os.environ.get('AWS_BUCKET_NAME')}.s3.amazonaws.com"
    )

    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
"""

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = os.environ.get("EMAIL_PORT")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL")
INTERVIEW_EMAIL = os.environ.get("INTERVIEW_EMAIL")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

LOGIN_URL = "https://app.hdiplatform.in/auth/signin/loginmail"
BASE_URL = "https://hdip.vercel.app/api"
SITE_DOMAIN = "app.hdiplatform.in"

ADMINS = [("Sumit Dey", "sumit.dey@hiringdog.com")]

GOOGLE_REDIRECT_URI = "https://app.hdiplatform.in/interviewer/calendar"
GOOGLE_CLIENT_ID = (
    "376552857175-vikfvim89ffnkh0hoc45djaqd61n2lsh.apps.googleusercontent.com"
)
GOOGLE_CLIENT_SECRET = "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"

CF_CLIENTID = os.environ.get("CF_CLIENTID")
CF_CLIENTSECRET = os.environ.get("CF_CLIENTSECRET")
CF_RETURNURL = os.environ.get("CF_RETURNURL")

TAWKTO_API = os.environ.get("TAWKTO_API")
