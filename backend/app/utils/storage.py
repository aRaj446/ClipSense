import os

UPLOAD_DIR        = "app/uploads"
METADATA_DIR      = "app/metadata"
TRAILERS_DIR      = "app/trailers"
SMART_UPLOAD_DIR  = "app/uploads/smart"
DB_PATH           = "app/clipsense.db"


def ensure_directories():
    os.makedirs(UPLOAD_DIR,       exist_ok=True)
    os.makedirs(METADATA_DIR,     exist_ok=True)
    os.makedirs(TRAILERS_DIR,     exist_ok=True)
    os.makedirs(SMART_UPLOAD_DIR, exist_ok=True)
