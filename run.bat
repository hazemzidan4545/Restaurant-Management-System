@echo off
echo Starting Restaurant Management System...

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

:: Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)

:: Install requirements if they don't exist
if not exist "venv\Lib\site-packages\flask" (
    echo Installing requirements...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Error: Failed to install requirements
        pause
        exit /b 1
    )
)

:: Set environment variables
set FLASK_APP=run.py
set FLASK_ENV=development
set FLASK_DEBUG=1

:: Start the application
echo Starting Flask application...
python run.py

:: If the application exits, wait for user input
echo.
echo Application has stopped. Press any key to close...
pause >nul
