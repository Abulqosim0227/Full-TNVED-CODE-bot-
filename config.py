# config.py
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


BOT_TOKEN = "Your bot token"
MODEL_NAME = "sentence-transformers/LaBSE"

# SIMILARITY_THRESHOLD and TOP_K are now defined within predictor.py
# keeping them here might cause confusion

PG_CONFIG = {
    "user": "postgres",
    "password": "123456",
    "host": "localhost",
    "port": 5432,
    "database": "postgres"
}
