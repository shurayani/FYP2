# IPECS – Intelligent Personal Expense Categorization System

Implementation of the FYP report (BI23110065): Python · Streamlit · SQLite · OpenCV · Gemini + PaddleOCR (hybrid OCR) ·
TF-IDF + Multinomial Naïve Bayes · Z-score anomaly detection · Prophet forecasts · Supabase offline-first sync · EN/BM interface.

## Run in VS Code (Python 3.10 – 3.12 recommended)
1. Unzip, then **File → Open Folder…** → the `ipecs` folder.
2. Open the VS Code terminal and run **one** of:
   * Windows: `setup_windows.bat`
   * macOS/Linux: `./setup_mac_linux.sh`

   This creates `.venv`, installs the requirements, trains the classifier and starts the app at http://localhost:8501.
3. Next time: activate the venv (`.venv\Scripts\activate`) and run `streamlit run app.py`, or press **F5** (“IPECS (Streamlit)”).

Logins: **admin / admin123** (change `ADMIN_PASSWORD` in `.env`) – anyone who registers becomes a `user`.
Optional demo data: `python scripts/seed_demo_data.py` → login **demo / demo123**.

## Optional online services (copy `.env.example` → `.env`)
* `GEMINI_API_KEY` – Gemini receipt extraction + AI insights. Without it, receipts use PaddleOCR.
* `SUPABASE_URL`, `SUPABASE_KEY` – sync. Run `supabase_schema.sql` once in the Supabase SQL editor first.
* PaddleOCR downloads its model files on the **first** scan (needs internet once); afterwards it works fully offline.

## Report → code map
| Module | Page | Backend |
|---|---|---|
| 1 User Account | `pages/1_Account.py` | `src/auth.py` |
| 2 Receipt | `pages/2_Receipts.py` | `src/receipt_manager.py`, `src/ocr_module.py`, `utils/gemini_helper.py` |
| 3 Transaction | `pages/3_Transactions.py` | `src/db_manager.py`, `src/preprocessor.py`, `src/classifier.py` |
| 4 Category | `pages/4_Categories.py` | `src/db_manager.py` |
| 5 Budget Goal | `pages/5_Budget_Goals.py` | `src/analytics.py` |
| 6 Spending Report | `pages/6_Reports.py` | `src/analytics.py` |
| 7 Anomaly Alert | `pages/7_Anomaly_Alerts.py` | `src/analytics.py` (|Z| > 2.0) |
| 8 Spending Forecast | `pages/8_Forecast.py` | `src/forecast.py` (Prophet + Gemini insights) |
| 9 Sync | `pages/10_Sync_Status.py` | `src/sync_manager.py` (last-write-wins) |
| Dashboard / Admin | `app.py`, `pages/9_Admin_Panel.py` | – |

Tests: `python -m pytest -q tests` · Retrain classifier: `python training/train_model.py`.
