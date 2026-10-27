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
| 1 User Account | `views/1_Account.py` | `src/auth.py` |
| 2 Receipt | `views/2_Receipts.py` | `src/receipt_manager.py`, `src/ocr_module.py`, `utils/gemini_helper.py` |
| 3 Transaction | `views/3_Transactions.py` | `src/db_manager.py`, `src/preprocessor.py`, `src/classifier.py` |
| 4 Category | `views/4_Categories.py` | `src/db_manager.py` |
| 5 Budget Goal | `views/5_Budget_Goals.py` | `src/analytics.py` |
| 6 Spending Report | `views/6_Reports.py` | `src/analytics.py` |
| 7 Anomaly Alert | `views/7_Anomaly_Alerts.py` | `src/analytics.py` (|Z| > 2.0) |
| 8 Spending Forecast | `views/8_Forecast.py` | `src/forecast.py` (Prophet + Gemini insights) |
| 9 Sync | `views/10_Sync_Status.py` | `src/sync_manager.py` (last-write-wins) |
| Dashboard / Admin | `app.py`, `views/9_Admin_Panel.py` | – |

Tests: `python -m pytest -q tests` · Retrain classifier: `python training/train_model.py`.

## Use IPECS on your phone (patch #13)
IPECS keeps running on your computer; the phone opens it in the browser and can install it as an app.
* **Same Wi-Fi:** `python start_phone.py` -> open the printed `http://192.168.x.x:8501` link on the phone.
  Phones only allow a *shortcut* from an `http://` link (browser menu -> Add to Home screen).
* **Install as an app (any network):** install the free [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  (Windows: `winget install --id Cloudflare.cloudflared`, macOS: `brew install cloudflared`), then run
  `python start_phone.py --tunnel` and open the printed `https://....trycloudflare.com` link on the phone.
  Press **Install IPECS app** on the login page (iPhone: Share -> Add to Home Screen).
* Keep the computer on and `start_phone.py` running while you use the phone. A quick-tunnel link changes each
  time it starts; anyone with the link can reach the login page, so change `ADMIN_PASSWORD` in `.env` first.
