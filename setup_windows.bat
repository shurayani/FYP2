@echo off
REM One-time setup + run for Windows. Double-click or run in the VS Code terminal.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || goto :err
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
echo Installing core requirements...
pip install -r requirements.txt || goto :err
echo Installing PaddleOCR (offline OCR engine, large download)...
pip install -r requirements-ocr.txt || echo [WARNING] PaddleOCR install failed - IPECS still runs; use Gemini or manual entry.
if not exist .env copy .env.example .env >nul
python training\train_model.py
echo.
echo Setup complete. Starting IPECS...
streamlit run app.py
goto :eof
:err
echo Setup failed. Make sure Python 3.10-3.12 is installed and on PATH.
pause
