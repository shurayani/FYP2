"""Central configuration. Secrets are read from environment variables / .env
(never hard-coded) as required by NFR14."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # python-dotenv is optional
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RECEIPT_DIR = BASE_DIR / "receipts"
TRAINING_DIR = BASE_DIR / "training"
DB_PATH = DATA_DIR / "ipecs.db"
MODEL_PATH = DATA_DIR / "nb_model.pkl"
VECTORIZER_PATH = DATA_DIR / "tfidf_vectorizer.pkl"
DATASET_PATH = TRAINING_DIR / "receipt_dataset.csv"

for _d in (DATA_DIR, RECEIPT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- External services (all optional: the app works fully offline without them)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "20"))   # seconds before falling back (NFR13)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

# --- Hard-coded administrator (Figure 9: single admin, username "admin")
ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@ipecs.local"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# --- Business rules taken from the report
ANOMALY_Z_THRESHOLD = 2.0          # |Z| > 2.0 (FR10)
MIN_SAMPLES_FOR_ZSCORE = 5         # need a few transactions in a category for a meaningful baseline
MIN_MONTHS_FOR_FORECAST = 3        # Prophet needs some history per category
MAX_UPLOAD_MB = 10                 # receipts: JPEG/PNG up to 10 MB
MIN_F1_THRESHOLD = 0.80            # NFR02
MIN_WEEKS_FOR_FORECAST = 3          # short-history mode: weekly Prophet when < 3 months of data
LOW_CONFIDENCE_THRESHOLD = 0.40     # below this the user is asked to double-check the category
                                    # (re-tune after retraining: Naive Bayes probabilities depend on the dataset)
ITEM_DATASET_PATH = TRAINING_DIR / "receipt_items_dataset.csv"
ITEM_MODEL_PATH = DATA_DIR / "item_model.pkl"
ITEM_VECTORIZER_PATH = DATA_DIR / "item_vectorizer.pkl"
ITEM_MIN_CONF = 0.40                # below this the item model stays silent
