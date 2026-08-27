import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("VCMS_SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "VCMS_DATABASE_URI", f"sqlite:///{os.path.join(BASE_DIR, 'vehicles.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    EXPORT_FOLDER = os.path.join(BASE_DIR, "exports")
    BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")
    ALLOWED_IMPORT_EXTENSIONS = {"xlsx", "xls", "csv", "json"}

    # Single-user login credentials (change in production / move to env vars)
    LOGIN_REQUIRED = os.environ.get("VCMS_LOGIN_REQUIRED", "true").lower() == "true"
    ADMIN_USERNAME = os.environ.get("VCMS_ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("VCMS_ADMIN_PASSWORD", "admin123")

    # Reminder thresholds, in days before expiry
    REMINDER_WINDOWS = [30, 15, 7, 1]
