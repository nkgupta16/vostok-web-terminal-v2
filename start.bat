@echo off
title Vostok Web Terminal
echo.
echo  ========================================
echo    VOSTOK WEB TERMINAL - Starting...
echo  ========================================
echo.

cd /d "%~dp0"

:: Kill any existing Streamlit on port 8501
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8501 ^| findstr LISTENING 2^>nul') do (
    echo  Killing existing process on port 8501 (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Launch Streamlit
echo  Starting Streamlit on http://localhost:8501
echo  Press Ctrl+C to stop
echo.
start http://localhost:8501
streamlit run app.py --server.port 8501 --server.headless true

pause

:: Launch Streamlit
echo  Starting Streamlit on http://localhost:8501
echo  Press Ctrl+C to stop
echo.
start http://localhost:8501
streamlit run app.py --server.port 8501 --server.headless true

pause
